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

# Las escrituras usan Lua para que leer, modificar y renovar el TTL sean una
# sola operación atómica dentro de Redis. Esto evita perder incrementos cuando
# dos solicitudes agregan la misma oferta al mismo tiempo.
_ADD_ITEM_LUA = """
local current = redis.call('HGET', KEYS[1], ARGV[1])
local data
if current then
  data = cjson.decode(current)
  data['cantidad'] = tonumber(data['cantidad']) + tonumber(ARGV[2])
else
  data = {
    cantidad = tonumber(ARGV[2]),
    precio_al_agregar = ARGV[3],
    producto_ref = ARGV[4] ~= '' and ARGV[4] or cjson.null
  }
end
redis.call('HSET', KEYS[1], ARGV[1], cjson.encode(data))
redis.call('EXPIRE', KEYS[1], tonumber(ARGV[5]))
return tonumber(data['cantidad'])
"""

_UPDATE_QUANTITY_LUA = """
local current = redis.call('HGET', KEYS[1], ARGV[1])
if not current then return 0 end
local data = cjson.decode(current)
data['cantidad'] = tonumber(ARGV[2])
redis.call('HSET', KEYS[1], ARGV[1], cjson.encode(data))
redis.call('EXPIRE', KEYS[1], tonumber(ARGV[3]))
return 1
"""

_DELETE_ITEM_LUA = """
local removed = redis.call('HDEL', KEYS[1], ARGV[1])
if removed == 1 and redis.call('EXISTS', KEYS[1]) == 1 then
  redis.call('EXPIRE', KEYS[1], tonumber(ARGV[2]))
end
return removed
"""

_GET_CART_LUA = """
local values = redis.call('HGETALL', KEYS[1])
if #values > 0 then redis.call('EXPIRE', KEYS[1], tonumber(ARGV[1])) end
return values
"""

_SET_FLASH_ITEM_LUA = """
redis.call('HSET', KEYS[1], ARGV[1], ARGV[2])
redis.call('EXPIRE', KEYS[1], tonumber(ARGV[3]))
return 1
"""


def _key(usuario_id: int) -> str:
    return f"carrito:{usuario_id}"


# ── Lectura ──────────────────────────────────────────────────────────────────


def obtener_carrito(r: redis.Redis, usuario_id: int) -> list[dict]:
    """Devuelve los ítems del carrito y renueva el TTL."""
    k = _key(usuario_id)
    flat = r.eval(_GET_CART_LUA, 1, k, _TTL)
    raw = dict(zip(flat[0::2], flat[1::2]))
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
) -> int:
    """Acumula cantidad si el ítem ya existe; lo crea si no. Renueva TTL."""
    return int(r.eval(
        _ADD_ITEM_LUA,
        1,
        _key(usuario_id),
        str(oferta_id),
        cantidad,
        str(precio_al_agregar),
        producto_ref or '',
        _TTL,
    ))


def establecer_item_flash(
    r: redis.Redis,
    usuario_id: int,
    oferta_id: int,
    cantidad: int,
    precio_promocional: Decimal,
    producto_ref: str,
    promocion_id: int,
    reserva_token: str,
) -> None:
    """Coloca la reserva flash como la única selección de esa oferta."""
    datos = json.dumps({
        'cantidad': cantidad,
        'precio_al_agregar': str(precio_promocional),
        'producto_ref': producto_ref,
        'promocion_flash_id': promocion_id,
        'reserva_flash_token': reserva_token,
    })
    r.eval(
        _SET_FLASH_ITEM_LUA, 1, _key(usuario_id), str(oferta_id), datos, _TTL
    )


def actualizar_cantidad(
    r: redis.Redis,
    usuario_id: int,
    oferta_id: int,
    nueva_cantidad: int,
) -> bool:
    """Actualiza la cantidad de un ítem. Retorna False si el ítem no existe."""
    return bool(r.eval(
        _UPDATE_QUANTITY_LUA,
        1,
        _key(usuario_id),
        str(oferta_id),
        nueva_cantidad,
        _TTL,
    ))


def eliminar_item(r: redis.Redis, usuario_id: int, oferta_id: int) -> bool:
    """Elimina un ítem del carrito. Retorna False si no existía."""
    return bool(r.eval(
        _DELETE_ITEM_LUA,
        1,
        _key(usuario_id),
        str(oferta_id),
        _TTL,
    ))


def vaciar_carrito(r: redis.Redis, usuario_id: int) -> None:
    """Elimina toda la clave del carrito (p. ej. después del checkout)."""
    r.delete(_key(usuario_id))


# ── TTL ───────────────────────────────────────────────────────────────────────


def ttl_restante(r: redis.Redis, usuario_id: int) -> int:
    """Segundos restantes antes de que expire el carrito. -2 si no existe."""
    return r.ttl(_key(usuario_id))
