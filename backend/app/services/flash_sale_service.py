"""Contador y reservas atómicas de ventas flash en Redis."""

import json
from decimal import Decimal
from datetime import timedelta, timezone

import redis
from sqlalchemy import func, text

from app.core import salud
from app.core.fault_injection import punto_de_falla
from app.core.time import utc_now
from app.models.promocion_flash import PromocionFlash, ReservaFlash


_RESERVE_LUA = """
local expired = redis.call('ZRANGEBYSCORE', KEYS[3], '-inf', ARGV[1])
for _, user_id in ipairs(expired) do
  local raw = redis.call('HGET', KEYS[2], user_id)
  if raw then
    local old = cjson.decode(raw)
    redis.call('HINCRBY', KEYS[1], 'disponibles', tonumber(old['cantidad']))
    redis.call('HDEL', KEYS[2], user_id)
  end
  redis.call('ZREM', KEYS[3], user_id)
end

local estado = redis.call('HGET', KEYS[1], 'estado')
local inicia = tonumber(redis.call('HGET', KEYS[1], 'inicia_ts') or '0')
local finaliza = tonumber(redis.call('HGET', KEYS[1], 'finaliza_ts') or '0')
if estado ~= 'activa' or tonumber(ARGV[1]) < inicia or tonumber(ARGV[1]) >= finaliza then
  return {-1, '', tonumber(redis.call('HGET', KEYS[1], 'disponibles') or '0'), 0}
end

local current = redis.call('HGET', KEYS[2], ARGV[2])
if current then
  local existing = cjson.decode(current)
  return {2, existing['token'], tonumber(redis.call('HGET', KEYS[1], 'disponibles')), tonumber(existing['expira_ts'])}
end

local cantidad = tonumber(ARGV[3])
local max_user = tonumber(redis.call('HGET', KEYS[1], 'max_por_usuario') or '1')
local disponibles = tonumber(redis.call('HGET', KEYS[1], 'disponibles') or '0')
if cantidad < 1 or cantidad > max_user then return {-2, '', disponibles, 0} end
if disponibles < cantidad then return {0, '', disponibles, 0} end

local expira = math.min(tonumber(ARGV[1]) + tonumber(ARGV[5]), finaliza)
local value = cjson.encode({token=ARGV[4], cantidad=cantidad, expira_ts=expira})
redis.call('HSET', KEYS[2], ARGV[2], value)
redis.call('ZADD', KEYS[3], expira, ARGV[2])
redis.call('HINCRBY', KEYS[1], 'disponibles', -cantidad)
return {1, ARGV[4], disponibles-cantidad, expira}
"""

_RELEASE_LUA = """
local raw = redis.call('HGET', KEYS[2], ARGV[1])
if not raw then return 0 end
local data = cjson.decode(raw)
if data['token'] ~= ARGV[2] then return 0 end
redis.call('HINCRBY', KEYS[1], 'disponibles', tonumber(data['cantidad']))
redis.call('HDEL', KEYS[2], ARGV[1])
redis.call('ZREM', KEYS[3], ARGV[1])
return 1
"""

_CONSUME_LUA = """
local raw = redis.call('HGET', KEYS[2], ARGV[1])
if not raw then return 0 end
local data = cjson.decode(raw)
if data['token'] ~= ARGV[2] then return 0 end
redis.call('HDEL', KEYS[2], ARGV[1])
redis.call('ZREM', KEYS[3], ARGV[1])
redis.call('HINCRBY', KEYS[1], 'vendidas', tonumber(data['cantidad']))
return 1
"""

_CLEAN_LUA = """
local expired = redis.call('ZRANGEBYSCORE', KEYS[3], '-inf', ARGV[1])
local released = 0
for _, user_id in ipairs(expired) do
  local raw = redis.call('HGET', KEYS[2], user_id)
  if raw then
    local old = cjson.decode(raw)
    released = released + tonumber(old['cantidad'])
    redis.call('HDEL', KEYS[2], user_id)
  end
  redis.call('ZREM', KEYS[3], user_id)
end
if released > 0 then redis.call('HINCRBY', KEYS[1], 'disponibles', released) end
return {released, tonumber(redis.call('HGET', KEYS[1], 'disponibles') or '0')}
"""


