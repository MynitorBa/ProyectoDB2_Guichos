"""Inyección de fallas controlada para demostrar la estrategia de consistencia.

Solo opera con ``FAULT_INJECTION_ENABLED=true`` (desarrollo y pruebas). Cada
punto de falla simula una caída en un lugar concreto del flujo, por ejemplo
"el proceso muere después de cobrar y antes de confirmar el pedido", para
mostrar cómo el sistema se recupera sin perder ni duplicar datos.

Modos: ``una_vez`` (se desactiva tras dispararse) o ``siempre``.
"""

from __future__ import annotations

import logging
import threading

from app.core.config import settings

logger = logging.getLogger(__name__)

PUNTOS = {
    'checkout.despues_reserva': 'El proceso cae tras reservar el inventario y antes de cobrar.',
    'checkout.despues_cobro': 'El proceso cae tras cobrar y antes de confirmar el pedido.',
    'checkout.confirmacion': 'La transacción de confirmación falla después de cobrar.',
    'outbox.mongo': 'El destino MongoDB del outbox falla.',
    'outbox.busqueda': 'El destino Elasticsearch del outbox falla.',
    'outbox.cassandra': 'El destino Cassandra del outbox falla.',
    'outbox.neo4j': 'El destino Neo4j del outbox falla.',
    'outbox.redis': 'El destino Redis del outbox falla.',
}
MODOS = ('una_vez', 'siempre')

_activos: dict[str, str] = {}
_disparos: dict[str, int] = {}
_lock = threading.Lock()


class FallaSimulada(RuntimeError):
    """Error provocado a propósito por un punto de falla activo."""


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


def estado() -> dict:
    with _lock:
        return {
            'habilitada': habilitada(),
            'puntos': [
                {'punto': p, 'descripcion': d, 'modo': _activos.get(p), 'disparos': _disparos.get(p, 0)}
                for p, d in PUNTOS.items()
            ],
        }


def punto_de_falla(punto: str) -> None:
    """Lanza ``FallaSimulada`` si el punto está activo. No hace nada si no."""
    if not _activos or not habilitada():
        return
    with _lock:
        modo = _activos.get(punto)
        if modo is None:
            return
        if modo == 'una_vez':
            del _activos[punto]
        _disparos[punto] = _disparos.get(punto, 0) + 1
    logger.warning('Falla simulada en %s', punto)
    raise FallaSimulada(f'Falla simulada: {PUNTOS[punto]}')
