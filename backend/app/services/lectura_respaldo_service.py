"""Modo de solo lectura cuando MySQL no responde (plan B de MySQL).

MySQL es la autoridad del dinero y del inventario y no se reemplaza. Lo que sí
se puede es seguir *mostrando* lo último que se leyó de él: cada respuesta
exitosa de ciertos endpoints de solo lectura (categorías, datos del usuario,
direcciones) se guarda en Redis, y si MySQL no responde se devuelve esa copia.

``consultar`` es el único punto de entrada: intenta MySQL (si su circuito está
cerrado), guarda el resultado y, ante una caída de conexión, sirve la copia.
"""

from __future__ import annotations

import json
import logging
from typing import Callable

import redis
from sqlalchemy.exc import InterfaceError, OperationalError

from app.core import salud

logger = logging.getLogger(__name__)

PREFIJO = 'respaldo:lectura:'
VIGENCIA_SEGUNDOS = 7 * 24 * 3600
# Errores de MySQL que significan «no hay servidor», no un error de la consulta.
_SIN_CONEXION = {2002, 2003, 2006, 2013, 2055}


class MySQLNoDisponible(Exception):
    """MySQL no responde y no hay copia guardada de lo pedido."""


def es_caida(exc: BaseException) -> bool:
    """True si la excepción indica que MySQL no está disponible."""
    if isinstance(exc, MySQLNoDisponible):
        return True
    if isinstance(exc, InterfaceError):
        return True
    if isinstance(exc, OperationalError):
        orig = getattr(exc, 'orig', None)
        codigo = orig.args[0] if orig is not None and getattr(orig, 'args', None) else None
        return codigo in _SIN_CONEXION or codigo is None
    return False


def disponible() -> bool:
    return salud.disponible('mysql')


def registrar_caida(exc: BaseException) -> None:
    salud.registrar_falla('mysql', exc, confirmada=True)


def _redis():
    from app.core.db_redis import get_redis
    return get_redis()


def guardar(clave: str, datos) -> None:
    """Guarda una copia JSON de lo leído (sin fallar si Redis no responde)."""
    try:
        _redis().set(PREFIJO + clave, json.dumps(datos, default=str), ex=VIGENCIA_SEGUNDOS)
    except redis.RedisError as exc:
        logger.warning('No se guardó la copia de lectura %s: %s', clave, exc)


def leer(clave: str):
    try:
        crudo = _redis().get(PREFIJO + clave)
    except redis.RedisError:
        return None
    return json.loads(crudo) if crudo else None


def consultar(clave: str, consulta: Callable[[], object]):
    """Resultado de ``consulta`` (MySQL) o, si MySQL no responde, su última copia."""
    if disponible():
        try:
            resultado = consulta()
        except (OperationalError, InterfaceError) as exc:
            if not es_caida(exc):
                raise
            registrar_caida(exc)
            logger.warning('MySQL no responde; se sirve la copia de lectura %s.', clave)
        else:
            salud.registrar_exito('mysql')
            guardar(clave, resultado)
            return resultado
    copia = leer(clave)
    if copia is None:
        raise MySQLNoDisponible(f'Sin copia de lectura para {clave}.')
    return copia
