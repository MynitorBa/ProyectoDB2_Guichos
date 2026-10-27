"""Autocompletado de respaldo en Redis (plan B de Elasticsearch).

Cuando Elasticsearch no responde, el buscador del encabezado sigue sugiriendo
productos a partir de un índice de prefijos en Redis:

- ``autocompletar:productos`` (ZSET, todos con puntaje 0): cada miembro es
  ``«texto normalizado»\\t«producto_id»``. Con puntajes iguales Redis ordena
  los miembros alfabéticamente, así que ``ZRANGEBYLEX`` encuentra en O(log n)
  todo lo que empieza con lo escrito.
- ``autocompletar:datos`` (HASH): producto_id → nombre, imagen y las claves
  del ZSET de ese producto (para retirarlas al editarlo).

Como el campo ``sugerencia`` de Elasticsearch, cada producto se indexa con su
nombre completo y sus sufijos desde cada palabra («galax» → Samsung Galaxy).
El índice se reconstruye desde la copia del catálogo en MySQL al arrancar y
cada 10 minutos, y se actualiza producto por producto con el outbox.
"""

from __future__ import annotations

import json
import logging
import unicodedata

import redis

logger = logging.getLogger(__name__)

CLAVE_INDICE = 'autocompletar:productos'
CLAVE_DATOS = 'autocompletar:datos'
_SEP = '\t'


def _normalizar(texto: str) -> str:
    # Igual que search_service.normalizar: sin tildes y en minúsculas.
    sin_tildes = unicodedata.normalize('NFKD', texto or '')
    return ''.join(c for c in sin_tildes if not unicodedata.combining(c)).lower().strip()


def _entradas(nombre: str) -> list[str]:
    """El nombre normalizado y sus sufijos desde cada palabra de 3+ letras."""
    palabras = _normalizar(nombre).split()
    entradas = [' '.join(palabras)] if palabras else []
    for i in range(1, len(palabras)):
        if len(palabras[i]) >= 3 and any(c.isalpha() for c in palabras[i]):
            entradas.append(' '.join(palabras[i:]))
    return entradas


def _miembros(doc: dict) -> tuple[str, list[str], str]:
    producto_id = str(doc['_id'])
    claves = [f'{entrada}{_SEP}{producto_id}' for entrada in _entradas(doc.get('nombre') or '')]
    imagenes = doc.get('imagenes') or []
    datos = json.dumps({
        'nombre': doc.get('nombre'),
        'imagen': imagenes[0] if imagenes else None,
        'claves': claves,
    })
    return producto_id, claves, datos


def actualizar(r: redis.Redis, producto_id: str, doc: dict | None) -> None:
    """Refleja un producto: lo indexa si está activo y lo retira si no."""
    anterior = r.hget(CLAVE_DATOS, producto_id)
    with r.pipeline(transaction=True) as pipe:
        if anterior:
            viejas = json.loads(anterior).get('claves') or []
            if viejas:
                pipe.zrem(CLAVE_INDICE, *viejas)
            pipe.hdel(CLAVE_DATOS, producto_id)
        if doc and doc.get('estado') == 'activo':
            _, claves, datos = _miembros(doc)
            if claves:
                pipe.zadd(CLAVE_INDICE, {clave: 0 for clave in claves})
            pipe.hset(CLAVE_DATOS, producto_id, datos)
        pipe.execute()


def reconstruir(r: redis.Redis, docs: list[dict]) -> int:
    """Rehace el índice completo con los productos activos.

    Se arma en claves temporales y se renombra: quien busca nunca ve el índice
    a medio llenar.
    """
    temporal_indice, temporal_datos = f'{CLAVE_INDICE}:nuevo', f'{CLAVE_DATOS}:nuevo'
    activos = [doc for doc in docs if doc.get('estado') == 'activo']
    with r.pipeline(transaction=False) as pipe:
        pipe.delete(temporal_indice, temporal_datos)
        for doc in activos:
            producto_id, claves, datos = _miembros(doc)
            if claves:
                pipe.zadd(temporal_indice, {clave: 0 for clave in claves})
            pipe.hset(temporal_datos, producto_id, datos)
        pipe.execute()
    with r.pipeline(transaction=True) as pipe:
        if activos:
            pipe.rename(temporal_indice, CLAVE_INDICE)
            pipe.rename(temporal_datos, CLAVE_DATOS)
        else:
            pipe.delete(CLAVE_INDICE, CLAVE_DATOS)
        pipe.execute()
    return len(activos)


def disponible(r: redis.Redis) -> bool:
    """True si el índice existe (ya se construyó al menos una vez)."""
    return bool(r.exists(CLAVE_INDICE))


def sugerir(r: redis.Redis, texto: str, limite: int = 6) -> list[dict]:
    """Productos cuyo nombre (o una palabra de él) empieza con ``texto``."""
    prefijo = _normalizar(texto)
    if not prefijo:
        return []
    # El máximo del rango es el prefijo seguido del carácter más alto de Unicode.
    miembros = r.zrangebylex(CLAVE_INDICE, f'[{prefijo}', f'[{prefijo}\U0010ffff', start=0, num=limite * 5)
    ids, vistos = [], set()
    for miembro in miembros:
        producto_id = miembro.rsplit(_SEP, 1)[1]
        if producto_id not in vistos:
            vistos.add(producto_id)
            ids.append(producto_id)
        if len(ids) == limite:
            break
    if not ids:
        return []
    datos = r.hmget(CLAVE_DATOS, ids)
    resultado = []
    for producto_id, crudo in zip(ids, datos):
        if crudo:
            info = json.loads(crudo)
            resultado.append({
                'producto_id': producto_id, 'nombre': info['nombre'],
                'imagen': info.get('imagen'), 'precio': None,
            })
    return resultado
