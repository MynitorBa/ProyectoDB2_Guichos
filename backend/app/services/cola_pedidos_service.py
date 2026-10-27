"""Pedidos en cola mientras MySQL no responde (plan B de MySQL).

Sin MySQL no se puede reservar inventario ni registrar un pago, así que no se
cobra nada. El checkout guarda en Redis una **solicitud de pedido** con lo que
había en el carrito (precio que el usuario vio, cantidades, dirección y método
de pago) y responde 202. Cuando MySQL vuelve, un worker pasa cada solicitud por
la saga normal de ``procesar_checkout``: revalida precio y existencia, reserva,
cobra y confirma. Si algo cambió (otro precio, sin stock, pago rechazado) la
solicitud queda «requiere atención» y se avisa al usuario; nunca se cobra un
precio distinto del que vio.

Claves de Redis:
- ``cola_pedidos:pendientes`` (LIST): ids en orden de llegada.
- ``cola_pedidos:solicitud:{id}`` (STRING JSON): la solicitud y su estado.
- ``cola_pedidos:usuario:{usuario_id}`` (LIST): ids del usuario, para listarlas.
- ``cola_pedidos:clave:{Idempotency-Key}``: id ya creado con esa clave.
"""

from __future__ import annotations

import json
import logging
import threading
import uuid
from decimal import Decimal

import redis
from sqlalchemy.exc import IntegrityError

from app.core import salud
from app.core.time import utc_now

logger = logging.getLogger(__name__)

PENDIENTES = 'cola_pedidos:pendientes'
VIGENCIA_SEGUNDOS = 30 * 24 * 3600
INTERVALO_SEGUNDOS = 5
_LOCK = 'cola_pedidos:procesando'


class SolicitudInvalida(Exception):
    def __init__(self, mensaje: str, codigo: str, estado: int = 409):
        super().__init__(mensaje)
        self.mensaje, self.codigo, self.estado = mensaje, codigo, estado


def _clave(solicitud_id: str) -> str:
    return f'cola_pedidos:solicitud:{solicitud_id}'


def obtener(r: redis.Redis, solicitud_id: str) -> dict | None:
    crudo = r.get(_clave(solicitud_id))
    return json.loads(crudo) if crudo else None


def _guardar(r: redis.Redis, solicitud: dict) -> None:
    r.set(_clave(solicitud['id']), json.dumps(solicitud), ex=VIGENCIA_SEGUNDOS)


def listar(r: redis.Redis, usuario_id: int) -> list[dict]:
    ids = r.lrange(f'cola_pedidos:usuario:{usuario_id}', 0, -1)
    return [s for s in (obtener(r, i) for i in ids) if s]


def encolar(r: redis.Redis, *, usuario_id: int, items: list[dict], direccion_id: int,
            metodo_pago_id: int, idempotency_key: str | None) -> dict:
    """Guarda la solicitud. Repetir con la misma clave devuelve la misma solicitud."""
    if idempotency_key:
        existente = r.get(f'cola_pedidos:clave:{idempotency_key}')
        if existente and (solicitud := obtener(r, existente)):
            return solicitud
    if not items:
        raise SolicitudInvalida('El carrito está vacío.', 'EMPTY_CART', 422)
    if any(item.get('promocion_flash_id') for item in items):
        raise SolicitudInvalida(
            'Las ofertas flash necesitan confirmar su cupo al momento y no pueden quedar en cola. '
            'Retíralas del carrito o intenta más tarde.', 'FLASH_REQUIRES_DATABASE')
    if any(s['estado'] == 'en_cola' for s in listar(r, usuario_id)):
        raise SolicitudInvalida('Ya tienes un pedido en cola; espera a que se procese.', 'ORDER_ALREADY_QUEUED')

    solicitud = {
        'id': str(uuid.uuid4()),
        'usuario_id': usuario_id,
        'items': [
            {'oferta_id': int(i['oferta_id']), 'cantidad': int(i['cantidad']),
             'precio_al_agregar': str(i['precio_al_agregar'])}
            for i in items
        ],
        'direccion_id': direccion_id,
        'metodo_pago_id': metodo_pago_id,
        # Clave propia para la saga: reintentar el procesamiento nunca crea dos pedidos.
        'clave_idempotencia': str(uuid.uuid4()),
        'creado_en': utc_now().isoformat(),
        'estado': 'en_cola',
        'pedido_id': None,
        'motivo': None,
    }
    with r.pipeline(transaction=True) as pipe:
        pipe.set(_clave(solicitud['id']), json.dumps(solicitud), ex=VIGENCIA_SEGUNDOS)
        pipe.rpush(PENDIENTES, solicitud['id'])
        pipe.lpush(f'cola_pedidos:usuario:{usuario_id}', solicitud['id'])
        if idempotency_key:
            pipe.set(f'cola_pedidos:clave:{idempotency_key}', solicitud['id'], ex=VIGENCIA_SEGUNDOS)
        pipe.execute()
    logger.info('Pedido en cola %s del usuario %s (MySQL no disponible).', solicitud['id'], usuario_id)
    return solicitud


# ── Procesamiento cuando MySQL vuelve ─────────────────────────────────────────