def _keys(promocion_id: int) -> tuple[str, str, str]:
    base = f'flash:{promocion_id}'
    return base, f'{base}:reservas', f'{base}:expiraciones'


def inicializar(
    r: redis.Redis,
    *,
    promocion_id: int,
    unidades: int,
    max_por_usuario: int,
    inicia_ts: int,
    finaliza_ts: int,
    precio: Decimal,
    estado: str = 'activa',
) -> None:
    state, reservations, expirations = _keys(promocion_id)
    with r.pipeline(transaction=True) as pipe:
        pipe.delete(state, reservations, expirations)
        pipe.hset(state, mapping={
            'disponibles': unidades,
            'vendidas': 0,
            'max_por_usuario': max_por_usuario,
            'inicia_ts': inicia_ts,
            'finaliza_ts': finaliza_ts,
            'precio': str(precio),
            'estado': estado,
        })
        ttl = max(1, finaliza_ts - inicia_ts + 86_400)
        pipe.expire(state, ttl)
        pipe.execute()


def rehidratar_si_falta(r: redis.Redis, promotion, reservations) -> bool:
    """Reconstruye en Redis una promoción vigente usando el estado durable MySQL.

    Redis acelera la competencia, pero MySQL conserva la información necesaria
    para recuperarnos tras reiniciar o perder el contenedor Redis.
    """
    state, reservation_key, expiration_key = _keys(promotion.id)
    if r.exists(state):
        return False
    lock_key = f'{state}:rehydrate-lock'
    if not r.set(lock_key, '1', nx=True, ex=5):
        return False
    try:
        if r.exists(state):
            return False
        active = [row for row in reservations if row.estado == 'reservada']
        reserved = sum(row.cantidad for row in active)
        available = max(
            0,
            promotion.unidades_totales - promotion.unidades_vendidas - reserved,
        )
        starts_ts = int(promotion.inicia_en.replace(tzinfo=timezone.utc).timestamp())
        ends_ts = int(promotion.finaliza_en.replace(tzinfo=timezone.utc).timestamp())
        with r.pipeline(transaction=True) as pipe:
            pipe.delete(state, reservation_key, expiration_key)
            pipe.hset(state, mapping={
                'disponibles': available,
                'vendidas': promotion.unidades_vendidas,
                'max_por_usuario': promotion.max_por_usuario,
                'inicia_ts': starts_ts,
                'finaliza_ts': ends_ts,
                'precio': str(promotion.precio_promocional),
                'estado': 'activa',
            })
            for row in active:
                expires_ts = int(row.expira_en.replace(tzinfo=timezone.utc).timestamp())
                pipe.hset(reservation_key, str(row.usuario_id), json.dumps({
                    'token': row.token,
                    'cantidad': row.cantidad,
                    'expira_ts': expires_ts,
                }))
                pipe.zadd(expiration_key, {str(row.usuario_id): expires_ts})
            ttl = max(1, ends_ts - starts_ts + 86_400)
            pipe.expire(state, ttl)
            pipe.execute()
        return True
    finally:
        r.delete(lock_key)


def reservar(
    r: redis.Redis,
    *,
    promocion_id: int,
    usuario_id: int,
    cantidad: int,
    token: str,
    ahora_ts: int,
    segundos_reserva: int,
) -> dict:
    result = r.eval(
        _RESERVE_LUA, 3, *_keys(promocion_id), ahora_ts, usuario_id,
        cantidad, token, segundos_reserva,
    )
    return {
        'codigo': int(result[0]),
        'token': result[1],
        'disponibles': int(result[2]),
        'expira_ts': int(result[3]),
    }


