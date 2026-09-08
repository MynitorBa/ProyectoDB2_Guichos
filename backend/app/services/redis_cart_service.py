"""
Carrito de compras persistido en Redis.

Estructura de claves:
  carrito:{usuario_id}  →  HASH
    campo: "{oferta_id}"
    valor: JSON  { "cantidad": int, "precio_al_agregar": str, "producto_ref": str | null }

El TTL se renueva con cada operación de lectura/escritura (ventana deslizante).
Cuando el usuario no interactúa durante REDIS_CART_TTL segundos, Redis elimina la
clave automáticamente → carrito "expirado por inactividad".
"""

import json
from decimal import Decimal

import redis

from app.core.config import settings

_TTL = settings.REDIS_CART_TTL  # segundos


def _key(usuario_id: int) -> str:
    return f"carrito:{usuario_id}"


# ── Lectura ──────────────────────────────────────────────────────────────────


def obtener_carrito(r: redis.Redis, usuario_id: int) -> list[dict]:
    """Devuelve los ítems del carrito y renueva el TTL."""
    k = _key(usuario_id)
    raw = r.hgetall(k)
    if raw:
        r.expire(k, _TTL)
    return [{"oferta_id": int(oid), **json.loads(v)} for oid, v in raw.items()]


def carrito_existe(r: redis.Redis, usuario_id: int) -> bool:
    return r.exists(_key(usuario_id)) == 1


# ── Escritura ─────────────────────────────────────────────────────────────────


def agregar_item(
    r: redis.Redis,
    usuario_id: int,
    oferta_id: int,
    cantidad: int,
    precio_al_agregar: Decimal,
    producto_ref: str | None,
) -> None:
    """Acumula cantidad si el ítem ya existe; lo crea si no. Renueva TTL."""
    k = _key(usuario_id)
    campo = str(oferta_id)

    existente = r.hget(k, campo)
    if existente:
        datos = json.loads(existente)
        datos["cantidad"] += cantidad
    else:
        datos = {
            "cantidad": cantidad,
            "precio_al_agregar": str(precio_al_agregar),
            "producto_ref": producto_ref,
        }

    r.hset(k, campo, json.dumps(datos))
    r.expire(k, _TTL)


def actualizar_cantidad(
    r: redis.Redis,
    usuario_id: int,
    oferta_id: int,
    nueva_cantidad: int,
) -> bool:
    """Actualiza la cantidad de un ítem. Retorna False si el ítem no existe."""
    k = _key(usuario_id)
    campo = str(oferta_id)
    existente = r.hget(k, campo)
    if not existente:
        return False
    datos = json.loads(existente)
    datos["cantidad"] = nueva_cantidad
    r.hset(k, campo, json.dumps(datos))
    r.expire(k, _TTL)
    return True


def eliminar_item(r: redis.Redis, usuario_id: int, oferta_id: int) -> bool:
    """Elimina un ítem del carrito. Retorna False si no existía."""
    k = _key(usuario_id)
    eliminados = r.hdel(k, str(oferta_id))
    if eliminados and r.exists(k):
        r.expire(k, _TTL)
    return eliminados > 0


def vaciar_carrito(r: redis.Redis, usuario_id: int) -> None:
    """Elimina toda la clave del carrito (p. ej. después del checkout)."""
    r.delete(_key(usuario_id))


# ── TTL ───────────────────────────────────────────────────────────────────────


def ttl_restante(r: redis.Redis, usuario_id: int) -> int:
    """Segundos restantes antes de que expire el carrito. -2 si no existe."""
    return r.ttl(_key(usuario_id))
