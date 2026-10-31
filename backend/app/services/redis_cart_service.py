"""
Carrito de compras persistido en Redis.

Estructura de claves:
  carrito:{usuario_id}  →  HASH
    campo: "{oferta_id}"
    valor: JSON  { "cantidad": int, "precio_al_agregar": str, "producto_ref": str | null }

El TTL se renueva con cada operación de lectura/escritura (ventana deslizante).
Cuando el usuario no interactúa durante REDIS_CART_TTL segundos, Redis elimina la
clave automáticamente → carrito "expirado por inactividad".

Plan B: cada cambio exitoso se copia en MySQL (carrito_respaldo_service). Si
Redis no responde, o su circuito está abierto (core/salud.py), la misma
operación se hace sobre la copia de MySQL y el carrito queda marcado como
pendiente; cuando Redis vuelve, se reconstruye desde MySQL antes de la
siguiente operación. Solo si ambos fallan se lanza ``CarritoNoDisponible``,
que es un error de Redis para que los llamadores respondan 503 como antes.
"""

import json
import logging
from decimal import Decimal

import redis
from sqlalchemy.exc import SQLAlchemyError

from app.core import salud
from app.core.config import settings
from app.core.fault_injection import punto_de_falla
from app.services import carrito_respaldo_service as respaldo

logger = logging.getLogger(__name__)

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


class CarritoNoDisponible(redis.exceptions.ConnectionError):
    """Ni Redis ni su respaldo en MySQL respondieron."""


def _key(usuario_id: int) -> str:
    return f"carrito:{usuario_id}"


def _como_items(crudo: dict) -> list[dict]:
    return [{"oferta_id": int(oid), **json.loads(v)} for oid, v in crudo.items()]


def _resincronizar(r: redis.Redis, usuario_id: int) -> None:
    """Si el carrito cambió solo en MySQL mientras Redis no respondía, lo trae de vuelta."""
    if not salud.disponible('mysql'):
        return  # sin MySQL no hay copia que revisar; no se espera su timeout
    try:
        pendiente = respaldo.pendiente(usuario_id)
    except SQLAlchemyError as exc:
        logger.warning('No se pudo revisar el respaldo del carrito %s: %s', usuario_id, exc)
        return
    if pendiente is None:
        return
    k = _key(usuario_id)
    with r.pipeline(transaction=True) as pipe:
        pipe.delete(k)
        if pendiente['items']:
            pipe.hset(k, mapping={str(oid): datos for oid, datos in pendiente['items'].items()})
            pipe.expire(k, pendiente['ttl'])
        pipe.execute()
    respaldo.marcar_sincronizado(usuario_id)
    logger.info('Carrito %s reconstruido en Redis desde su respaldo en MySQL.', usuario_id)


def _espejar(r: redis.Redis, usuario_id: int) -> None:
    """Copia a MySQL el estado que acaba de quedar en Redis. Nunca falla la operación.

    Si fallara aquí y se reintentara en el respaldo, el cambio se aplicaría dos
    veces; por eso cualquier error solo se registra.
    """
    if not salud.disponible('mysql'):
        return  # la copia se pone al día con la siguiente escritura
    k = _key(usuario_id)

    def leer_redis():
        return {int(oid): v for oid, v in r.hgetall(k).items()}, r.ttl(k)

    try:
        respaldo.espejar(usuario_id, leer_redis)
    except (redis.RedisError, SQLAlchemyError) as exc:
        logger.warning('No se pudo copiar el carrito %s a MySQL: %s', usuario_id, exc)


def _ejecutar(en_redis, en_respaldo):
    """Intenta Redis (si su circuito está cerrado) y, si no, el respaldo en MySQL."""
    if salud.disponible('redis'):
        try:
            resultado = en_redis()
            salud.registrar_exito('redis')
            return resultado
        except redis.RedisError as exc:
            # Sin conexión el circuito se abre de una vez: las siguientes operaciones
            # van directo a MySQL en lugar de esperar el timeout.
            salud.registrar_falla('redis', exc, confirmada=isinstance(exc, (redis.ConnectionError, redis.TimeoutError)))
            logger.warning('Redis no respondió; el carrito usa su respaldo en MySQL: %s', exc)
    try:
        return en_respaldo()
    except SQLAlchemyError as exc:
        raise CarritoNoDisponible('Ni Redis ni el respaldo del carrito están disponibles.') from exc


def en_respaldo() -> bool:
    """True si el carrito está funcionando sobre MySQL en este momento."""
    return salud.degradado('redis')


# ── Lectura ──────────────────────────────────────────────────────────────────


