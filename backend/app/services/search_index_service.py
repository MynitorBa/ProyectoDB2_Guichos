"""Construcción y mantenimiento del índice de búsqueda de productos.

Elasticsearch es una proyección reconstruible del catálogo: nunca decide
precio ni stock. Cada documento se arma con el **estado actual** de las
fuentes autoritativas (MongoDB para la descripción, MySQL para ofertas,
inventario, ventas flash y ventas, Neo4j para el rating) en el momento de
indexar. Por eso indexar es idempotente e independiente del orden de los
eventos que lo disparan.

La versión externa de cada documento es el instante (µs) en que se leyó ese
estado. Si dos escrituras compiten, Elasticsearch rechaza la que leyó datos
más antiguos (``version_type=external_gte``).

Desde la Entrega 4 (mapping v2) cada documento lleva además el **vector** del
texto del producto (nombre, categorías, descripción y atributos), calculado por
el servicio de embeddings. Solo se recalcula si cambia ese texto (huella en
``vector_texto_hash``); si el servicio no responde, el producto se indexa sin
vector y la reconciliación periódica lo completa cuando vuelve.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from bson import ObjectId
from elasticsearch import Elasticsearch, NotFoundError, helpers
from pymongo.database import Database
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core import salud
from app.core.config import settings
from app.core.time import utc_now
from app.models.pedido import Pedido, PedidoLinea
from app.models.promocion_flash import PromocionFlash
from app.services import embeddings_client
from app.services.offer_service import listar_ofertas_por_referencias

logger = logging.getLogger(__name__)

MAPPINGS_DIR = Path(__file__).resolve().parents[3] / 'database' / 'elasticsearch'
VERSION_MAPPING = 2  # v2 (Entrega 4): agrega el campo vectorial
PREFIJO_INDICE = 'productos_v'

# Atributos con demasiados valores distintos para servir como faceta; siguen
# siendo buscables mediante ``texto_atributos``.
ATRIBUTOS_NO_FACETABLES = {
    'isbn', 'paginas', 'peso_g', 'autor', 'editorial', 'procesador',
    'incluye', 'origen', 'num_piezas',
}
LARGO_MAXIMO_FACETA = 30


# ── Definición e índices ──────────────────────────────────────────────────────

def cargar_definicion(version: int = VERSION_MAPPING) -> dict:
    ruta = MAPPINGS_DIR / f'productos_v{version}.json'
    return json.loads(ruta.read_text(encoding='utf-8'))


def nombre_indice_nuevo(version: int = VERSION_MAPPING) -> str:
    return f'{PREFIJO_INDICE}{version}_{utc_now():%Y%m%d%H%M%S}'


def crear_indice(es: Elasticsearch, nombre: str, version: int = VERSION_MAPPING) -> None:
    es.indices.create(index=nombre, **cargar_definicion(version))


def indice_actual(es: Elasticsearch, alias: str | None = None) -> str | None:
    alias = alias or settings.ES_INDEX_ALIAS
    try:
        return next(iter(es.indices.get_alias(name=alias)))
    except NotFoundError:
        return None


def cambiar_alias(es: Elasticsearch, nuevo: str, alias: str | None = None) -> list[str]:
    """Apunta el alias al índice nuevo en una sola operación atómica.

    Devuelve los índices que dejaron de estar detrás del alias.
    """
    alias = alias or settings.ES_INDEX_ALIAS
    anteriores = []
    try:
        anteriores = list(es.indices.get_alias(name=alias))
    except NotFoundError:
        pass
    acciones = [{'remove': {'index': indice, 'alias': alias}} for indice in anteriores]
    acciones.append({'add': {'index': nuevo, 'alias': alias}})
    es.indices.update_aliases(actions=acciones)
    return [indice for indice in anteriores if indice != nuevo]


def asegurar_indice(es: Elasticsearch, alias: str | None = None) -> str:
    """Crea el índice y el alias si todavía no existen. Devuelve el índice vigente."""
    actual = indice_actual(es, alias)
    if actual:
        return actual
    nuevo = nombre_indice_nuevo()
    crear_indice(es, nuevo)
    cambiar_alias(es, nuevo, alias)
    return nuevo


def version_lectura() -> int:
    """Versión externa: instante de lectura del estado, en microsegundos."""
    return time.time_ns() // 1000


# ── Construcción de documentos ────────────────────────────────────────────────

def _iso(valor) -> str | None:
    if isinstance(valor, datetime):
        return valor.isoformat()
    return valor


def _primera_imagen(imagenes) -> str | None:
    for imagen in imagenes or []:
        url = imagen.get('url') if isinstance(imagen, dict) else imagen
        if url:
            return url
    return None


def _categorias(doc: dict) -> list[dict]:
    categorias = doc.get('categorias') or ([doc['categoria']] if doc.get('categoria') else [])
    return [
        {'slug': c['slug'], 'nombre': c.get('nombre', c['slug'])}
        for c in categorias
        if isinstance(c, dict) and c.get('slug')
    ]


def _atributo(nombre: str, valor, origen: str) -> dict | None:
    if valor is None or valor == '' or isinstance(valor, (dict, list)):
        return None
    entrada = {'nombre': nombre, 'origen': origen}
    if isinstance(valor, bool):
        entrada['valor'] = 'Sí' if valor else 'No'
    elif isinstance(valor, (int, float)):
        entrada['valor'] = f'{valor:g}'
        entrada['valor_num'] = float(valor)
    else:
        entrada['valor'] = str(valor).strip()
    entrada['facetable'] = (
        nombre not in ATRIBUTOS_NO_FACETABLES
        and len(entrada['valor']) <= LARGO_MAXIMO_FACETA
    )
    return entrada


def _atributos(doc: dict, variantes: list[dict]) -> list[dict]:
    resultado, vistos = [], set()
    fuentes = [(doc.get('atributos') or {}, 'producto')]
    fuentes += [(v.get('atributos') or {}, 'variante') for v in variantes]
    for atributos, origen in fuentes:
        for nombre, valor in atributos.items():
            entrada = _atributo(nombre, valor, origen)
            if entrada and (nombre, entrada['valor']) not in vistos:
                vistos.add((nombre, entrada['valor']))
                resultado.append(entrada)
    return resultado


def _entradas_sugerencia(nombre: str) -> list[str]:
    """El nombre completo y sus sufijos: 'galaxy' también sugiere 'Samsung Galaxy A54'."""
    palabras = nombre.split()
    entradas = [nombre] if nombre else []
    for i in range(1, min(len(palabras), 5)):
        # Solo sufijos que empiezan con una palabra real ("Galaxy"), no con "15" o "de".
        if len(palabras[i]) >= 3 and any(c.isalpha() for c in palabras[i]):
            entradas.append(' '.join(palabras[i:]))
    return entradas


def _ratings(mysql_db: Session, refs: list[str]) -> dict[str, tuple[float, int]]:
    """Calificación pública desde la autoridad MySQL; Neo4j es proyección."""
    from app.services.review_mysql_service import ratings_por_producto

    return ratings_por_producto(mysql_db, refs)


def _ventas(mysql_db: Session, refs: list[str]) -> dict[str, int]:
    filas = (
        mysql_db.query(PedidoLinea.producto_ref, func.coalesce(func.sum(PedidoLinea.cantidad), 0))
        .join(Pedido, Pedido.id == PedidoLinea.pedido_id)
        .filter(PedidoLinea.producto_ref.in_(refs))
        .filter(Pedido.estado.notin_(['cancelado', 'reembolsado']))
        .group_by(PedidoLinea.producto_ref)
        .all()
    )
    return {ref: int(total) for ref, total in filas}


def _flash_activas(mysql_db: Session, offer_ids: list[int]) -> dict[int, float]:
    if not offer_ids:
        return {}
    ahora = utc_now()
    filas = mysql_db.query(PromocionFlash).filter(
        PromocionFlash.oferta_id.in_(offer_ids),
        PromocionFlash.estado == 'activa',
        PromocionFlash.inicia_en <= ahora,
        PromocionFlash.finaliza_en > ahora,
    ).all()
    return {p.oferta_id: float(p.precio_promocional) for p in filas}


def _documento(doc: dict, ofertas: list[dict], variantes: list[dict], flash: dict[int, float],
               ventas: int, rating: tuple[float, int] | None) -> dict:
    disponibles = [o for o in ofertas if o['disponible']]
    precios_flash = [
        (flash[o['oferta_id']], o['precio']) for o in disponibles if o['oferta_id'] in flash
    ]
    precios_visibles = [o['precio'] for o in disponibles] + [p for p, _ in precios_flash]
    todos = [o['precio'] for o in ofertas] + [p for p, _ in precios_flash]
    precio_min = min(precios_visibles or todos or [0.0])
    precio_max = max(todos or [0.0])
    descuento = max(
        (round((1 - promo / normal) * 100) for promo, normal in precios_flash if normal),
        default=0,
    )
    # Precio que muestra el catálogo: la oferta principal (TiendaYa disponible,
    # luego la más barata) o la flash más barata si mejora su precio normal.
    # Es el que se usa para ordenar y filtrar, para que coincida con la vista.
    principal = ofertas[0] if ofertas else None
    mejor_flash = min(precios_flash, default=None)
    if mejor_flash and mejor_flash[0] < mejor_flash[1]:
        precio_visible = mejor_flash[0]
    elif principal:
        precio_visible = principal['precio']
    else:
        precio_visible = precio_min
    categorias = _categorias(doc)
    nombre = doc.get('nombre', '')
    texto_atributos = ' '.join(
        str(valor) for valor in (doc.get('atributos') or {}).values() if isinstance(valor, str)
    )

    documento = {
        'producto_id': str(doc['_id']),
        'sku': doc.get('sku'),
        'nombre': nombre,
        'descripcion': doc.get('descripcion') or '',
        'texto_atributos': texto_atributos,
        'categorias': categorias,
        'atributos': _atributos(doc, variantes),
        'vendedores': sorted({o['vendedor_nombre'] for o in ofertas}),
        'vendedor_ids': sorted({o['vendedor_id'] for o in ofertas}),
        # Para buscar dentro de una tienda: "con stock" significa con stock de ese vendedor.
        'vendedores_con_stock': sorted({o['vendedor_id'] for o in disponibles}),
        'precio': precio_visible,
        'precio_min': precio_min,
        'precio_max': precio_max,
        'moneda': (ofertas[0]['moneda'] if ofertas else doc.get('moneda')) or 'GTQ',
        'stock_total': sum(o['stock'] for o in ofertas),
        'tiene_stock': bool(disponibles),
        'es_tiendaya': any(o['es_tiendaya'] for o in disponibles),
        'tiene_flash': bool(precios_flash),
        'descuento_flash_pct': descuento,
        'ventas_totales': ventas,
        'imagen': _primera_imagen(doc.get('imagenes')),
        'estado': doc.get('estado', 'activo'),
        'fecha_creacion': _iso(doc.get('fecha_creacion')),
        'fecha_actualizacion': _iso(doc.get('fecha_actualizacion')),
        'indexado_en': utc_now().isoformat(),
        'sugerencia': {
            'input': _entradas_sugerencia(nombre),
            'weight': 1 + min(ventas, 1_000_000),
        },
    }
    if rating:
        documento['rating_promedio'], documento['num_resenas'] = rating
    return documento


def construir_documentos(
    mysql_db: Session,
    mongo: Database,
    producto_refs: list[str] | None = None,
    neo4j_driver=None,
) -> dict[str, dict | None]:
    """Arma los documentos de búsqueda en lote.

    Devuelve ``{producto_ref: documento}``. El valor es ``None`` cuando el
    producto no existe o no está activo, y por tanto debe salir del índice.
    """
    filtro = {'estado': 'activo'} if producto_refs is None else {
        '_id': {'$in': [ObjectId(ref) for ref in producto_refs if ObjectId.is_valid(ref)]}
    }
    docs = {str(doc['_id']): doc for doc in mongo.productos.find(filtro)}
    refs = list(docs) if producto_refs is None else list(producto_refs)
    activos = [ref for ref in refs if docs.get(ref, {}).get('estado') == 'activo']

    ofertas = listar_ofertas_por_referencias(mysql_db, activos)
    flash = _flash_activas(
        mysql_db, [o['oferta_id'] for lista in ofertas.values() for o in lista]
    )
    ventas = _ventas(mysql_db, activos) if activos else {}
    ratings = _ratings(mysql_db, activos)
    variantes = defaultdict(list)
    for variante in mongo.producto_variantes.find(
        {'producto_ref': {'$in': activos}, 'estado': 'activa'}, {'producto_ref': 1, 'atributos': 1}
    ):
        variantes[variante['producto_ref']].append(variante)

    return {
        ref: _documento(
            docs[ref], ofertas.get(ref, []), variantes.get(ref, []), flash,
            ventas.get(ref, 0), ratings.get(ref),
        ) if ref in activos else None
        for ref in refs
    }


# ── Vectores (Entrega 4) ──────────────────────────────────────────────────────

def texto_vector(documento: dict) -> str:
    """Texto que se convierte en vector: el del documento de búsqueda ya armado."""
    texto = embeddings_client.texto_producto({
        'nombre': documento.get('nombre'),
        'categorias': documento.get('categorias'),
        'descripcion': documento.get('descripcion'),
    })
    atributos = (documento.get('texto_atributos') or '').strip()
    return f'{texto}. {atributos}' if atributos else texto


def _huella(texto: str) -> str:
    return hashlib.sha256(f'{settings.EMBEDDINGS_MODEL}\n{texto}'.encode('utf-8')).hexdigest()


def dimensiones_vector() -> int:
    return cargar_definicion()['mappings']['properties']['vector']['dims']


def _vectores_vigentes(es: Elasticsearch, ids: list[str]) -> dict[str, dict]:
    """Vector y huella que ya tiene cada producto en el índice vigente."""
    if not ids:
        return {}
    try:
        respuesta = es.mget(index=settings.ES_INDEX_ALIAS, ids=ids,
                            source=['vector', 'vector_texto_hash', 'vector_modelo'])
    except NotFoundError:
        return {}
    return {d['_id']: d['_source'] for d in respuesta['docs'] if d.get('found') and d['_source'].get('vector')}


_indices_con_vector: dict[str, bool] = {}


def indice_tiene_vector(es: Elasticsearch, indice: str | None = None) -> bool:
    """True si el índice (o el que está detrás del alias) ya usa el mapping con vector.

    Un índice v1 tiene mapping estricto y rechazaría el campo: hasta que se
    migre con ``reindex_search.py --recrear`` se sigue indexando sin vectores.
    """
    nombre = indice or indice_actual(es)
    if not nombre:
        return False
    if nombre not in _indices_con_vector:
        mapping = next(iter(es.indices.get_mapping(index=nombre).values()))['mappings']
        _indices_con_vector[nombre] = 'vector' in mapping.get('properties', {})
    return _indices_con_vector[nombre]


def adjuntar_vectores(es: Elasticsearch, documentos: dict[str, dict | None], *,
                      indice: str | None = None) -> dict:
    """Agrega el vector a cada documento. Reutiliza el vigente si el texto no cambió.

    ``indice`` es el índice de destino (por defecto, el del alias). Devuelve un
    resumen: reutilizados, calculados y sin_vector (servicio caído).
    """
    activos = {ref: doc for ref, doc in documentos.items() if doc is not None}
    resumen = {'reutilizados': 0, 'calculados': 0, 'sin_vector': 0}
    if not activos or not indice_tiene_vector(es, indice):
        return resumen
    huellas = {ref: _huella(texto_vector(doc)) for ref, doc in activos.items()}
    vigentes = _vectores_vigentes(es, list(activos))
    pendientes = []
    for ref, doc in activos.items():
        previo = vigentes.get(ref)
        if previo and previo.get('vector_texto_hash') == huellas[ref]:
            doc.update(vector=previo['vector'], vector_texto_hash=huellas[ref],
                       vector_modelo=previo.get('vector_modelo'))
            resumen['reutilizados'] += 1
        else:
            pendientes.append(ref)
    if pendientes:
        vectores = embeddings_client.generar([texto_vector(activos[ref]) for ref in pendientes])
        dims = dimensiones_vector()
        if vectores is None or any(len(v) != dims for v in vectores):
            if vectores is not None:
                logger.error('El modelo de embeddings no produce %s dimensiones; revise EMBEDDINGS_MODEL.', dims)
            resumen['sin_vector'] = len(pendientes)
        else:
            for ref, vector in zip(pendientes, vectores):
                activos[ref].update(vector=vector, vector_texto_hash=huellas[ref],
                                    vector_modelo=settings.EMBEDDINGS_MODEL)
            resumen['calculados'] = len(pendientes)
    return resumen


def ids_sin_vector(es: Elasticsearch) -> list[str]:
    """Productos activos indexados sin vector (el servicio no respondía al indexarlos)."""
    if not indice_tiene_vector(es):
        return []
    return [
        hit['_id'] for hit in helpers.scan(
            es, index=settings.ES_INDEX_ALIAS, _source=False,
            query={'query': {'bool': {
                'filter': [{'term': {'estado': 'activo'}}],
                'must_not': [{'exists': {'field': 'vector'}}],
            }}},
        )
    ]


# ── Escritura en el índice ────────────────────────────────────────────────────

def _acciones(documentos: dict[str, dict | None], indice: str, version: int):
    for ref, documento in documentos.items():
        base = {'_index': indice, '_id': ref, 'version': version, 'version_type': 'external_gte'}
        if documento is None:
            yield {**base, '_op_type': 'delete'}
        else:
            yield {**base, '_op_type': 'index', '_source': documento}


def escribir_documentos(
    es: Elasticsearch,
    documentos: dict[str, dict | None],
    *,
    indice: str | None = None,
    version: int | None = None,
    refrescar: bool = False,
) -> dict:
    """Indexa o elimina en bloque. Es idempotente.

    Un conflicto de versión significa que el índice ya tiene un estado más
    reciente y se considera éxito. Una eliminación de algo inexistente también.
    """
    indice = indice or settings.ES_INDEX_ALIAS
    version = version or version_lectura()
    resumen = {'indexados': 0, 'eliminados': 0, 'omitidos': 0}
    for ok, item in helpers.streaming_bulk(
        es, _acciones(documentos, indice, version),
        raise_on_error=False, raise_on_exception=True, refresh=refrescar,
    ):
        operacion, detalle = next(iter(item.items()))
        estado = detalle.get('status')
        if ok:
            resumen['indexados' if operacion == 'index' else 'eliminados'] += 1
        elif estado in (404, 409):
            resumen['omitidos'] += 1
        else:
            raise RuntimeError(f'Elasticsearch rechazó {operacion} {detalle.get("_id")}: {detalle.get("error")}')
    return resumen


def _como_fecha(valor) -> datetime | None:
    if isinstance(valor, datetime):
        return valor
    if isinstance(valor, str):
        return datetime.fromisoformat(valor)
    return None


def ids_indexados(es: Elasticsearch) -> dict[str, str | None]:
    """{producto_id: indexado_en} de todo el índice vigente."""
    return {
        hit['_id']: hit['_source'].get('indexado_en')
        for hit in helpers.scan(
            es, index=settings.ES_INDEX_ALIAS, _source=['indexado_en'],
            query={'query': {'match_all': {}}},
        )
    }


def reconciliar_desfasados(es: Elasticsearch, mysql_db: Session, mongo: Database, neo4j_driver=None) -> dict:
    """Reindexa solo lo que el outbox pudo no haber cubierto.

    Las ediciones de catálogo se escriben primero en MongoDB y después se
    encola su evento en MySQL; si el proceso cae entre ambos pasos, el índice
    queda atrasado. Aquí se detectan productos editados después de su último
    indexado, ausentes del índice o que ya no están activos.
    """
    asegurar_indice(es)
    indexados = ids_indexados(es)
    desfasados = []
    for doc in mongo.productos.find({'estado': 'activo'}, {'fecha_actualizacion': 1}):
        ref = str(doc['_id'])
        indexado_en = _como_fecha(indexados.pop(ref, None))
        actualizado = _como_fecha(doc.get('fecha_actualizacion'))
        if indexado_en is None or (actualizado and actualizado > indexado_en):
            desfasados.append(ref)
    # Lo que queda en ``indexados`` ya no está activo en MongoDB.
    refs = desfasados + sorted(indexados)
    # Productos que se indexaron sin vector porque el servicio de embeddings no respondía.
    if salud.disponible('embeddings'):
        refs += [ref for ref in ids_sin_vector(es) if ref not in refs]
    resumen = (
        indexar_productos(es, mysql_db, mongo, refs, neo4j_driver, refrescar=True)
        if refs else {'indexados': 0, 'eliminados': 0, 'omitidos': 0}
    )
    resumen['depurados'] = depurar_borrados(es)
    return resumen


# Proporción de documentos borrados a partir de la cual se purgan.
MAX_BORRADOS = 0.2


def depurar_borrados(es: Elasticsearch, *, maximo: float = MAX_BORRADOS) -> int:
    """Purga del índice las versiones viejas de documentos ya reemplazados.

    Cada reindexado de un producto deja su versión anterior marcada como
    borrada hasta que Lucene fusiona segmentos. El grafo HNSW del kNN las sigue
    recorriendo: si los vecinos más cercanos son versiones borradas, se
    descartan y el kNN puede devolver menos resultados, o ninguno, aunque haya
    productos parecidos. Se purgan cuando pasan de ``maximo`` del total.
    Devuelve cuántos había (0 si no hizo falta).

    Corre con la reconciliación (cada 10 minutos). Los borrados de los últimos
    segundos los retiene Elasticsearch (soft deletes, para recuperar réplicas)
    y se quitan en la siguiente pasada.
    """
    nombre = indice_actual(es)
    if not nombre:
        return 0
    docs = es.indices.stats(index=nombre, metric='docs')['indices'][nombre]['primaries']['docs']
    borrados = docs.get('deleted', 0)
    if not borrados or borrados / (borrados + docs.get('count', 0)) <= maximo:
        return 0
    es.indices.forcemerge(index=nombre, only_expunge_deletes=True)
    logger.info('Índice %s: se purgaron %s documentos borrados.', nombre, borrados)
    return borrados


def indexar_productos(
    es: Elasticsearch,
    mysql_db: Session,
    mongo: Database,
    producto_refs: list[str],
    neo4j_driver=None,
    refrescar: bool = False,
) -> dict:
    """Lee el estado actual de los productos indicados y lo proyecta al índice."""
    version = version_lectura()
    documentos = construir_documentos(mysql_db, mongo, producto_refs, neo4j_driver)
    vectores = adjuntar_vectores(es, documentos)
    resumen = escribir_documentos(es, documentos, version=version, refrescar=refrescar)
    return {**resumen, 'vectores': vectores}
