"""«Te podría interesar» del inicio: vecinos por vector de lo visto y el carrito (Entrega 4)."""

import json
import secrets

import pytest
from elasticsearch import Elasticsearch
from fastapi.testclient import TestClient

from app.core.db_elastic import get_es as cliente_es
from app.core.db_mongo import get_mongo_db
from app.core.db_mysql import SessionLocal
from app.core.db_redis import get_redis
from app.core.deps import get_es
from app.main import app
from app.services import para_ti_service as para_ti

client = TestClient(app)
USUARIO_PRUEBA = 9900002  # sin fila en MySQL: solo se usan sus claves de Redis


def _ref(sku: str) -> str:
    # Por SKU en MongoDB: otras pruebas reindexan estos productos y el índice
    # puede tardar un instante en volver a encontrarlos por nombre.
    return str(get_mongo_db().productos.find_one({'sku': sku}, {'_id': 1})['_id'])


@pytest.fixture
def laptop() -> str:
    return _ref('TECH-LAP-001')  # Laptop Dell Inspiron 15


@pytest.fixture
def audifonos() -> str:
    return _ref('TECH-AUD-001')  # Audífonos Sony


@pytest.fixture
def claves_limpias():
    r = get_redis()
    claves = [f'vistos:{USUARIO_PRUEBA}', f'carrito:{USUARIO_PRUEBA}']
    r.delete(*claves)
    yield r
    r.delete(*claves)


def _para_ti(**params):
    respuesta = client.get('/api/v1/products/para-ti', params=params)
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()


def test_sin_historial_no_hay_recomendaciones():
    assert _para_ti() == {'items': [], 'origen': None, 'semillas': 0}


def test_lo_visto_en_el_navegador_trae_productos_parecidos(laptop):
    datos = _para_ti(vistos=laptop)
    assert datos['origen'] == 'vectores' and datos['semillas'] == 1
    refs = [p['_id'] for p in datos['items']]
    assert laptop not in refs and 0 < len(refs) <= 8
    assert any('laptop' in p['nombre'].lower() for p in datos['items'])
    assert all(p['disponible'] for p in datos['items'])


def test_cada_interes_aporta_sus_vecinos(laptop, audifonos):
    nombres = ' '.join(p['nombre'].lower() for p in _para_ti(vistos=f'{audifonos},{laptop}')['items'])
    assert 'laptop' in nombres or 'macbook' in nombres
    assert 'airpods' in nombres or 'bocina' in nombres


def test_ignora_identificadores_invalidos():
    assert _para_ti(vistos='abc,../../etc,<script>')['semillas'] == 0


def test_el_carrito_pesa_mas_que_lo_visto_y_lo_reciente_mas_que_lo_antiguo():
    elegidas = para_ti.semillas(['a' * 24, 'b' * 24, 'c' * 24], ['d' * 24])
    assert elegidas[0] == ('d' * 24, para_ti.PESO_CARRITO)
    assert [ref[0] for ref in elegidas[1:]] == ['a' * 24, 'b' * 24, 'c' * 24]
    assert elegidas[1][1] > elegidas[2][1] > elegidas[3][1]


def test_historial_y_carrito_en_redis(claves_limpias, laptop, audifonos):
    r = claves_limpias
    for ref in (laptop, audifonos, laptop):
        assert para_ti.registrar_visto(r, USUARIO_PRUEBA, ref)
    # Sin repetidos y lo último visto al frente.
    assert r.lrange(f'vistos:{USUARIO_PRUEBA}', 0, -1) == [laptop, audifonos]
    assert r.ttl(f'vistos:{USUARIO_PRUEBA}') > 0
    r.hset(f'carrito:{USUARIO_PRUEBA}', '1', json.dumps({'cantidad': 1, 'producto_ref': audifonos}))
    r.expire(f'carrito:{USUARIO_PRUEBA}', 100)
    with SessionLocal() as db:
        datos = para_ti.recomendar(db, get_mongo_db(), cliente_es(), r, usuario_id=USUARIO_PRUEBA)
    assert datos['semillas'] == 2 and datos['items']
    assert not {laptop, audifonos} & {p['_id'] for p in datos['items']}
    # Leer el carrito para recomendar no renueva su TTL.
    assert r.ttl(f'carrito:{USUARIO_PRUEBA}') <= 100


def test_registrar_visto_requiere_sesion(laptop):
    assert client.post(f'/api/v1/products/{laptop}/visto').status_code in (401, 403)


def test_registrar_visto_con_sesion(laptop):
    cliente = TestClient(app)
    token = cliente.post('/api/v1/auth/login', json={
        'email': 'comprador1@gmail.com', 'password': 'password123',
    }).json()['access_token']
    cliente.headers['Authorization'] = f'Bearer {token}'
    usuario_id = cliente.get('/api/v1/auth/me').json()['id']
    r, clave = get_redis(), f'vistos:{usuario_id}'
    previos = r.lrange(clave, 0, -1)
    try:
        assert cliente.post(f'/api/v1/products/{laptop}/visto').status_code == 204
        assert r.lindex(clave, 0) == laptop
        datos = cliente.get('/api/v1/products/para-ti').json()
        assert datos['origen'] == 'vectores' and laptop not in {p['_id'] for p in datos['items']}
    finally:
        r.delete(clave)
        if previos:
            r.rpush(clave, *previos)


def test_sin_elasticsearch_no_falla(laptop):
    caido = Elasticsearch('http://127.0.0.1:1', request_timeout=0.5, max_retries=0)
    app.dependency_overrides[get_es] = lambda: caido
    try:
        # Una semilla al azar evita que la caché de 10 minutos oculte la falla.
        datos = _para_ti(vistos=f'{laptop},{secrets.token_hex(12)}')
    finally:
        app.dependency_overrides.pop(get_es, None)
    assert datos['items'] == [] and datos['origen'] is None
