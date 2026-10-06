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
"""

from __future__ import annotations

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

from app.core.config import settings
from app.core.time import utc_now
from app.models.pedido import Pedido, PedidoLinea
from app.models.promocion_flash import PromocionFlash
from app.services.offer_service import listar_ofertas_por_referencias

logger = logging.getLogger(__name__)

MAPPINGS_DIR = Path(__file__).resolve().parents[3] / 'database' / 'elasticsearch'
VERSION_MAPPING = 1
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


def _ratings(neo4j_driver, refs: list[str]) -> dict[str, tuple[float, int]]:
    if neo4j_driver is None or not refs:
        return {}
    try:
        with neo4j_driver.session() as s:
            filas = s.run(
                """
                MATCH (r:Reseña {estado: 'aprobada'})-[:SOBRE]->(p:Producto)
                WHERE p.ref IN $refs
                RETURN p.ref AS ref, avg(r.calificacion) AS promedio, count(r) AS total
                """,
                refs=refs,
            ).data()
        return {f['ref']: (round(f['promedio'] or 0.0, 2), f['total']) for f in filas}
    except Exception as exc:  # El rating es opcional para indexar.
        logger.warning('Neo4j no disponible al indexar ratings: %s', exc)
        return {}


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
    ratings = _ratings(neo4j_driver, activos)
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
    if not refs:
        return {'indexados': 0, 'eliminados': 0, 'omitidos': 0}
    return indexar_productos(es, mysql_db, mongo, refs, neo4j_driver, refrescar=True)


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
    return escribir_documentos(es, documentos, version=version, refrescar=refrescar)
