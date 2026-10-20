"""Manejadores globales de fallas de infraestructura (app/core/errores.py).

Se prueban sobre una app mínima para no tocar las bases reales: cada excepción
de un motor caído debe llegar al cliente como un JSON con ``detail`` (texto) y
``code`` estable, nunca como un 500 genérico ni con trazas internas.
"""

import cassandra
import httpx
import pymongo.errors as mongo_err
import pytest
import redis.exceptions as redis_err
import sqlalchemy.exc as sa_err
from cassandra.cluster import NoHostAvailable
from elastic_transport import ConnectionError as EsConnectionError
from fastapi import FastAPI
from fastapi.testclient import TestClient
from neo4j.exceptions import ServiceUnavailable

from app.core.errores import registrar_manejadores


class _OrigMySQL(Exception):
    """Imita la excepción del driver con su código de error de MySQL."""


def _mysql(codigo: int) -> sa_err.OperationalError:
    return sa_err.OperationalError('SELECT 1', {}, _OrigMySQL(codigo, 'error simulado'))


CASOS = [
    (redis_err.ConnectionError('caído'), 503, 'REDIS_UNAVAILABLE'),
    (mongo_err.ServerSelectionTimeoutError('caído'), 503, 'CATALOG_UNAVAILABLE'),
    (mongo_err.OperationFailure('consulta inválida'), 500, 'CATALOG_ERROR'),
    (_mysql(2003), 503, 'DATABASE_UNAVAILABLE'),
    (_mysql(1213), 409, 'CONCURRENT_UPDATE'),
    (_mysql(1205), 409, 'CONCURRENT_UPDATE'),
    (sa_err.IntegrityError('INSERT', {}, _OrigMySQL(1062, 'Duplicate entry')), 409, 'DATA_CONFLICT'),
    (ServiceUnavailable('caído'), 503, 'GRAPH_UNAVAILABLE'),
    (NoHostAvailable('caído', {}), 503, 'ANALYTICS_UNAVAILABLE'),
    (cassandra.OperationTimedOut('lento'), 503, 'ANALYTICS_UNAVAILABLE'),
    (EsConnectionError('caído'), 503, 'SEARCH_UNAVAILABLE'),
    (httpx.ConnectError('caído'), 503, 'EXTERNAL_SERVICE_UNAVAILABLE'),
]


@pytest.fixture
def cliente_que_falla():
    app = FastAPI()
    registrar_manejadores(app)
    excepcion = {}

    @app.get('/falla')
    def falla():
        raise excepcion['valor']

    cliente = TestClient(app, raise_server_exceptions=False)

    def llamar(exc):
        excepcion['valor'] = exc
        return cliente.get('/falla')

    return llamar


@pytest.mark.parametrize('exc, estado, codigo', CASOS, ids=[c[2] + ':' + type(c[0]).__name__ for c in CASOS])
def test_cada_falla_de_motor_devuelve_mensaje_claro(cliente_que_falla, exc, estado, codigo):
    respuesta = cliente_que_falla(exc)
    assert respuesta.status_code == estado
    cuerpo = respuesta.json()
    assert cuerpo['code'] == codigo
    assert isinstance(cuerpo['detail'], str) and cuerpo['detail']
    # No se filtran detalles internos del driver al cliente.
    assert 'simulado' not in cuerpo['detail'] and 'Duplicate' not in cuerpo['detail']


def test_los_503_indican_cuando_reintentar(cliente_que_falla):
    respuesta = cliente_que_falla(redis_err.ConnectionError('caído'))
    assert respuesta.headers.get('Retry-After') == '5'
