"""Inyección de fallas controlada para demostrar la estrategia de consistencia.

Solo opera con ``FAULT_INJECTION_ENABLED=true`` (desarrollo y pruebas). Cada
punto de falla simula una caída en un lugar concreto del flujo, por ejemplo
"el proceso muere después de cobrar y antes de confirmar el pedido", para
mostrar cómo el sistema se recupera sin perder ni duplicar datos.

Los puntos de un componente (``redis``, ``mysql``, ``mongo``, ``embeddings``)
simulan que ese motor deja de responder **en ese instante exacto**: lanzan el
mismo error que lanzaría su driver con el contenedor caído, así que se ejecuta
el mismo camino de recuperación que en una caída real, pero en el momento
preciso que se quiere probar (algo imposible de lograr con ``docker stop``).

Modos: ``una_vez`` (se desactiva tras dispararse) o ``siempre``.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass

from app.core.config import settings

logger = logging.getLogger(__name__)


class FallaSimulada(RuntimeError):
    """Error provocado a propósito por un punto de falla activo."""


def _proceso(mensaje: str) -> BaseException:
    return FallaSimulada(mensaje)


def _redis(mensaje: str) -> BaseException:
    import redis
    return redis.ConnectionError(mensaje)


def _mysql_sin_conexion(mensaje: str) -> BaseException:
    import pymysql
    from sqlalchemy.exc import OperationalError
    # 2013: «Lost connection to MySQL server during query», lo que se ve si el
    # servidor cae con la consulta en curso.
    return OperationalError('falla simulada', {}, pymysql.err.OperationalError(2013, mensaje))


def _mysql_deadlock(mensaje: str) -> BaseException:
    import pymysql
    from sqlalchemy.exc import OperationalError
    return OperationalError('falla simulada', {}, pymysql.err.OperationalError(1213, mensaje))


def _mongo(mensaje: str) -> BaseException:
    from pymongo.errors import ServerSelectionTimeoutError
    return ServerSelectionTimeoutError(mensaje)


def _embeddings(mensaje: str) -> BaseException:
    import httpx
    return httpx.ConnectError(mensaje)


@dataclass(frozen=True)
class Punto:
    descripcion: str
    grupo: str = 'proceso'
    error: object = _proceso


PUNTOS_DEF: dict[str, Punto] = {
    # Caídas del proceso del backend en medio de la saga.
    'checkout.despues_reserva': Punto('El proceso cae tras reservar el inventario y antes de cobrar.'),
    'checkout.despues_cobro': Punto('El proceso cae tras cobrar y antes de confirmar el pedido.'),
    'checkout.confirmacion': Punto('La transacción de confirmación falla después de cobrar.'),
    'checkout.respuesta_perdida': Punto('El pedido ya quedó confirmado, pero la respuesta nunca llega al navegador.'),
    # Un motor deja de responder en un instante preciso.
    'checkout.redis_leer_carrito': Punto('Redis cae justo al leer el carrito cuando se presiona «Comprar».', 'redis', _redis),
    'checkout.redis_validar_flash': Punto('Redis cae justo al validar la reserva flash del carrito al comprar.', 'redis', _redis),
    'checkout.redis_consumir_flash': Punto('Redis cae justo al cerrar la reserva flash, con la venta ya confirmada.', 'redis', _redis),
    'checkout.redis_vaciar_carrito': Punto('Redis cae justo al vaciar el carrito, con la venta ya confirmada.', 'redis', _redis),
    'checkout.mysql_al_recibir': Punto('MySQL deja de responder justo al recibir la compra, antes de reservar.', 'mysql', _mysql_sin_conexion),
    'checkout.mysql_deadlock': Punto('MySQL elige esta compra como víctima de un deadlock al bloquear las ofertas.', 'mysql', _mysql_deadlock),
    'checkout.mysql_durante_reserva': Punto('MySQL pierde la conexión a mitad de la reserva, con las filas bloqueadas.', 'mysql', _mysql_sin_conexion),
    'checkout.mongo_lineas': Punto('MongoDB cae justo al leer los nombres de producto para las líneas del pedido.', 'mongo', _mongo),
    'carrito.redis_agregar': Punto('Redis cae justo al agregar un producto al carrito.', 'redis', _redis),
    'flash.redis_tras_reservar': Punto('Redis aparta la unidad flash pero la conexión se corta antes de responder.', 'redis', _redis),
    'busqueda.embeddings': Punto('El servicio de embeddings cae justo al vectorizar una búsqueda.', 'embeddings', _embeddings),
    # Destinos del outbox.
    'outbox.mongo': Punto('El destino MongoDB del outbox falla.', 'outbox'),
    'outbox.busqueda': Punto('El destino Elasticsearch del outbox falla.', 'outbox'),
    'outbox.cassandra': Punto('El destino Cassandra del outbox falla.', 'outbox'),
    'outbox.neo4j': Punto('El destino Neo4j del outbox falla.', 'outbox'),
    'outbox.redis': Punto('El destino Redis del outbox falla.', 'outbox'),
    'outbox.catalogo': Punto('El destino «copia del catálogo» (MySQL, plan B) del outbox falla.', 'outbox'),
}
PUNTOS = {punto: d.descripcion for punto, d in PUNTOS_DEF.items()}
MODOS = ('una_vez', 'siempre')

_activos: dict[str, str] = {}
_disparos: dict[str, int] = {}
_lock = threading.Lock()


def habilitada() -> bool:
    return bool(settings.FAULT_INJECTION_ENABLED)


def activar(punto: str, modo: str = 'una_vez') -> None:
    if not habilitada():
        raise PermissionError('La inyección de fallas está deshabilitada.')
    if punto not in PUNTOS:
        raise ValueError(f'Punto de falla desconocido: {punto}')
    if modo not in MODOS:
        raise ValueError(f'Modo desconocido: {modo}')
    with _lock:
        _activos[punto] = modo


def desactivar(punto: str | None = None) -> None:
    with _lock:
        if punto is None:
            _activos.clear()
        else:
            _activos.pop(punto, None)


def disparos(punto: str) -> int:
    with _lock:
        return _disparos.get(punto, 0)


def estado() -> dict:
    with _lock:
        return {
            'habilitada': habilitada(),
            'puntos': [
                {'punto': p, 'descripcion': d.descripcion, 'grupo': d.grupo,
                 'modo': _activos.get(p), 'disparos': _disparos.get(p, 0)}
                for p, d in PUNTOS_DEF.items()
            ],
        }


def punto_de_falla(punto: str) -> None:
    """Lanza el error del punto si está activo. No hace nada si no."""
    if not _activos or not habilitada():
        return
    with _lock:
        modo = _activos.get(punto)
        if modo is None:
            return
        if modo == 'una_vez':
            del _activos[punto]
        _disparos[punto] = _disparos.get(punto, 0) + 1
    definicion = PUNTOS_DEF[punto]
    logger.warning('Falla simulada en %s', punto)
    raise definicion.error(f'Falla simulada: {definicion.descripcion}')