def liberar(r: redis.Redis, promocion_id: int, usuario_id: int, token: str) -> bool:
    return bool(r.eval(
        _RELEASE_LUA, 3, *_keys(promocion_id), usuario_id, token
    ))


def consumir(r: redis.Redis, promocion_id: int, usuario_id: int, token: str) -> bool:
    return bool(r.eval(
        _CONSUME_LUA, 3, *_keys(promocion_id), usuario_id, token
    ))


def obtener_reserva(r: redis.Redis, promocion_id: int, usuario_id: int) -> dict | None:
    raw = r.hget(_keys(promocion_id)[1], str(usuario_id))
    return json.loads(raw) if raw else None


def obtener_estado(r: redis.Redis, promocion_id: int) -> dict:
    raw = r.hgetall(_keys(promocion_id)[0])
    if not raw:
        return {}
    return {
        **raw,
        'disponibles': int(raw.get('disponibles', 0)),
        'vendidas': int(raw.get('vendidas', 0)),
        'inicia_ts': int(raw.get('inicia_ts', 0)),
        'finaliza_ts': int(raw.get('finaliza_ts', 0)),
    }


def limpiar_expiradas(r: redis.Redis, promocion_id: int, ahora_ts: int) -> dict:
    result = r.eval(_CLEAN_LUA, 3, *_keys(promocion_id), ahora_ts)
    return {'liberadas': int(result[0]), 'disponibles': int(result[1])}


def cerrar(r: redis.Redis, promocion_id: int) -> None:
    state, reservations, expirations = _keys(promocion_id)
    with r.pipeline(transaction=True) as pipe:
        pipe.hset(state, mapping={'estado': 'finalizada', 'disponibles': 0})
        pipe.delete(reservations, expirations)
        pipe.execute()


def eliminar(r: redis.Redis, promocion_id: int) -> None:
    r.delete(*_keys(promocion_id))


# ── Plan B: reservas en MySQL cuando Redis no responde ───────────────────────
#
# MySQL ya guarda el estado durable de cada promoción (unidades totales y
# vendidas) y cada reserva. Sin Redis, la competencia por el cupo se resuelve
# con un bloqueo de fila sobre la promoción: más lento que el script Lua, igual
# de correcto. La promoción queda marcada en flash_resincronizar y el worker
# reconstruye su estado en Redis desde MySQL cuando Redis vuelve.

def _ts(fecha) -> int:
    return int(fecha.replace(tzinfo=timezone.utc).timestamp())


def marcar_resincronizar(db, promocion_id: int) -> None:
    db.execute(text(
        'INSERT IGNORE INTO flash_resincronizar (promocion_id, creado_en) VALUES (:p, :a)'
    ), {'p': promocion_id, 'a': utc_now()})


def pendiente_resincronizar(db, promocion_id: int) -> bool:
    return db.execute(text(
        'SELECT 1 FROM flash_resincronizar WHERE promocion_id = :p'
    ), {'p': promocion_id}).first() is not None


def _reserva_mysql(db, promocion_id: int, usuario_id: int) -> dict | None:
    fila = db.query(ReservaFlash).filter(
        ReservaFlash.promocion_id == promocion_id,
        ReservaFlash.usuario_id == usuario_id,
        ReservaFlash.estado == 'reservada',
        ReservaFlash.expira_en > utc_now(),
    ).first()
    if not fila:
        return None
    return {'token': fila.token, 'cantidad': fila.cantidad, 'expira_ts': _ts(fila.expira_en)}