def _notificar(db, solicitud: dict, titulo: str, mensaje: str) -> None:
    from app.models.notificacion import Notificacion
    db.add(Notificacion(
        usuario_id=solicitud['usuario_id'], tipo='pedido_en_cola', titulo=titulo,
        mensaje=mensaje, pedido_id=solicitud.get('pedido_id'),
    ))
    db.commit()


def _procesar(r: redis.Redis, solicitud: dict) -> None:
    """Pasa una solicitud por la saga normal. Deja propagar las caídas de MySQL."""
    from app.core.db_mongo import get_mongo_db
    from app.core.db_mysql import SessionLocal
    from app.models.pedido import Pedido
    from app.schemas.checkout import CheckoutItem
    from app.services.checkout_service import CheckoutError, huella_solicitud, procesar_checkout

    items = [CheckoutItem(oferta_id=i['oferta_id'], cantidad=i['cantidad']) for i in solicitud['items']]
    with SessionLocal() as db:
        try:
            pedido = procesar_checkout(
                db, get_mongo_db(),
                usuario_id=solicitud['usuario_id'],
                direccion_id=solicitud['direccion_id'],
                metodo_pago_id=solicitud['metodo_pago_id'],
                items=items,
                precios_esperados={i['oferta_id']: Decimal(i['precio_al_agregar']) for i in solicitud['items']},
                promociones_flash={},
                clave_idempotencia=solicitud['clave_idempotencia'],
                huella=huella_solicitud(items, solicitud['direccion_id'], solicitud['metodo_pago_id']),
            )
            solicitud.update({'estado': 'procesado', 'pedido_id': pedido.id, 'motivo': None})
            titulo, mensaje = 'Tu pedido en cola fue confirmado', \
                f'Confirmamos tu pedido #{pedido.id} con el precio que viste en el carrito.'
        except IntegrityError:
            # El proceso cayó después de crear el pedido: la clave ya existe.
            db.rollback()
            pedido = db.query(Pedido).filter_by(clave_idempotencia=solicitud['clave_idempotencia']).first()
            if not pedido:
                raise
            solicitud.update({'estado': 'procesado', 'pedido_id': pedido.id, 'motivo': None})
            titulo, mensaje = 'Tu pedido en cola fue registrado', f'Tu pedido #{pedido.id} quedó registrado.'
        except CheckoutError as exc:
            db.rollback()
            if exc.code == 'PAYMENT_PENDING':
                solicitud.update({'estado': 'procesado', 'pedido_id': exc.pedido_id,
                                  'motivo': 'El pago se está verificando con la pasarela.'})
                titulo, mensaje = 'Estamos verificando el pago de tu pedido', exc.message
            else:
                solicitud.update({'estado': 'requiere_atencion', 'pedido_id': exc.pedido_id,
                                  'motivo': exc.message, 'codigo': exc.code})
                titulo = 'Tu pedido en cola necesita tu atención'
                mensaje = f'No pudimos confirmarlo: {exc.message} No se realizó ningún cobro adicional.'
        _guardar(r, solicitud)
        r.lrem(PENDIENTES, 1, solicitud['id'])
        _notificar(db, solicitud, titulo, mensaje)
    logger.info('Pedido en cola %s procesado: %s', solicitud['id'], solicitud['estado'])


def procesar_pendientes(r: redis.Redis) -> int:
    """Procesa la cola en orden. Se detiene si MySQL vuelve a fallar."""
    from app.services import lectura_respaldo_service as lectura

    if not r.set(_LOCK, '1', nx=True, ex=120):
        return 0  # otro proceso ya la está atendiendo
    procesadas = 0
    try:
        while (solicitud_id := r.lindex(PENDIENTES, 0)) is not None:
            solicitud = obtener(r, solicitud_id)
            if not solicitud or solicitud['estado'] != 'en_cola':
                r.lrem(PENDIENTES, 1, solicitud_id)
                continue
            try:
                _procesar(r, solicitud)
            except Exception as exc:  # noqa: BLE001
                if lectura.es_caida(exc):
                    lectura.registrar_caida(exc)
                    break
                logger.exception('Error procesando el pedido en cola %s; queda pendiente.', solicitud_id)
                break
            procesadas += 1
            r.expire(_LOCK, 120)
    finally:
        r.delete(_LOCK)
    return procesadas


# ── Worker ────────────────────────────────────────────────────────────────────

_stop = threading.Event()
_thread: threading.Thread | None = None


def _loop() -> None:
    from app.core.db_redis import get_redis
    while not _stop.is_set():
        if salud.disponible('mysql'):
            try:
                if get_redis().llen(PENDIENTES):
                    procesar_pendientes(get_redis())
            except redis.RedisError as exc:
                logger.warning('No se pudo revisar la cola de pedidos: %s', exc)
            except Exception:
                logger.exception('Error en el worker de pedidos en cola')
        _stop.wait(INTERVALO_SEGUNDOS)


def start_cola_pedidos_worker() -> None:
    global _thread
    if _thread and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_loop, name='tiendaya-cola-pedidos', daemon=True)
    _thread.start()


def stop_cola_pedidos_worker() -> None:
    global _thread
    _stop.set()
    if _thread and _thread.is_alive():
        _thread.join(timeout=5)
    _thread = None
