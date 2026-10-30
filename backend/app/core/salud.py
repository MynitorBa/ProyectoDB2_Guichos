"""Estado de salud de cada motor y detector de fallas (circuit breaker).

Cada motor tiene un contador de fallas consecutivas. Al llegar a ``UMBRAL``
el circuito se **abre**: durante ``ESPERA_SEGUNDOS`` ``disponible()`` responde
False y quien tenga un respaldo lo usa de inmediato, sin pagar el timeout del
motor caído en cada petición. Pasada la espera se deja pasar un intento
(semiabierto): si funciona, el circuito se cierra; si falla, se vuelve a abrir.

``sondear()`` hace un ping real a los seis motores y al servicio de embeddings (en paralelo y con tiempo
límite) y alimenta el mismo estado; lo usa ``GET /salud/motores``.
"""

from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturoVencido
from dataclasses import dataclass

logger = logging.getLogger(__name__)

MOTORES = ('mysql', 'mongo', 'redis', 'elasticsearch', 'neo4j', 'cassandra', 'embeddings')
UMBRAL = 3
ESPERA_SEGUNDOS = 15
TIEMPO_SONDEO_SEGUNDOS = 3
CACHE_SONDEO_SEGUNDOS = 5


@dataclass
class _Estado:
    fallas: int = 0
    abierto_hasta: float = 0.0
    ultimo_error: str | None = None
    ultima_falla: float | None = None
    ultimo_exito: float | None = None


_lock = threading.Lock()
_estados = {motor: _Estado() for motor in MOTORES}


def _estado(motor: str) -> _Estado:
    if motor not in _estados:
        raise ValueError(f'Motor desconocido: {motor}')
    return _estados[motor]


def disponible(motor: str) -> bool:
    """False mientras el circuito está abierto: usar el respaldo sin intentar."""
    with _lock:
        return time.monotonic() >= _estado(motor).abierto_hasta


def degradado(motor: str) -> bool:
    """True si el motor acumula fallas recientes (circuito abierto o semiabierto)."""
    with _lock:
        return _estado(motor).fallas >= UMBRAL


def registrar_exito(motor: str) -> None:
    with _lock:
        e = _estado(motor)
        if e.fallas >= UMBRAL:
            logger.info('%s volvió a responder; se cierra el circuito.', motor)
        e.fallas = 0
        e.abierto_hasta = 0.0
        e.ultimo_exito = time.time()


def registrar_falla(motor: str, exc: BaseException | str | None = None, *, confirmada: bool = False) -> None:
    """Cuenta una falla. ``confirmada`` (un ping fallido) abre el circuito de inmediato."""
    with _lock:
        e = _estado(motor)
        e.fallas = max(e.fallas + 1, UMBRAL if confirmada else 0)
        e.ultima_falla = time.time()
        e.ultimo_error = (exc if isinstance(exc, str) else exc.__class__.__name__) if exc else None
        if e.fallas >= UMBRAL:
            if e.abierto_hasta <= time.monotonic():
                logger.warning('%s falló %s veces seguidas; se abre el circuito %s s.',
                               motor, e.fallas, ESPERA_SEGUNDOS)
            e.abierto_hasta = time.monotonic() + ESPERA_SEGUNDOS


def reiniciar() -> None:
    """Vuelve todos los circuitos a cerrado (pruebas)."""
    global _ultimo_sondeo
    with _lock:
        for motor in MOTORES:
            _estados[motor] = _Estado()
        _ultimo_sondeo = (0.0, None)


def estado(motor: str) -> str:
    """'ok', 'degradado' (fallas recientes, semiabierto) o 'caido' (circuito abierto)."""
    with _lock:
        e = _estado(motor)
        if e.fallas < UMBRAL:
            return 'ok'
        return 'caido' if time.monotonic() < e.abierto_hasta else 'degradado'


# ── Sondeo activo ─────────────────────────────────────────────────────────────

def _ping_mysql():
    from sqlalchemy import text
    from app.core.db_mysql import engine
    with engine.connect() as conn:
        conn.execute(text('SELECT 1'))


def _ping_mongo():
    from app.core.db_mongo import get_mongo_client
    get_mongo_client().admin.command('ping')


def _ping_redis():
    from app.core.db_redis import get_redis
    get_redis().ping()


def _ping_elasticsearch():
    from app.core.db_elastic import get_es
    if not get_es().ping():
        raise ConnectionError('Elasticsearch no respondió al ping')


def _ping_neo4j():
    from app.core.db_neo4j import get_driver
    with get_driver().session() as s:
        s.run('RETURN 1').consume()


def _ping_cassandra():
    from app.core.db_cassandra import get_cassandra_session
    get_cassandra_session(initialize=False).execute('SELECT release_version FROM system.local')


def _ping_embeddings():
    from app.services.embeddings_client import estado
    if not estado().get('listo'):
        raise ConnectionError('El modelo de embeddings no está cargado')


_PINGS = {
    'mysql': _ping_mysql, 'mongo': _ping_mongo, 'redis': _ping_redis,
    'elasticsearch': _ping_elasticsearch, 'neo4j': _ping_neo4j, 'cassandra': _ping_cassandra,
    'embeddings': _ping_embeddings,
}
# Los hilos del sondeo pueden quedar esperando a un motor colgado; un pool
# propio evita que se acumulen más allá de uno por motor.
_pool = ThreadPoolExecutor(max_workers=len(MOTORES), thread_name_prefix='sondeo-salud')
_lock_sondeo = threading.Lock()
_ultimo_sondeo: tuple[float, dict | None] = (0.0, None)


def _probar(motor: str) -> None:
    _PINGS[motor]()


def sondear(forzar: bool = False) -> dict:
    """Ping real a cada motor; el resultado se reutiliza durante unos segundos."""
    global _ultimo_sondeo
    with _lock_sondeo:
        hecho_en, resultado = _ultimo_sondeo
        if not forzar and resultado is not None and time.monotonic() - hecho_en < CACHE_SONDEO_SEGUNDOS:
            return resultado
        futuros = {motor: _pool.submit(_probar, motor) for motor in MOTORES}
        limite = time.monotonic() + TIEMPO_SONDEO_SEGUNDOS
        for motor, futuro in futuros.items():
            try:
                futuro.result(timeout=max(0.0, limite - time.monotonic()))
                registrar_exito(motor)
            except FuturoVencido:
                registrar_falla(motor, 'sin respuesta', confirmada=True)
            except Exception as exc:  # noqa: BLE001 - cualquier error es una falla del motor
                registrar_falla(motor, exc, confirmada=True)
        resultado = resumen()
        _ultimo_sondeo = (time.monotonic(), resultado)
        return resultado


def resumen() -> dict:
    motores = {motor: estado(motor) for motor in MOTORES}
    return {
        'motores': motores,
        'degradados': [motor for motor, valor in motores.items() if valor != 'ok'],
    }
