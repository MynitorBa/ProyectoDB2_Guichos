"""Detector de fallas por motor y endpoint GET /salud/motores."""

from fastapi.testclient import TestClient

from app.core import salud
from app.main import app

client = TestClient(app)


def test_el_circuito_se_abre_tras_el_umbral_y_se_cierra_con_un_exito():
    for _ in range(salud.UMBRAL - 1):
        salud.registrar_falla('redis', 'timeout')
    assert salud.disponible('redis') and salud.estado('redis') == 'ok'

    salud.registrar_falla('redis', 'timeout')
    assert not salud.disponible('redis')
    assert salud.estado('redis') == 'caido'
    assert salud.degradado('redis')

    salud.registrar_exito('redis')
    assert salud.disponible('redis') and salud.estado('redis') == 'ok'


def test_un_ping_fallido_abre_el_circuito_de_inmediato():
    salud.registrar_falla('mongo', 'sin respuesta', confirmada=True)
    assert not salud.disponible('mongo')


def test_pasada_la_espera_se_permite_un_intento(monkeypatch):
    monkeypatch.setattr(salud, 'ESPERA_SEGUNDOS', 0)
    salud.registrar_falla('neo4j', 'x', confirmada=True)
    assert salud.disponible('neo4j')
    assert salud.estado('neo4j') == 'degradado'


def test_endpoint_con_todos_los_motores_arriba():
    datos = client.get('/api/v1/salud/motores').json()
    assert set(datos['motores']) == set(salud.MOTORES)
    assert datos['degradados'] == []
    assert all(valor == 'ok' for valor in datos['motores'].values())


def test_endpoint_reporta_un_motor_caido_sin_exponer_el_error(monkeypatch):
    def caido():
        raise ConnectionError('detalle interno que no debe salir')

    monkeypatch.setitem(salud._PINGS, 'neo4j', caido)
    respuesta = client.get('/api/v1/salud/motores')
    datos = respuesta.json()
    assert datos['motores']['neo4j'] == 'caido'
    assert datos['degradados'] == ['neo4j']
    assert 'detalle interno' not in respuesta.text


def test_busqueda_con_el_circuito_abierto_usa_mongodb_sin_esperar():
    salud.registrar_falla('elasticsearch', 'x', confirmada=True)
    datos = client.get('/api/v1/search', params={'q': 'Laptop'}).json()
    assert datos['degradado'] is True
    assert datos['motor'] == 'mongodb'


def test_un_error_de_infraestructura_alimenta_el_detector():
    from fastapi import Request
    import asyncio
    import redis.exceptions as redis_err

    manejador = app.exception_handlers[redis_err.RedisError]
    peticion = Request({'type': 'http', 'method': 'GET', 'path': '/x', 'headers': [], 'query_string': b''})
    for _ in range(salud.UMBRAL):
        asyncio.run(manejador(peticion, redis_err.ConnectionError('caído')))
    assert salud.estado('redis') == 'caido'


def test_el_sondeo_de_cassandra_no_deja_la_sesion_sin_keyspace():
    # Si el sondeo de salud abría la sesión compartida sin keyspace, el outbox fallaba después.
    from app.core import db_cassandra
    from app.core.config import settings
    db_cassandra._session = None
    salud._ping_cassandra()
    assert db_cassandra.get_cassandra_session().keyspace == settings.CASSANDRA_KEYSPACE
