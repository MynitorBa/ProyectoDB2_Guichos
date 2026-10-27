"""Búsqueda de productos sobre Elasticsearch.

Reparto de responsabilidades:

- **Elasticsearch decide qué productos y en qué orden**: texto libre con
  tolerancia a errores, sinónimos, prefijos, relevancia y facetas calculadas
  con agregaciones.
- **MySQL decide el precio y el stock que se muestran**: la página de
  resultados se hidrata con ``catalog_service.enriquecer_productos``. Los
  rangos y conteos de precio de las facetas provienen de la proyección del
  índice, que puede ir unos instantes por detrás (consistencia eventual).
- **Si Elasticsearch no responde**, la búsqueda continúa sobre MongoDB con la
  coincidencia exacta anterior y la respuesta lo indica con ``degradado``.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field, replace

import redis as redis_lib
from bson import ObjectId
from elastic_transport import TransportError
from elasticsearch import ApiError, Elasticsearch
from pymongo.database import Database
from sqlalchemy.orm import Session

from app.core import salud
from app.core.config import settings
from app.models.categoria import Categoria
from app.services import catalog_service
from app.services import catalogo_respaldo_service as catalogo_respaldo

logger = logging.getLogger(__name__)

ORDENES = ('relevancia', 'precio_asc', 'precio_desc', 'nombre_asc', 'reciente', 'mas_vendidos', 'descuento_desc')
RANGOS_PRECIO = (
    (None, 100), (100, 250), (250, 500), (500, 1000),
    (1000, 2500), (2500, 5000), (5000, None),
)
MAX_ATRIBUTOS_FACETA = 8
# Errores tolerados por palabra: 0 hasta 4 letras, 1 de 5 a 7, 2 desde 8.
FUZZINESS = 'AUTO:5,8'
ERRORES_MOTOR = (TransportError, ApiError)


def _consultar(es: Elasticsearch, **argumentos) -> dict:
    """``es.search`` pasando por el detector de fallas del motor.

    Con el circuito abierto no se intenta: se lanza el mismo error de transporte
    para que el llamador use su respaldo sin esperar el timeout.
    """
    if not salud.disponible('elasticsearch'):
        raise TransportError('Elasticsearch marcado como no disponible (circuito abierto)')
    try:
        respuesta = es.search(index=settings.ES_INDEX_ALIAS, **argumentos)
    except TransportError as exc:
        salud.registrar_falla('elasticsearch', exc)
        raise
    salud.registrar_exito('elasticsearch')
    return respuesta


@dataclass
class ParametrosBusqueda:
    q: str = ''
    categoria: str | None = None
    vendedores: list[str] = field(default_factory=list)
    precio_min: float | None = None
    precio_max: float | None = None
    atributos: dict[str, list[str]] = field(default_factory=dict)
    solo_stock: bool = False
    solo_flash: bool = False
    solo_tiendaya: bool = False
    orden: str | None = None
    page: int = 1
    page_size: int = 20
    # Búsqueda dentro de una tienda: limita a productos con ofertas de este
    # vendedor y muestra el precio de su oferta, no el de la oferta principal.
    vendedor_id: int | None = None

    @property
    def texto(self) -> str:
        return (self.q or '').strip()

    @property
    def orden_efectivo(self) -> str:
        if self.orden in ORDENES:
            return self.orden
        return 'relevancia' if self.texto else 'mas_vendidos'


def normalizar(texto: str) -> str:
    sin_tildes = unicodedata.normalize('NFKD', texto or '')
    return ''.join(c for c in sin_tildes if not unicodedata.combining(c)).lower().strip()


# ── Construcción de la consulta ───────────────────────────────────────────────

def _consulta_texto(q: str) -> dict:
    """Varias estrategias combinadas; cada una aporta puntaje si coincide.

    1. Coincidencia exacta de todas las palabras, con sinónimos (``telefono``
       también busca celulares). Es la señal más fuerte.
    2. Coincidencia difusa: 1 error en palabras de 5 a 7 letras y 2 desde 8
       (``samsng`` → Samsung). Las palabras de 4 letras o menos no se
       corrigen: con un error de margen ``tala`` coincidiría con "tela",
       "talla" o "bala"; esas búsquedas cortas las cubre el prefijo (4).
       Usa el analizador sin sinónimos porque la expansión de sinónimos
       multi-palabra no se combina con la difusa.
    3. Recuperación amplia: basta con la mayoría de las palabras.
    4. Prefijos sobre n-gramas, para búsquedas incompletas (``sams``).
    5. Frase en el nombre, que premia el orden correcto de las palabras.
    6. SKU exacto.
    """
    campos = ['nombre^4', 'categorias.nombre^2', 'texto_atributos^1.5', 'descripcion']
    return {
        'bool': {
            'should': [
                {'multi_match': {
                    'query': q, 'type': 'best_fields', 'fields': campos,
                    'operator': 'and', 'boost': 3,
                }},
                {'multi_match': {
                    'query': q, 'type': 'best_fields',
                    'fields': ['nombre^3', 'texto_atributos', 'descripcion^0.5'],
                    'analyzer': 'es_texto', 'fuzziness': FUZZINESS, 'prefix_length': 1,
                    'max_expansions': 50, 'operator': 'and', 'boost': 1.5,
                }},
                {'multi_match': {
                    'query': q, 'type': 'best_fields', 'fields': campos,
                    'analyzer': 'es_texto', 'fuzziness': FUZZINESS, 'prefix_length': 1,
                    # Con 2 o más palabras basta el 75 % ("laptop barata").
                    'minimum_should_match': '1<75%', 'boost': 0.5,
                }},
                {'match': {'nombre.autocompletar': {'query': q, 'operator': 'and', 'boost': 1}}},
                {'match_phrase': {'nombre': {'query': q, 'slop': 2, 'boost': 3}}},
                {'term': {'sku': {'value': q, 'boost': 20}}},
            ],
            'minimum_should_match': 1,
        }
    }


def filtros_posteriores(p: ParametrosBusqueda) -> dict[str, dict]:
    """Filtros elegidos por el usuario, uno por faceta.

    Se aplican como ``post_filter`` para que cada faceta pueda contar sin su
    propio filtro (facetas disyuntivas): al elegir un vendedor, los conteos de
    los demás vendedores no caen a cero.
    """
    filtros: dict[str, dict] = {}
    if p.categoria:
        filtros['categoria'] = {'term': {'categorias.slug': p.categoria}}
    if p.vendedores:
        filtros['vendedor'] = {'terms': {'vendedores': p.vendedores}}
    if p.precio_min is not None or p.precio_max is not None:
        rango = {}
        if p.precio_min is not None:
            rango['gte'] = p.precio_min
        if p.precio_max is not None:
            rango['lte'] = p.precio_max
        filtros['precio'] = {'range': {'precio': rango}}
    if p.solo_stock:
        filtros['stock'] = (
            {'term': {'vendedores_con_stock': p.vendedor_id}} if p.vendedor_id is not None
            else {'term': {'tiene_stock': True}}
        )
    if p.solo_flash:
        filtros['flash'] = {'term': {'tiene_flash': True}}
    if p.solo_tiendaya:
        filtros['tiendaya'] = {'term': {'es_tiendaya': True}}
    for nombre, valores in sorted(p.atributos.items()):
        if valores:
            filtros[f'attr:{nombre}'] = {'nested': {
                'path': 'atributos',
                'query': {'bool': {'filter': [
                    {'term': {'atributos.nombre': nombre}},
                    {'terms': {'atributos.valor': valores}},
                ]}},
            }}
    return filtros


def _excepto(filtros: dict[str, dict], *claves: str) -> dict:
    resto = [f for k, f in filtros.items() if k not in claves]
    return {'bool': {'filter': resto}} if resto else {'match_all': {}}


def _agregaciones(filtros: dict[str, dict], p: ParametrosBusqueda) -> dict:
    rangos = [
        {**({'from': desde} if desde is not None else {}), **({'to': hasta} if hasta is not None else {})}
        for desde, hasta in RANGOS_PRECIO
    ]
    aggs = {
        'categorias': {'filter': _excepto(filtros, 'categoria'),
                       'aggs': {'valores': {'terms': {'field': 'categorias.slug', 'size': 50}}}},
        'vendedores': {'filter': _excepto(filtros, 'vendedor'),
                       'aggs': {'valores': {'terms': {'field': 'vendedores', 'size': 30}}}},
        'precio': {'filter': _excepto(filtros, 'precio'), 'aggs': {
            'rangos': {'range': {'field': 'precio', 'ranges': rangos}},
            'estadisticas': {'stats': {'field': 'precio'}},
        }},
        'con_stock': {'filter': {'bool': {'filter': [
            _excepto(filtros, 'stock'), {'term': {'tiene_stock': True}}]}}},
        'flash': {'filter': {'bool': {'filter': [
            _excepto(filtros, 'flash'), {'term': {'tiene_flash': True}}]}}},
        'tiendaya': {'filter': {'bool': {'filter': [
            _excepto(filtros, 'tiendaya'), {'term': {'es_tiendaya': True}}]}}},
        # Atributos no seleccionados: se cuentan con todos los filtros activos.
        'atributos': {'filter': _excepto(filtros), 'aggs': {'anidados': {
            'nested': {'path': 'atributos'},
            'aggs': {'facetables': {'filter': {'term': {'atributos.facetable': True}}, 'aggs': {
                'nombres': {'terms': {'field': 'atributos.nombre', 'size': 30}, 'aggs': {
                    'valores': {'terms': {'field': 'atributos.valor', 'size': 20}},
                }},
            }}},
        }}},
    }
    # Atributos seleccionados: cada uno cuenta sin su propio filtro (disyuntivo).
    for nombre in p.atributos:
        aggs[f'attr:{nombre}'] = {'filter': _excepto(filtros, f'attr:{nombre}'), 'aggs': {'anidados': {
            'nested': {'path': 'atributos'},
            'aggs': {'del_atributo': {'filter': {'term': {'atributos.nombre': nombre}}, 'aggs': {
                'valores': {'terms': {'field': 'atributos.valor', 'size': 50}},
            }}},
        }}}
    return aggs


def _orden(orden: str) -> list:
    return {
        'relevancia': ['_score', {'ventas_totales': 'desc'}, {'nombre.orden': 'asc'}],
        'precio_asc': [{'precio': 'asc'}, {'nombre.orden': 'asc'}],
        'precio_desc': [{'precio': 'desc'}, {'nombre.orden': 'asc'}],
        'nombre_asc': [{'nombre.orden': 'asc'}],
        'reciente': [{'fecha_creacion': 'desc'}, {'nombre.orden': 'asc'}],
        'mas_vendidos': [{'ventas_totales': 'desc'}, '_score', {'nombre.orden': 'asc'}],
        'descuento_desc': [{'descuento_flash_pct': 'desc'}, {'ventas_totales': 'desc'}],
    }[orden]


def construir_consulta(p: ParametrosBusqueda) -> dict:
    """Cuerpo completo de la búsqueda; separado para probarlo y medirlo."""
    filtros = filtros_posteriores(p)
    alcance = [{'term': {'estado': 'activo'}}]
    if p.vendedor_id is not None:
        # El alcance de tienda no es una faceta: también limita los conteos.
        alcance.append({'term': {'vendedor_ids': p.vendedor_id}})
    base = {'bool': {
        'filter': alcance,
        'must': [_consulta_texto(p.texto)] if p.texto else [],
    }}
    cuerpo = {
        'query': {'function_score': {
            'query': base,
            # La popularidad desempata entre productos igual de relevantes.
            'functions': [
                {'field_value_factor': {'field': 'ventas_totales', 'factor': 0.5, 'modifier': 'log2p', 'missing': 0}},
                {'field_value_factor': {'field': 'rating_promedio', 'modifier': 'ln2p', 'missing': 0}},
                {'filter': {'term': {'tiene_stock': True}}, 'weight': 1},
            ],
            'score_mode': 'sum',
            'boost_mode': 'multiply',
        }},
        'aggs': _agregaciones(filtros, p),
        'sort': _orden(p.orden_efectivo),
        'from': (p.page - 1) * p.page_size,
        'size': p.page_size,
        '_source': ['producto_id'],
        'track_total_hits': True,
    }
    if filtros:
        cuerpo['post_filter'] = {'bool': {'filter': list(filtros.values())}}
    if p.texto:
        cuerpo['highlight'] = {
            'pre_tags': ['<mark>'], 'post_tags': ['</mark>'], 'encoder': 'html',
            'fields': {
                'nombre': {'number_of_fragments': 0},
                'descripcion': {'fragment_size': 120, 'number_of_fragments': 1},
            },
        }
        cuerpo['suggest'] = {
            'text': p.texto,
            'correccion': {'phrase': {
                'field': 'nombre.sugeridor',
                'size': 1,
                'gram_size': 3,
                'max_errors': 2,
                'direct_generator': [{
                    'field': 'nombre.sugeridor', 'suggest_mode': 'always', 'min_word_length': 3,
                }],
                # Solo sugerir frases que de verdad devuelven productos (de la
                # tienda, si la búsqueda es dentro de una).
                'collate': {'query': {'source': {'bool': {
                    'must': {'match': {
                        'nombre': {'query': '{{suggestion}}', 'operator': 'and', 'fuzziness': 0},
                    }},
                    'filter': alcance,
                }}}, 'prune': False},
            }},
        }
    return cuerpo


def como_argumentos(cuerpo: dict) -> dict:
    """El cliente de Python nombra ``from_`` y ``source`` lo que el JSON llama ``from`` y ``_source``."""
    renombres = {'from': 'from_', '_source': 'source'}
    return {renombres.get(clave, clave): valor for clave, valor in cuerpo.items()}


# ── Respuesta ─────────────────────────────────────────────────────────────────

def _etiquetas_categorias(mysql_db: Session) -> dict[str, str]:
    return {slug: nombre for slug, nombre in mysql_db.query(Categoria.slug, Categoria.nombre)}


def _etiquetas_atributos(mongo: Database) -> dict[str, str]:
    etiquetas = {}
    if not salud.disponible('mongo'):
        return etiquetas
    try:
        for esquema in mongo.categoria_esquemas.find({}, {'atributos.nombre': 1, 'atributos.etiqueta': 1}):
            for atributo in esquema.get('atributos', []):
                etiquetas.setdefault(atributo['nombre'], atributo.get('etiqueta') or atributo['nombre'])
    except catalogo_respaldo.ERRORES_MONGO as exc:
        # Sin MongoDB las facetas de atributos muestran el nombre técnico.
        salud.registrar_falla('mongo', exc)
    return etiquetas


def _etiqueta_rango(desde, hasta) -> str:
    if desde is None:
        return f'Hasta Q{hasta:,.0f}'
    if hasta is None:
        return f'Más de Q{desde:,.0f}'
    return f'Q{desde:,.0f} – Q{hasta:,.0f}'


def _facetas(aggs: dict, p: ParametrosBusqueda, mysql_db: Session, mongo: Database) -> dict:
    categorias = _etiquetas_categorias(mysql_db)
    etiquetas_attr = _etiquetas_atributos(mongo)

    atributos: dict[str, dict] = {}
    for bucket in aggs['atributos']['anidados']['facetables']['nombres']['buckets']:
        nombre = bucket['key']
        atributos[nombre] = {
            'nombre': nombre,
            'etiqueta': etiquetas_attr.get(nombre, nombre.replace('_', ' ').capitalize()),
            'conteo': bucket['doc_count'],
            'valores': [{'valor': v['key'], 'conteo': v['doc_count']} for v in bucket['valores']['buckets']],
        }
    for nombre, seleccion in p.atributos.items():
        buckets = aggs[f'attr:{nombre}']['anidados']['del_atributo']['valores']['buckets']
        atributos[nombre] = {
            'nombre': nombre,
            'etiqueta': etiquetas_attr.get(nombre, nombre.replace('_', ' ').capitalize()),
            'conteo': sum(b['doc_count'] for b in buckets),
            'valores': [{'valor': b['key'], 'conteo': b['doc_count']} for b in buckets],
        }
    for faceta in atributos.values():
        seleccion = set(p.atributos.get(faceta['nombre'], []))
        for valor in faceta['valores']:
            valor['seleccionado'] = valor['valor'] in seleccion
    # Seleccionados primero; luego los atributos presentes en más productos y
    # con más de un valor posible (un único valor no ayuda a filtrar).
    visibles = sorted(
        (f for f in atributos.values() if f['nombre'] in p.atributos or len(f['valores']) > 1),
        key=lambda f: (f['nombre'] not in p.atributos, -f['conteo']),
    )[:MAX_ATRIBUTOS_FACETA]

    precio = aggs['precio']
    stats = precio['estadisticas']
    return {
        'categorias': [
            {'valor': b['key'], 'etiqueta': categorias.get(b['key'], b['key']),
             'conteo': b['doc_count'], 'seleccionado': b['key'] == p.categoria}
            for b in aggs['categorias']['valores']['buckets']
        ],
        'vendedores': [
            {'valor': b['key'], 'etiqueta': b['key'], 'conteo': b['doc_count'],
             'seleccionado': b['key'] in p.vendedores}
            for b in aggs['vendedores']['valores']['buckets']
        ],
        'precio': {
            'min': stats['min'], 'max': stats['max'],
            'rangos': [
                {'desde': desde, 'hasta': hasta, 'etiqueta': _etiqueta_rango(desde, hasta), 'conteo': b['doc_count']}
                for (desde, hasta), b in zip(RANGOS_PRECIO, precio['rangos']['buckets'])
                if b['doc_count']
            ],
        },
        'disponibilidad': {
            'con_stock': aggs['con_stock']['doc_count'],
            'flash': aggs['flash']['doc_count'],
            'tiendaya': aggs['tiendaya']['doc_count'],
        },
        'atributos': visibles,
    }


def _parece_incompleta(q: str, nombres: list[str]) -> bool:
    """True si cada palabra buscada es el inicio de una palabra de los resultados.

    ``licu`` o ``mous`` son búsquedas a medio escribir, no errores: si ya
    encontraron "Licuadora" o "Mouse", sugerir otra palabra confunde.
    """
    palabras = {p for nombre in nombres for p in re.findall(r'\w+', normalizar(nombre))}
    return all(
        any(palabra.startswith(token) for palabra in palabras)
        for token in re.findall(r'\w+', normalizar(q))
    )


def _sugerencia(respuesta: dict, q: str, nombres: list[str]) -> str | None:
    if nombres and _parece_incompleta(q, nombres):
        return None
    opciones = respuesta.get('suggest', {}).get('correccion', [{}])[0].get('options', [])
    for opcion in opciones:
        if opcion.get('collate_match', True) and normalizar(opcion['text']) != normalizar(q):
            return opcion['text']
    return None


def _hidratar(
    ids: list[str], resaltados: dict[str, dict], mysql_db: Session, mongo: Database, redis_db,
    vendedor_id: int | None = None,
) -> list[dict]:
    """Página de resultados con precio, stock y flash autoritativos de MySQL/Redis."""
    docs, _ = catalogo_respaldo.productos_por_ids(mongo, ids)
    ordenados = [docs[i] for i in ids if i in docs]
    items, _ = catalog_service.enriquecer_productos(
        ordenados, mysql_db, redis_db, vendedor_id=vendedor_id
    )
    for item in items:
        if item['_id'] in resaltados:
            item['resaltado'] = resaltados[item['_id']]
    return items


def _armar_respuesta(respuesta: dict, p: ParametrosBusqueda, mysql_db: Session, mongo: Database, redis_db) -> dict:
    hits = respuesta['hits']['hits']
    ids = [hit['_id'] for hit in hits]
    resaltados = {
        hit['_id']: {campo: fragmentos[0] for campo, fragmentos in hit.get('highlight', {}).items()}
        for hit in hits if hit.get('highlight')
    }
    total = respuesta['hits']['total']['value']
    items = _hidratar(ids, resaltados, mysql_db, mongo, redis_db, p.vendedor_id)
    return {
        'items': items,
        'total': total,
        'page': p.page,
        'page_size': p.page_size,
        'total_pages': max(1, -(-total // p.page_size)),
        'orden': p.orden_efectivo,
        'facetas': _facetas(respuesta['aggregations'], p, mysql_db, mongo),
        'sugerencia': (
            _sugerencia(respuesta, p.texto, [i.get('nombre', '') for i in items[:3]])
            if p.texto else None
        ),
        'degradado': False,
        'motor': 'elasticsearch',
        'tiempo_ms': respuesta.get('took'),
        'sin_coincidencias': False,
    }


def _sin_texto(p: ParametrosBusqueda, *, conservar_filtros: bool) -> ParametrosBusqueda:
    """La misma búsqueda sin el texto (y opcionalmente sin los filtros del usuario).

    El alcance de tienda (``vendedor_id``) se conserva siempre: dentro de una
    tienda nunca se muestran productos de otros vendedores.
    """
    alternativa = replace(p, q='')
    if not conservar_filtros:
        alternativa = replace(
            alternativa, categoria=None, vendedores=[], precio_min=None, precio_max=None,
            atributos={}, solo_stock=False, solo_flash=False, solo_tiendaya=False,
        )
    return alternativa


def _tiene_filtros(p: ParametrosBusqueda) -> bool:
    return bool(
        p.categoria or p.vendedores or p.precio_min is not None or p.precio_max is not None
        or p.atributos or p.solo_stock or p.solo_flash or p.solo_tiendaya
    )


def _alternativa_sin_coincidencias(
    es: Elasticsearch, mysql_db: Session, mongo: Database, p: ParametrosBusqueda, redis_db,
) -> dict | None:
    """Productos populares cuando el texto no coincide con nada.

    Primero respeta los filtros elegidos; si con ellos tampoco hay productos,
    los quita. El usuario siempre ve algo, y la respuesta dice que no son
    coincidencias de su búsqueda.
    """
    intentos = [True, False] if _tiene_filtros(p) else [True]
    for conservar in intentos:
        alternativa = _sin_texto(p, conservar_filtros=conservar)
        try:
            respuesta = _consultar(es, **como_argumentos(construir_consulta(alternativa)))
        except ERRORES_MOTOR as exc:
            logger.warning('No se pudo calcular la alternativa sin coincidencias: %s', exc)
            return None
        if respuesta['hits']['total']['value']:
            resultado = _armar_respuesta(respuesta, alternativa, mysql_db, mongo, redis_db)
            resultado['alternativa'] = 'populares_con_filtros' if conservar and _tiene_filtros(p) else 'populares'
            return resultado
    return None


def buscar(
    es: Elasticsearch,
    mysql_db: Session,
    mongo: Database,
    p: ParametrosBusqueda,
    redis_db=None,
) -> dict:
    try:
        respuesta = _consultar(es, **como_argumentos(construir_consulta(p)))
    except ERRORES_MOTOR as exc:
        logger.warning('Elasticsearch no disponible; búsqueda degradada a MongoDB: %s', exc)
        return buscar_en_mongo(mysql_db, mongo, p, redis_db)

    resultado = _armar_respuesta(respuesta, p, mysql_db, mongo, redis_db)
    if resultado['total'] or not p.texto:
        return resultado
    # El texto no coincide con ningún producto: en lugar de una página vacía se
    # muestran productos populares, marcados como tales (no son coincidencias).
    alternativa = _alternativa_sin_coincidencias(es, mysql_db, mongo, p, redis_db)
    if alternativa is None:
        return resultado
    alternativa.update({
        'sin_coincidencias': True,
        'consulta': p.texto,
        'orden': p.orden_efectivo,
        'sugerencia': resultado['sugerencia'],
        'tiempo_ms': (respuesta.get('took') or 0) + (alternativa.get('tiempo_ms') or 0),
    })
    return alternativa


# ── Respaldo sobre MongoDB ────────────────────────────────────────────────────

ORDEN_RESPALDO = {
    'relevancia': 'mas_vendidos', 'precio_asc': 'precio_asc', 'precio_desc': 'precio_desc',
    'nombre_asc': 'nombre_asc', 'reciente': 'reciente', 'mas_vendidos': 'mas_vendidos',
    'descuento_desc': 'descuento_desc',
}


def buscar_en_mongo(mysql_db: Session, mongo: Database, p: ParametrosBusqueda, redis_db=None) -> dict:
    """Modo degradado: coincidencia exacta de subcadena, sin relevancia ni tolerancia.

    Solo admite filtros de categoría, precio, stock y flash; las facetas se
    limitan a conteos por categoría.
    """
    sin_coincidencias = False
    resultado = catalog_service.listar_productos(
        mongo, mysql_db,
        categoria_slug=p.categoria,
        precio_min=p.precio_min,
        precio_max=p.precio_max,
        disponible=True if p.solo_stock else None,
        q=p.texto or None,
        page=p.page,
        page_size=p.page_size,
        orden=ORDEN_RESPALDO[p.orden_efectivo],
        vendedor_id=p.vendedor_id,
        solo_flash=p.solo_flash,
        redis_db=redis_db,
    )
    if p.texto and not resultado.get('items'):
        # Igual que con Elasticsearch: sin coincidencias se muestran populares.
        sin_coincidencias = True
        resultado = catalog_service.listar_productos(
            mongo, mysql_db, page=p.page, page_size=p.page_size, orden='mas_vendidos',
            vendedor_id=p.vendedor_id, redis_db=redis_db,
        )
    filtro = {'estado': 'activo'}
    if p.texto and not sin_coincidencias:
        patron = re.escape(p.texto)
        filtro['$or'] = [
            {'nombre': {'$regex': patron, '$options': 'i'}},
            {'sku': {'$regex': patron, '$options': 'i'}},
        ]
    try:
        conteos = list(mongo.productos.aggregate([
            {'$match': filtro},
            {'$project': {'cats': {'$ifNull': ['$categorias', ['$categoria']]}}},
            {'$unwind': '$cats'},
            {'$group': {'_id': '$cats.slug', 'conteo': {'$sum': 1}}},
            {'$sort': {'conteo': -1}},
        ])) if salud.disponible('mongo') else []
    except catalogo_respaldo.ERRORES_MONGO as exc:
        # Sin MongoDB los productos vienen de su copia; solo se pierden estos conteos.
        salud.registrar_falla('mongo', exc)
        conteos = []
    etiquetas = _etiquetas_categorias(mysql_db)
    resultado.pop('dual_read', None)
    resultado.update({
        'orden': p.orden_efectivo,
        'facetas': {
            'categorias': [
                {'valor': c['_id'], 'etiqueta': etiquetas.get(c['_id'], c['_id']),
                 'conteo': c['conteo'], 'seleccionado': c['_id'] == p.categoria}
                for c in conteos if c['_id']
            ],
            'vendedores': [], 'atributos': [],
            'precio': {'min': None, 'max': None, 'rangos': []},
            'disponibilidad': None,
        },
        'sugerencia': None,
        'degradado': True,
        # Si MongoDB tampoco respondió, los productos salieron de su copia en MySQL.
        'motor': 'mysql' if resultado.get('catalogo_respaldo') else 'mongodb',
        'tiempo_ms': None,
        'sin_coincidencias': sin_coincidencias,
        **({'consulta': p.texto, 'alternativa': 'populares'} if sin_coincidencias else {}),
    })
    return resultado


# ── Autocompletado ────────────────────────────────────────────────────────────

def _sugerir_sin_elasticsearch(mongo: Database, texto: str, limite: int) -> tuple[list[dict], str]:
    """Respaldo del autocompletado: Redis (prefijos), luego MongoDB y luego la copia en MySQL."""
    if salud.disponible('redis'):
        try:
            from app.core.db_redis import get_redis
            from app.services import autocompletado_respaldo_service as autocompletado
            r = get_redis()
            if autocompletado.disponible(r):
                productos = autocompletado.sugerir(r, texto, limite)
                salud.registrar_exito('redis')
                return productos, 'redis'
        except redis_lib.RedisError as exc:
            salud.registrar_falla('redis', exc, confirmada=isinstance(exc, redis_lib.ConnectionError))
    filtro = {'estado': 'activo', 'nombre': {'$regex': re.escape(texto), '$options': 'i'}}
    docs, desde_respaldo = catalogo_respaldo.productos(
        mongo, filtro, estado='activo', categoria_slug=None, q=texto,
    )
    productos = [
        {'producto_id': str(d['_id']), 'nombre': d.get('nombre'),
         'imagen': (d.get('imagenes') or [None])[0], 'precio': None}
        for d in docs[:limite]
    ]
    return productos, 'mysql' if desde_respaldo else 'mongodb'


def sugerir(es: Elasticsearch, mysql_db: Session, mongo: Database, q: str, limite: int = 6) -> dict:
    texto = (q or '').strip()
    categorias = [
        {'slug': slug, 'nombre': nombre}
        for slug, nombre in _etiquetas_categorias(mysql_db).items()
        if texto and normalizar(nombre).startswith(normalizar(texto))
    ][:3]
    try:
        respuesta = _consultar(
            es,
            suggest={'productos': {
                'prefix': texto,
                'completion': {
                    'field': 'sugerencia',
                    'size': limite * 2,
                    'skip_duplicates': True,
                    'fuzzy': {'fuzziness': 'AUTO', 'prefix_length': 1, 'min_length': 4},
                },
            }},
            source=['producto_id', 'nombre', 'imagen', 'precio', 'categorias'],
        )
    except ERRORES_MOTOR as exc:
        logger.warning('Autocompletado sin Elasticsearch: %s', exc)
        productos, motor = _sugerir_sin_elasticsearch(mongo, texto, limite)
        return {'productos': productos, 'categorias': categorias, 'degradado': True, 'motor': motor}

    productos, vistos = [], set()
    for opcion in respuesta['suggest']['productos'][0]['options']:
        fuente = opcion['_source']
        if fuente['producto_id'] in vistos:
            continue
        vistos.add(fuente['producto_id'])
        productos.append({
            'producto_id': fuente['producto_id'],
            'nombre': fuente['nombre'],
            'imagen': fuente.get('imagen'),
            'precio': fuente.get('precio'),
            'coincidencia': opcion['text'],
        })
        if len(productos) == limite:
            break
    return {'productos': productos, 'categorias': categorias, 'degradado': False, 'motor': 'elasticsearch'}
