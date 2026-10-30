"""«También te podría interesar»: productos parecidos por significado (Entrega 4).

Usa el vector que cada producto ya tiene en el índice de búsqueda (mapping v2)
y una búsqueda kNN en Elasticsearch. No necesita el servicio de embeddings al
consultar: el vector del producto se calculó al indexarlo.

Complementa a las recomendaciones por compras (Neo4j): aquellas sugieren
*complementos* («quien compró la laptop compró un mouse»); estas sugieren
*alternativas* («otras laptops parecidas») y funcionan también con productos
que nadie ha comprado. Por eso se excluyen los productos que ya aparecen en la
sección de compras, para no mostrar lo mismo dos veces.

Escala: los vecinos de un producto solo cambian cuando cambia el catálogo, no
con cada visita. Se guardan en Redis una hora (``similares:{producto}``); el
tráfico de la página pega en esa caché y no en el índice vectorial.

Respaldo: si Elasticsearch no responde o el producto aún no tiene vector, se
muestran los más vendidos de su categoría (``origen: mas_vendidos``).
"""

from __future__ import annotations

import json
import logging

import redis
from elastic_transport import TransportError
from elasticsearch import ApiError, Elasticsearch, NotFoundError
from pymongo.database import Database
from sqlalchemy.orm import Session

from app.core import salud
from app.core.config import settings
from app.services import catalog_service, recommendation_service

logger = logging.getLogger(__name__)

CACHE_SEGUNDOS = 3600
VECINOS_GUARDADOS = 24
CANDIDATOS_KNN = 100


def _clave(producto_ref: str) -> str:
    return f'similares:{producto_ref}'


def vecinos(es: Elasticsearch, producto_ref: str, *, cantidad: int = VECINOS_GUARDADOS) -> list[dict] | None:
    """Los productos activos más cercanos por vector: ``[{producto_ref, similitud}]``.

    ``None`` si el producto no tiene vector o Elasticsearch no responde.
    """
    if not salud.disponible('elasticsearch'):
        return None
    try:
        fuente = es.get(index=settings.ES_INDEX_ALIAS, id=producto_ref, source=['vector'])['_source']
        if not fuente.get('vector'):
            return None
        respuesta = es.search(
            index=settings.ES_INDEX_ALIAS, size=cantidad, source=False,
            knn={
                'field': 'vector', 'query_vector': fuente['vector'],
                'k': cantidad, 'num_candidates': CANDIDATOS_KNN,
                'filter': {'bool': {
                    'filter': [{'term': {'estado': 'activo'}}],
                    'must_not': [{'ids': {'values': [producto_ref]}}],
                }},
            },
        )
    except NotFoundError:
        return None
    except (TransportError, ApiError) as exc:
        if isinstance(exc, TransportError):
            salud.registrar_falla('elasticsearch', exc)
        logger.warning('No se pudieron calcular los productos similares de %s: %s', producto_ref, exc)
        return None
    salud.registrar_exito('elasticsearch')
    return [{'producto_ref': h['_id'], 'similitud': round(h['_score'], 4)} for h in respuesta['hits']['hits']]


def vecinos_con_cache(es: Elasticsearch, redis_db, producto_ref: str) -> list[dict] | None:
    """``vecinos`` pasando por la caché de Redis (una hora). Sin Redis, consulta directo."""
    if redis_db is not None and salud.disponible('redis'):
        try:
            guardado = redis_db.get(_clave(producto_ref))
            if guardado:
                return json.loads(guardado)
        except redis.RedisError as exc:
            salud.registrar_falla('redis', exc)
            redis_db = None
    resultado = vecinos(es, producto_ref)
    if resultado is not None and redis_db is not None:
        try:
            redis_db.set(_clave(producto_ref), json.dumps(resultado), ex=CACHE_SEGUNDOS)
        except redis.RedisError as exc:
            salud.registrar_falla('redis', exc)
    return resultado


def similares(
    mysql: Session, mongo: Database, es: Elasticsearch, redis_db, *,
    producto_ref: str, excluir: list[str] | None = None, limite: int = 8,
) -> tuple[list[dict], str | None]:
    """Productos comprables parecidos al dado y el origen: 'vectores' o 'mas_vendidos'."""
    excluidos = set(excluir or []) | {producto_ref}
    candidatos = vecinos_con_cache(es, redis_db, producto_ref)
    origen = 'vectores'
    if candidatos is None:
        permitidos = recommendation_service.refs_misma_categoria(mongo, producto_ref)
        candidatos = recommendation_service._mas_vendidos(mysql, permitidos) if permitidos else []
        origen = 'mas_vendidos'

    resultado = []
    for candidato in candidatos:
        if candidato['producto_ref'] in excluidos:
            continue
        producto = catalog_service.obtener_producto(mongo, candidato['producto_ref'], mysql)
        if not producto or not producto.get('disponible'):
            continue
        if 'similitud' in candidato:
            producto['similitud'] = candidato['similitud']
        resultado.append(producto)
        if len(resultado) >= limite:
            break
    return resultado, origen if resultado else None
