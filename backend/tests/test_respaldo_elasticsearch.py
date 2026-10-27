"""Plan B de Elasticsearch: búsqueda en MongoDB → copia en MySQL; autocompletado en Redis."""

import pytest
from bson import ObjectId
from elasticsearch import Elasticsearch
from fastapi.testclient import TestClient
from pymongo import MongoClient

from app.core import salud
from app.core.config import settings
from app.core.deps import get_es
from app.core.db_mongo import get_mongo_db
from app.core.db_redis import get_redis
from app.main import app
from app.services import autocompletado_respaldo_service as autocompletado
from app.services.catalogo_respaldo_service import reconstruir_autocompletado

client = TestClient(app)


@pytest.fixture(scope='module', autouse=True)
def indice_construido():
    reconstruir_autocompletado()


@pytest.fixture
def sin_elasticsearch():
    caido = Elasticsearch('http://127.0.0.1:1', request_timeout=0.5, max_retries=0)
    app.dependency_overrides[get_es] = lambda: caido
    yield
    app.dependency_overrides.pop(get_es, None)


@pytest.fixture
def sin_mongo():
    app.dependency_overrides[get_mongo_db] = lambda: MongoClient(
        'mongodb://127.0.0.1:1', serverSelectionTimeoutMS=200)[settings.MONGO_DB]
    yield
    app.dependency_overrides.pop(get_mongo_db, None)


def _sugerir(q):
    respuesta = client.get('/api/v1/search/suggest', params={'q': q})
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()


# ── Índice de prefijos en Redis ───────────────────────────────────────────────

def test_prefijo_sufijo_y_sin_tildes():
    r = get_redis()
    assert any('Laptop' in p['nombre'] for p in autocompletado.sugerir(r, 'lap'))
    assert any('Galaxy' in p['nombre'] for p in autocompletado.sugerir(r, 'galax'))  # palabra intermedia
    assert any('fonos' in p['nombre'] for p in autocompletado.sugerir(r, 'audifonos'))  # sin tilde
    assert autocompletado.sugerir(r, 'hefkjdshafh') == []


def test_actualizar_refleja_renombres_y_retiros():
    r, oid = get_redis(), str(ObjectId())
    try:
        autocompletado.actualizar(r, oid, {'_id': oid, 'nombre': 'Zumbador Cuántico', 'estado': 'activo'})
        assert [p['producto_id'] for p in autocompletado.sugerir(r, 'zumbador')] == [oid]
        assert [p['producto_id'] for p in autocompletado.sugerir(r, 'cuantico')] == [oid]

        autocompletado.actualizar(r, oid, {'_id': oid, 'nombre': 'Xilófono Cuántico', 'estado': 'activo'})
        assert autocompletado.sugerir(r, 'zumbador') == []

        autocompletado.actualizar(r, oid, {'_id': oid, 'nombre': 'Xilófono Cuántico', 'estado': 'inactivo'})
        assert autocompletado.sugerir(r, 'xilofono') == []
    finally:
        autocompletado.actualizar(r, oid, None)


# ── Cadena del autocompletado ─────────────────────────────────────────────────

def test_autocompletado_con_elasticsearch():
    assert _sugerir('lap')['motor'] == 'elasticsearch'


def test_sin_elasticsearch_el_autocompletado_sale_de_redis(sin_elasticsearch):
    datos = _sugerir('galax')
    assert datos['degradado'] is True and datos['motor'] == 'redis'
    assert any('Galaxy' in p['nombre'] for p in datos['productos'])


def test_sin_elasticsearch_ni_redis_sale_de_mongodb(sin_elasticsearch):
    salud.registrar_falla('redis', 'caído', confirmada=True)
    datos = _sugerir('laptop')
    assert datos['motor'] == 'mongodb'
    assert datos['productos']


def test_sin_elasticsearch_redis_ni_mongo_sale_de_mysql(sin_elasticsearch, sin_mongo):
    salud.registrar_falla('redis', 'caído', confirmada=True)
    datos = _sugerir('laptop')
    assert datos['motor'] == 'mysql'
    assert all('laptop' in p['nombre'].lower() for p in datos['productos'])


# ── Búsqueda completa ─────────────────────────────────────────────────────────

def test_busqueda_sin_elasticsearch_ni_mongo_sale_de_mysql(sin_elasticsearch, sin_mongo):
    datos = client.get('/api/v1/search', params={'q': 'Laptop'}).json()
    assert datos['degradado'] is True and datos['motor'] == 'mysql'
    assert datos['items']
    assert all('laptop' in item['nombre'].lower() for item in datos['items'])
    assert all('precio' in item for item in datos['items'])


def test_texto_sin_coincidencias_sin_elasticsearch_ni_mongo_muestra_populares(sin_elasticsearch, sin_mongo):
    datos = client.get('/api/v1/search', params={'q': 'hefkjdshafh'}).json()
    assert datos['motor'] == 'mysql'
    assert datos['sin_coincidencias'] is True and datos['items']
