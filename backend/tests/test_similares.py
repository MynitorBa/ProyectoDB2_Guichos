"""«También te podría interesar»: productos similares por vector (Entrega 4)."""

import pytest
from elasticsearch import Elasticsearch
from fastapi.testclient import TestClient

from app.core.db_mongo import get_mongo_db
from app.core.db_redis import get_redis
from app.core.deps import get_es
from app.main import app
from app.services import similares_service

client = TestClient(app)


@pytest.fixture
def laptop() -> str:
    """Laptop Dell Inspiron 15, por SKU (otras pruebas la reindexan)."""
    return str(get_mongo_db().productos.find_one({'sku': 'TECH-LAP-001'}, {'_id': 1})['_id'])


@pytest.fixture(autouse=True)
def sin_cache(laptop):
    get_redis().delete(similares_service._clave(laptop))
    yield
    get_redis().delete(similares_service._clave(laptop))


def _similares(ref, **params):
    respuesta = client.get(f'/api/v1/products/{ref}/similares', params=params)
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()


def test_devuelve_productos_parecidos_por_vector(laptop):
    datos = _similares(laptop)
    assert datos['origen'] == 'vectores'
    assert 0 < len(datos['items']) <= 8
    refs = [p['_id'] for p in datos['items']]
    assert laptop not in refs and len(refs) == len(set(refs))
    assert all(p['disponible'] and 0 < p['similitud'] <= 1 for p in datos['items'])
    similitudes = [p['similitud'] for p in datos['items']]
    assert similitudes == sorted(similitudes, reverse=True)
    # Entre los parecidos a una laptop hay otra laptop (la calidad se mide en la fase 7).
    assert any('laptop' in p['nombre'].lower() for p in datos['items'])


def test_no_repite_lo_que_ya_muestra_la_seccion_de_compras(laptop):
    primeros = [p['_id'] for p in _similares(laptop, limite=3)['items']]
    siguientes = _similares(laptop, limite=3, excluir=','.join(primeros))['items']
    assert siguientes and not {p['_id'] for p in siguientes} & set(primeros)


def test_los_vecinos_se_guardan_en_redis(laptop):
    _similares(laptop)
    guardados = get_redis().get(similares_service._clave(laptop))
    assert guardados and laptop not in guardados
    assert get_redis().ttl(similares_service._clave(laptop)) <= similares_service.CACHE_SEGUNDOS


def test_sin_elasticsearch_responde_con_los_mas_vendidos(laptop):
    caido = Elasticsearch('http://127.0.0.1:1', request_timeout=0.5, max_retries=0)
    app.dependency_overrides[get_es] = lambda: caido
    try:
        datos = _similares(laptop)
    finally:
        app.dependency_overrides.pop(get_es, None)
    assert datos['origen'] in ('mas_vendidos', None)
    assert all('similitud' not in p and p['_id'] != laptop for p in datos['items'])


def test_producto_inexistente_no_falla():
    assert _similares('000000000000000000000000') == {'items': [], 'origen': None}
