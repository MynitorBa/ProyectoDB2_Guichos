"""Plan B de MongoDB: el catálogo se lee de su copia en MySQL (y de Elasticsearch).

MongoDB «caído» es un cliente real apuntando a un puerto sin servidor, con un
tiempo de espera corto: falla igual que con el contenedor detenido, sin
detener la base que usan las demás pruebas.
"""

import pytest
from bson import ObjectId
from fastapi.testclient import TestClient
from pymongo import MongoClient
from sqlalchemy import text

from app.core import salud
from app.core.config import settings
from app.core.db_mongo import get_mongo_db
from app.core.db_mysql import SessionLocal
from app.main import app
from app.services import catalogo_respaldo_service as respaldo
from app.services.outbox_service import destinos_de

client = TestClient(app)


def _mongo_caido():
    return MongoClient('mongodb://127.0.0.1:1', serverSelectionTimeoutMS=200)[settings.MONGO_DB]


@pytest.fixture
def sin_mongo():
    app.dependency_overrides[get_mongo_db] = _mongo_caido
    yield
    app.dependency_overrides.pop(get_mongo_db, None)


@pytest.fixture(scope='module', autouse=True)
def copia_al_dia():
    with SessionLocal() as db:
        respaldo.reconciliar(get_mongo_db(), db)
        db.commit()


def _producto_con_oferta() -> str:
    with SessionLocal() as db:
        return db.execute(text("""
            SELECT o.producto_ref FROM ofertas o
            WHERE o.estado = 'activa' AND o.producto_ref IS NOT NULL ORDER BY o.id LIMIT 1
        """)).scalar_one()


def _fila(coleccion: str, ref: str):
    with SessionLocal() as db:
        return db.execute(text(
            'SELECT estado FROM catalogo_respaldo WHERE coleccion = :c AND ref = :r'
        ), {'c': coleccion, 'r': ref}).first()


# ── La copia ──────────────────────────────────────────────────────────────────

def test_la_copia_tiene_todo_el_catalogo_y_reconciliar_es_idempotente():
    mongo = get_mongo_db()
    with SessionLocal() as db:
        assert respaldo.reconciliar(mongo, db) == {'copiados': 0, 'retirados': 0}
        total = db.execute(text(
            "SELECT COUNT(*) FROM catalogo_respaldo WHERE coleccion = 'productos'"
        )).scalar_one()
    assert total == mongo.productos.count_documents({})


def test_copiar_producto_sigue_cambios_y_eliminaciones():
    mongo, oid, vid = get_mongo_db(), ObjectId(), ObjectId()
    mongo.productos.insert_one({'_id': oid, 'nombre': 'Temporal plan B', 'estado': 'activo'})
    mongo.producto_variantes.insert_one({'_id': vid, 'producto_ref': str(oid), 'estado': 'activa'})
    try:
        with SessionLocal() as db:
            respaldo.copiar_producto(mongo, db, str(oid))
            db.commit()
        assert _fila('productos', str(oid)).estado == 'activo'
        assert _fila('producto_variantes', str(vid)) is not None

        mongo.productos.update_one({'_id': oid}, {'$set': {'estado': 'inactivo'}})
        mongo.producto_variantes.delete_one({'_id': vid})
        with SessionLocal() as db:
            respaldo.copiar_producto(mongo, db, str(oid))
            db.commit()
        assert _fila('productos', str(oid)).estado == 'inactivo'
        assert _fila('producto_variantes', str(vid)) is None

        mongo.productos.delete_one({'_id': oid})
        with SessionLocal() as db:
            respaldo.copiar_producto(mongo, db, str(oid))
            db.commit()
        assert _fila('productos', str(oid)) is None
    finally:
        mongo.productos.delete_one({'_id': oid})
        mongo.producto_variantes.delete_one({'_id': vid})
        with SessionLocal() as db:
            db.execute(text('DELETE FROM catalogo_respaldo WHERE ref IN (:a, :b)'), {'a': str(oid), 'b': str(vid)})
            db.commit()


def test_las_ediciones_del_catalogo_llegan_a_la_copia_por_el_outbox():
    assert 'catalogo' in destinos_de('producto.catalogo_actualizado')


def test_la_copia_conserva_los_tipos_de_mongodb():
    ref = _producto_con_oferta()
    original = get_mongo_db().productos.find_one({'_id': ObjectId(ref)})
    copia, _ = respaldo.productos_por_ids(_mongo_caido(), [ref])
    assert copia[ref] == original


# ── La tienda con MongoDB caído ───────────────────────────────────────────────

def test_listado_sin_mongo_sale_de_la_copia_con_precio_de_mysql(sin_mongo):
    datos = client.get('/api/v1/products/', params={'page_size': 50}).json()
    assert datos['catalogo_respaldo'] is True
    assert datos['total'] > 0
    assert all(item['estado'] == 'activo' for item in datos['items'])
    assert any('precio' in item for item in datos['items'])
    assert salud._estado('mongo').fallas >= 1  # la falla alimentó el detector


def test_detalle_sin_mongo_incluye_ofertas_y_variantes(sin_mongo):
    ref = _producto_con_oferta()
    respuesta = client.get(f'/api/v1/products/{ref}')
    assert respuesta.status_code == 200, respuesta.text
    datos = respuesta.json()
    assert datos['catalogo_respaldo'] is True
    assert datos['ofertas'] and 'variantes' in datos


def test_filtro_de_categoria_y_texto_sin_mongo(sin_mongo):
    con_mongo = client.get('/api/v1/products/', params={'categoria': 'computadoras', 'page_size': 100})
    app.dependency_overrides.pop(get_mongo_db, None)
    salud.reiniciar()
    real = client.get('/api/v1/products/', params={'categoria': 'computadoras', 'page_size': 100}).json()
    assert con_mongo.json()['total'] == real['total']

    app.dependency_overrides[get_mongo_db] = _mongo_caido
    texto = client.get('/api/v1/products/', params={'q': 'laptop', 'page_size': 100}).json()
    assert texto['total'] >= 1
    assert all('laptop' in item['nombre'].lower() for item in texto['items'])


def test_busqueda_con_elasticsearch_y_sin_mongo_hidrata_desde_la_copia(sin_mongo):
    datos = client.get('/api/v1/search', params={'q': 'Laptop'}).json()
    assert datos['motor'] == 'elasticsearch'
    assert datos['items']


def test_recomendaciones_sin_mongo_no_fallan(sin_mongo):
    respuesta = client.get(f'/api/v1/products/{_producto_con_oferta()}/recommendations')
    assert respuesta.status_code == 200


# ── Último recurso: Elasticsearch ─────────────────────────────────────────────

def test_un_producto_que_aun_no_esta_en_la_copia_sale_de_elasticsearch():
    ref = _producto_con_oferta()
    with SessionLocal() as db:
        db.execute(text("DELETE FROM catalogo_respaldo WHERE coleccion = 'productos' AND ref = :r"), {'r': ref})
        db.commit()
    try:
        docs, desde_respaldo = respaldo.productos_por_ids(_mongo_caido(), [ref])
        assert desde_respaldo
        assert docs[ref]['nombre']
        assert docs[ref]['_id'] == ObjectId(ref)
    finally:
        with SessionLocal() as db:
            respaldo.copiar_producto(get_mongo_db(), db, ref)
            db.commit()
