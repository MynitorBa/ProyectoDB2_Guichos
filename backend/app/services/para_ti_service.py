"""«Te podría interesar» en el inicio: recomendaciones por vectores (Entrega 4).

Semillas: lo que el usuario tiene en el carrito y lo último que vio. Con
sesión, los vistos se guardan en Redis (``vistos:{usuario_id}``, los últimos
20, 30 días) y sirven en cualquier dispositivo; sin sesión, el navegador manda
los suyos. El carrito se lee sin renovar su TTL: mirar recomendaciones no es
actividad sobre el carrito.

Consulta: una cláusula kNN por semilla en la misma búsqueda, con su peso
(carrito 2, vistos 1 → 0.8 → 0.64… por antigüedad). Elasticsearch suma los
puntajes: cada interés aporta sus vecinos y lo que se parece a varios sube.
Se prefirió a promediar los vectores porque el promedio de una laptop y unos
audífonos cae «en medio» y no se parece a ninguno de los dos.

Escala: el resultado se guarda 10 minutos por combinación de semillas
(``para_ti:{huella}``); los vectores de las semillas ya están en el índice, así
que no se llama al servicio de embeddings.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re

import redis
from elastic_transport import TransportError
from elasticsearch import ApiError, Elasticsearch
from pymongo.database import Database
from sqlalchemy.orm import Session

from app.core import salud
from app.core.config import settings
from app.services import catalog_service, catalogo_respaldo_service

logger = logging.getLogger(__name__)

MAX_VISTOS = 20
VISTOS_TTL = 30 * 24 * 3600
MAX_SEMILLAS = 5
PESO_CARRITO = 2.0
DECAIMIENTO_VISTOS = 0.8
CACHE_SEGUNDOS = 600
CANDIDATOS_KNN = 50
_REF_VALIDA = re.compile(r'^[0-9a-f]{24}$')


def _clave_vistos(usuario_id: int) -> str:
    return f'vistos:{usuario_id}'


def refs_validas(refs) -> list[str]:
    """Solo identificadores de producto bien formados, sin repetir, en orden."""
    vistos = []
    for ref in refs or []:
        ref = (ref or '').strip().lower()
        if _REF_VALIDA.match(ref) and ref not in vistos:
            vistos.append(ref)
    return vistos


def registrar_visto(redis_db, usuario_id: int, producto_ref: str) -> bool:
    """Pone el producto al frente del historial del usuario. Falla en silencio sin Redis."""
    if not refs_validas([producto_ref]) or not salud.disponible('redis'):
        return False
    clave = _clave_vistos(usuario_id)
    try:
        pipe = redis_db.pipeline()
        pipe.lrem(clave, 0, producto_ref)
        pipe.lpush(clave, producto_ref)
        pipe.ltrim(clave, 0, MAX_VISTOS - 1)
        pipe.expire(clave, VISTOS_TTL)
        pipe.execute()
    except redis.RedisError as exc:
        salud.registrar_falla('redis', exc)
        return False
    return True


def _desde_redis(redis_db, usuario_id: int) -> tuple[list[str], list[str]]:
    """Vistos y productos del carrito del usuario (sin tocar el TTL del carrito)."""
    if redis_db is None or not salud.disponible('redis'):
        return [], []
    try:
        pipe = redis_db.pipeline()
        pipe.lrange(_clave_vistos(usuario_id), 0, MAX_VISTOS - 1)
        pipe.hvals(f'carrito:{usuario_id}')
        vistos, lineas = pipe.execute()
    except redis.RedisError as exc:
        salud.registrar_falla('redis', exc)
        return [], []
    carrito = [json.loads(linea).get('producto_ref') for linea in lineas]
    return refs_validas(vistos), refs_validas(carrito)


def semillas(vistos: list[str], carrito: list[str]) -> list[tuple[str, float]]:
    """Las semillas con su peso: primero el carrito, después lo visto más reciente."""
    pesos: dict[str, float] = {ref: PESO_CARRITO for ref in carrito}
    peso = 1.0
    for ref in vistos:
        if ref not in pesos:
            pesos[ref] = peso
            peso *= DECAIMIENTO_VISTOS
    return sorted(pesos.items(), key=lambda par: -par[1])[:MAX_SEMILLAS]


def _vecinos(es: Elasticsearch, elegidas: list[tuple[str, float]], excluir: list[str], cantidad: int) -> list[str] | None:
    """Productos activos cercanos a las semillas, sin las excluidas. ``None`` si ES falla."""
    if not salud.disponible('elasticsearch'):
        return None
    try:
        docs = es.mget(index=settings.ES_INDEX_ALIAS, ids=[ref for ref, _ in elegidas], source=['vector'])['docs']
        vectores = {d['_id']: d['_source']['vector'] for d in docs if d.get('found') and d['_source'].get('vector')}
        if not vectores:
            return []
        filtro = {'bool': {
            'filter': [{'term': {'estado': 'activo'}}],
            'must_not': [{'ids': {'values': excluir}}],
        }}
        respuesta = es.search(
            index=settings.ES_INDEX_ALIAS, size=cantidad, source=False,
            knn=[{
                'field': 'vector', 'query_vector': vectores[ref], 'k': cantidad,
                'num_candidates': CANDIDATOS_KNN, 'filter': filtro, 'boost': peso,
            } for ref, peso in elegidas if ref in vectores],
        )
    except (TransportError, ApiError) as exc:
        if isinstance(exc, TransportError):
            salud.registrar_falla('elasticsearch', exc)
        logger.warning('No se pudieron calcular las recomendaciones del inicio: %s', exc)
        return None
    salud.registrar_exito('elasticsearch')
    return [hit['_id'] for hit in respuesta['hits']['hits']]


def recomendar(
    mysql: Session, mongo: Database, es: Elasticsearch, redis_db, *,
    usuario_id: int | None = None, vistos_cliente: list[str] | None = None, limite: int = 8,
) -> dict:
    """``{items, origen, semillas}``; ``origen`` es 'vectores' o None (no hay con qué recomendar)."""
    vistos, carrito = _desde_redis(redis_db, usuario_id) if usuario_id else ([], [])
    vistos += [ref for ref in refs_validas(vistos_cliente)[:MAX_VISTOS] if ref not in vistos]
    elegidas = semillas(vistos, carrito)
    if not elegidas:
        return {'items': [], 'origen': None, 'semillas': 0}
    # Ni lo que ya está en el carrito ni lo que acaba de ver.
    excluir = list(dict.fromkeys(carrito + vistos))
    clave = 'para_ti:' + hashlib.sha1(json.dumps([elegidas, excluir, limite]).encode()).hexdigest()

    refs = None
    if redis_db is not None and salud.disponible('redis'):
        try:
            guardado = redis_db.get(clave)
            refs = json.loads(guardado) if guardado else None
        except redis.RedisError as exc:
            salud.registrar_falla('redis', exc)
    if refs is None:
        refs = _vecinos(es, elegidas, excluir, limite * 2)
        if refs is None:
            return {'items': [], 'origen': None, 'semillas': len(elegidas)}
        if redis_db is not None and salud.disponible('redis'):
            try:
                redis_db.set(clave, json.dumps(refs), ex=CACHE_SEGUNDOS)
            except redis.RedisError as exc:
                salud.registrar_falla('redis', exc)

    # Precio, stock y disponibilidad siempre de MySQL.
    docs, _ = catalogo_respaldo_service.productos_por_ids(mongo, refs)
    items, _ = catalog_service.enriquecer_productos([docs[r] for r in refs if r in docs], mysql, redis_db)
    items = [item for item in items if item.get('disponible')][:limite]
    return {'items': items, 'origen': 'vectores' if items else None, 'semillas': len(elegidas)}
