"""Manejo centralizado de errores de infraestructura.

Cuando un motor (MySQL, MongoDB, Redis, Neo4j, Cassandra, Elasticsearch o la
pasarela) falla y el endpoint no lo atrapó, la respuesta deja de ser un 500
genérico: es un 503 con un mensaje que dice qué parte no está disponible y un
``code`` estable para el frontend. Nunca se filtran trazas al cliente.

El formato es el mismo del resto de la API: ``{"detail": "...", "code": "..."}``.
"""

from __future__ import annotations

import logging

import httpx
import pymongo.errors as mongo_err
import redis.exceptions as redis_err
import sqlalchemy.exc as sa_err
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core import salud
from app.services.lectura_respaldo_service import MySQLNoDisponible, es_caida

logger = logging.getLogger(__name__)

# Códigos de error de MySQL que indican una carrera con otra transacción,
# no una caída: el cliente puede reintentar.
_MYSQL_BLOQUEO = {1205, 1213}  # lock wait timeout, deadlock


def _respuesta(status: int, detalle: str, codigo: str, reintentar_en: int | None = None) -> JSONResponse:
    headers = {'Retry-After': str(reintentar_en)} if reintentar_en else None
    return JSONResponse(status_code=status, content={'detail': detalle, 'code': codigo}, headers=headers)


def _registrar(request: Request, exc: Exception, motor: str, clave: str | None = None) -> None:
    # La falla también alimenta el detector de fallas del motor (salud.py).
    if clave:
        salud.registrar_falla(clave, exc)
    logger.error('%s no disponible en %s %s: %s', motor, request.method, request.url.path,
                 exc.__class__.__name__, exc_info=(type(exc), exc, exc.__traceback__))


def registrar_manejadores(app: FastAPI) -> None:
    @app.exception_handler(redis_err.RedisError)
    async def redis_caido(request: Request, exc: redis_err.RedisError):
        _registrar(request, exc, 'Redis', 'redis')
        return _respuesta(503, 'El carrito y las ofertas flash no están disponibles temporalmente. '
                               'Intenta de nuevo en unos momentos.', 'REDIS_UNAVAILABLE', 5)

    @app.exception_handler(mongo_err.PyMongoError)
    async def mongo_caido(request: Request, exc: mongo_err.PyMongoError):
        conexion = isinstance(exc, (mongo_err.ConnectionFailure, mongo_err.NetworkTimeout, mongo_err.ExecutionTimeout))
        _registrar(request, exc, 'MongoDB', 'mongo' if conexion else None)
        if isinstance(exc, (mongo_err.ConnectionFailure, mongo_err.NetworkTimeout, mongo_err.ExecutionTimeout)):
            return _respuesta(503, 'El catálogo de productos no está disponible temporalmente. '
                                   'Intenta de nuevo en unos momentos.', 'CATALOG_UNAVAILABLE', 5)
        return _respuesta(500, 'No se pudo completar la operación con el catálogo.', 'CATALOG_ERROR')

    @app.exception_handler(sa_err.OperationalError)
    async def mysql_operacional(request: Request, exc: sa_err.OperationalError):
        codigo_mysql = exc.orig.args[0] if getattr(exc, 'orig', None) is not None and exc.orig.args else None
        if codigo_mysql in _MYSQL_BLOQUEO:
            logger.warning('Conflicto de bloqueo en %s %s: %s', request.method, request.url.path, codigo_mysql)
            return _respuesta(409, 'Otra operación estaba modificando los mismos datos. Intenta de nuevo.',
                              'CONCURRENT_UPDATE', 1)
        _registrar(request, exc, 'MySQL', 'mysql')
        if es_caida(exc):
            salud.registrar_falla('mysql', exc, confirmada=True)
        return _respuesta(503, 'La base de datos principal no está disponible temporalmente. '
                               'Intenta de nuevo en unos momentos.', 'DATABASE_UNAVAILABLE', 5)

    @app.exception_handler(MySQLNoDisponible)
    async def mysql_sin_copia(request: Request, exc: MySQLNoDisponible):
        return _respuesta(503, 'La tienda está en modo de solo lectura: esta información no está '
                               'disponible por ahora. Intenta de nuevo en unos momentos.',
                          'DATABASE_UNAVAILABLE', 5)

    @app.exception_handler(sa_err.InterfaceError)
    async def mysql_interfaz(request: Request, exc: sa_err.InterfaceError):
        _registrar(request, exc, 'MySQL', 'mysql')
        return _respuesta(503, 'La base de datos principal no está disponible temporalmente. '
                               'Intenta de nuevo en unos momentos.', 'DATABASE_UNAVAILABLE', 5)

    @app.exception_handler(sa_err.TimeoutError)
    async def mysql_pool(request: Request, exc: sa_err.TimeoutError):
        _registrar(request, exc, 'MySQL (pool)')
        return _respuesta(503, 'El servidor está muy ocupado. Intenta de nuevo en unos segundos.',
                          'DATABASE_BUSY', 2)

    @app.exception_handler(sa_err.IntegrityError)
    async def mysql_integridad(request: Request, exc: sa_err.IntegrityError):
        # Llega aquí solo si el endpoint no validó el caso: no se exponen nombres de índices.
        logger.warning('Violación de integridad no controlada en %s %s: %s',
                       request.method, request.url.path, exc.orig)
        return _respuesta(409, 'La operación entra en conflicto con datos existentes '
                               '(por ejemplo, un registro duplicado).', 'DATA_CONFLICT')

    try:
        import neo4j.exceptions as neo_err

        @app.exception_handler(neo_err.ServiceUnavailable)
        @app.exception_handler(neo_err.SessionExpired)
        async def neo4j_caido(request: Request, exc: Exception):
            _registrar(request, exc, 'Neo4j', 'neo4j')
            return _respuesta(503, 'Las reseñas, recomendaciones y el análisis de fraude no están '
                                   'disponibles temporalmente.', 'GRAPH_UNAVAILABLE', 5)
    except ImportError:  # pragma: no cover - el driver es dependencia del proyecto
        pass

    try:
        import cassandra
        from cassandra.cluster import NoHostAvailable

        @app.exception_handler(NoHostAvailable)
        @app.exception_handler(cassandra.OperationTimedOut)
        @app.exception_handler(cassandra.Unavailable)
        async def cassandra_caido(request: Request, exc: Exception):
            _registrar(request, exc, 'Cassandra', 'cassandra')
            return _respuesta(503, 'Las estadísticas y tendencias de ventas no están disponibles '
                                   'temporalmente.', 'ANALYTICS_UNAVAILABLE', 5)
    except ImportError:  # pragma: no cover
        pass

    try:
        from elastic_transport import TransportError

        @app.exception_handler(TransportError)
        async def elastic_caido(request: Request, exc: TransportError):
            _registrar(request, exc, 'Elasticsearch', 'elasticsearch')
            return _respuesta(503, 'El buscador no está disponible temporalmente.',
                              'SEARCH_UNAVAILABLE', 5)
    except ImportError:  # pragma: no cover
        pass

    @app.exception_handler(httpx.HTTPError)
    async def servicio_externo(request: Request, exc: httpx.HTTPError):
        _registrar(request, exc, 'Servicio externo')
        return _respuesta(503, 'Un servicio externo (por ejemplo, la pasarela de pagos) no respondió. '
                               'Intenta de nuevo en unos momentos.', 'EXTERNAL_SERVICE_UNAVAILABLE', 5)