def obtener_carrito(r: redis.Redis, usuario_id: int, *, punto_falla: str | None = None) -> list[dict]:
    """Devuelve los ítems del carrito y renueva el TTL.

    ``punto_falla`` identifica al llamador para el laboratorio de fallas (el
    checkout simula que Redis cae justo en su lectura, no en cualquier otra).
    """
    def en_redis():
        if punto_falla:
            punto_de_falla(punto_falla)
        _resincronizar(r, usuario_id)
        flat = r.eval(_GET_CART_LUA, 1, _key(usuario_id), _TTL)
        return _como_items(dict(zip(flat[0::2], flat[1::2])))

    return _ejecutar(en_redis, lambda: _como_items(respaldo.leer(usuario_id)))


def carrito_existe(r: redis.Redis, usuario_id: int) -> bool:
    return bool(obtener_carrito(r, usuario_id))


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
    def en_redis():
        punto_de_falla('carrito.redis_agregar')
        _resincronizar(r, usuario_id)
        total = int(r.eval(
            _ADD_ITEM_LUA,
            1,
            _key(usuario_id),
            str(oferta_id),
            cantidad,
            str(precio_al_agregar),
            producto_ref or '',
            _TTL,
        ))
        _espejar(r, usuario_id)
        return total

    def cambio(items):
        datos = json.loads(items[oferta_id]) if oferta_id in items else {
            'cantidad': 0, 'precio_al_agregar': str(precio_al_agregar), 'producto_ref': producto_ref or None,
        }
        datos['cantidad'] = int(datos['cantidad']) + cantidad
        items[oferta_id] = json.dumps(datos)
        return datos['cantidad']

    return _ejecutar(en_redis, lambda: respaldo.modificar(usuario_id, cambio))


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

    def en_redis():
        _resincronizar(r, usuario_id)
        r.eval(_SET_FLASH_ITEM_LUA, 1, _key(usuario_id), str(oferta_id), datos, _TTL)
        _espejar(r, usuario_id)

    def cambio(items):
        items[oferta_id] = datos

    _ejecutar(en_redis, lambda: respaldo.modificar(usuario_id, cambio))


def actualizar_cantidad(
    r: redis.Redis,
    usuario_id: int,
    oferta_id: int,
    nueva_cantidad: int,
) -> bool:
    """Actualiza la cantidad de un ítem. Retorna False si el ítem no existe."""
    def en_redis():
        _resincronizar(r, usuario_id)
        ok = bool(r.eval(
            _UPDATE_QUANTITY_LUA,
            1,
            _key(usuario_id),
            str(oferta_id),
            nueva_cantidad,
            _TTL,
        ))
        if ok:
            _espejar(r, usuario_id)
        return ok

    def cambio(items):
        if oferta_id not in items:
            return False
        datos = json.loads(items[oferta_id])
        datos['cantidad'] = nueva_cantidad
        items[oferta_id] = json.dumps(datos)
        return True

    return _ejecutar(en_redis, lambda: respaldo.modificar(usuario_id, cambio))


def eliminar_item(r: redis.Redis, usuario_id: int, oferta_id: int) -> bool:
    """Elimina un ítem del carrito. Retorna False si no existía."""
    def en_redis():
        _resincronizar(r, usuario_id)
        ok = bool(r.eval(
            _DELETE_ITEM_LUA,
            1,
            _key(usuario_id),
            str(oferta_id),
            _TTL,
        ))
        _espejar(r, usuario_id)
        return ok

    def cambio(items):
        return items.pop(oferta_id, None) is not None

    return _ejecutar(en_redis, lambda: respaldo.modificar(usuario_id, cambio))


def vaciar_carrito(r: redis.Redis, usuario_id: int, *, punto_falla: str | None = None) -> None:
    """Elimina toda la clave del carrito (p. ej. después del checkout)."""
    def en_redis():
        if punto_falla:
            punto_de_falla(punto_falla)
        r.delete(_key(usuario_id))
        try:
            respaldo.vaciar(usuario_id, pendiente=False)
        except SQLAlchemyError as exc:
            logger.warning('No se pudo vaciar el respaldo del carrito %s: %s', usuario_id, exc)

    _ejecutar(en_redis, lambda: respaldo.vaciar(usuario_id, pendiente=True))


# ── TTL ───────────────────────────────────────────────────────────────────────


def ttl_restante(r: redis.Redis, usuario_id: int) -> int:
    """Segundos restantes antes de que expire el carrito. -2 si no existe."""
    return _ejecutar(lambda: r.ttl(_key(usuario_id)), lambda: respaldo.segundos_restantes(usuario_id))