def reserva_vigente(r: redis.Redis, db, promocion_id: int, usuario_id: int, *,
                    punto_falla: str | None = None) -> dict | None:
    """La reserva del usuario: de Redis si responde; si no, o si la promoción
    cambió solo en MySQL y aún no se reconstruye en Redis, desde MySQL."""
    if salud.disponible('redis'):
        try:
            if punto_falla:
                punto_de_falla(punto_falla)
            reserva = obtener_reserva(r, promocion_id, usuario_id)
            salud.registrar_exito('redis')
            if reserva or not pendiente_resincronizar(db, promocion_id):
                return reserva
        except redis.RedisError as exc:
            salud.registrar_falla('redis', exc)
    return _reserva_mysql(db, promocion_id, usuario_id)


def liberar_seguro(r: redis.Redis, db, promocion_id: int, usuario_id: int, token: str) -> bool:
    """Libera la unidad en Redis; si no responde, la promoción queda por reconstruir.

    El llamador marca la reserva como cancelada en MySQL, que es lo durable.
    """
    if salud.disponible('redis'):
        try:
            resultado = liberar(r, promocion_id, usuario_id, token)
            salud.registrar_exito('redis')
            return resultado
        except redis.RedisError as exc:
            salud.registrar_falla('redis', exc)
    marcar_resincronizar(db, promocion_id)
    return False


def disponibles_mysql(db, promotion) -> int:
    """Cupo restante calculado solo con MySQL: totales − vendidas − reservas vigentes."""
    reservadas = db.query(func.coalesce(func.sum(ReservaFlash.cantidad), 0)).filter(
        ReservaFlash.promocion_id == promotion.id,
        ReservaFlash.estado == 'reservada',
        ReservaFlash.expira_en > utc_now(),
    ).scalar()
    return max(0, promotion.unidades_totales - promotion.unidades_vendidas - int(reservadas))


def reservar_en_mysql(db, *, promocion_id: int, usuario_id: int, cantidad: int, token: str) -> dict:
    """Mismo contrato que ``reservar`` (códigos 1, 2, 0, -1, -2), resuelto en MySQL.

    Con código 1 o 2 devuelve además ``reserva`` (el ReservaFlash). Confirma la
    transacción; el bloqueo de la fila de la promoción serializa a los compradores.
    """
    promotion = db.query(PromocionFlash).filter_by(id=promocion_id).with_for_update().one()
    ahora = utc_now()
    if promotion.estado not in {'programada', 'activa'} or not (promotion.inicia_en <= ahora < promotion.finaliza_en):
        db.rollback()
        return {'codigo': -1, 'token': '', 'disponibles': 0, 'expira_ts': 0}
    db.query(ReservaFlash).filter(
        ReservaFlash.promocion_id == promocion_id,
        ReservaFlash.estado == 'reservada',
        ReservaFlash.expira_en <= ahora,
    ).update({'estado': 'expirada'}, synchronize_session=False)
    existente = db.query(ReservaFlash).filter_by(
        promocion_id=promocion_id, usuario_id=usuario_id, estado='reservada'
    ).first()
    disponibles = disponibles_mysql(db, promotion)
    if existente:
        db.commit()
        return {'codigo': 2, 'token': existente.token, 'disponibles': disponibles,
                'expira_ts': _ts(existente.expira_en), 'reserva': existente}
    if cantidad < 1 or cantidad > promotion.max_por_usuario:
        db.rollback()
        return {'codigo': -2, 'token': '', 'disponibles': disponibles, 'expira_ts': 0}
    if disponibles < cantidad:
        db.rollback()
        return {'codigo': 0, 'token': '', 'disponibles': disponibles, 'expira_ts': 0}
    expira = min(ahora + timedelta(seconds=promotion.segundos_reserva), promotion.finaliza_en)
    reserva = ReservaFlash(
        token=token, promocion_id=promocion_id, usuario_id=usuario_id, cantidad=cantidad,
        precio_unitario=promotion.precio_promocional, expira_en=expira,
    )
    db.add(reserva)
    marcar_resincronizar(db, promocion_id)
    db.commit()
    return {'codigo': 1, 'token': token, 'disponibles': disponibles - cantidad,
            'expira_ts': _ts(expira), 'reserva': reserva}
