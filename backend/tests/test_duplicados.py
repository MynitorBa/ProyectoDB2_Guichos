"""Aviso de posibles duplicados al proponer un producto nuevo (Entrega 4)."""

import pytest
from elasticsearch import Elasticsearch
from fastapi.testclient import TestClient

from app.core import salud
from app.core.db_elastic import get_es as cliente_es
from app.core.db_mysql import SessionLocal
from app.core.deps import get_es
from app.main import app
from app.models.solicitud_catalogo import SolicitudCatalogo
from app.models.usuario import Usuario
from app.models.vendedor import Vendedor
from app.services import duplicados_service as duplicados

client = TestClient(app)


def _cliente(email: str) -> TestClient:
    cliente = TestClient(app)
    token = cliente.post('/api/v1/auth/login', json={'email': email, 'password': 'password123'}).json()['access_token']
    cliente.headers['Authorization'] = f'Bearer {token}'
    return cliente


@pytest.fixture(scope='module')
def vendedor():
    return _cliente('vendedor1@tiendaya.gt')


@pytest.fixture(scope='module')
def admin():
    return _cliente('admin@tiendaya.gt')


def _buscar(**datos):
    return duplicados.posibles_duplicados(cliente_es(), **datos)


def test_el_mismo_producto_escrito_distinto_es_muy_probable():
    encontrados = _buscar(nombre='Laptop Dell Inspiron 15', categorias=['Computadoras'],
                          descripcion='Laptop con procesador Intel Core i5, 8GB RAM y SSD de 512GB')
    assert encontrados[0]['nombre'] == 'Laptop Dell Inspiron 15'
    assert encontrados[0]['nivel'] == 'muy_probable'


@pytest.mark.parametrize('nombre, descripcion, categoria, esperado', [
    ('Audifonos Sony WH1000XM5', 'Audífonos inalámbricos con cancelación de ruido', 'Audio', 'Audífonos Sony'),
    ('Licuadora Oster 600 W', 'Licuadora de 10 velocidades', 'Hogar', 'Licuadora Oster'),
    ('Samsung Galaxy A54 5G 128GB', 'Celular Samsung', 'Celulares', 'Samsung Galaxy A54'),
])
def test_detecta_variaciones_de_escritura(nombre, descripcion, categoria, esperado):
    encontrados = _buscar(nombre=nombre, descripcion=descripcion, categorias=[categoria])
    assert encontrados and encontrados[0]['nombre'].startswith(esperado)
    assert encontrados[0]['similitud'] >= duplicados.UMBRAL_POSIBLE


@pytest.mark.parametrize('nombre, descripcion, categoria', [
    ('Taza de cerámica con diseño maya', 'Taza artesanal guatemalteca', 'Hogar'),
    ('Bicicleta de montaña aro 29', 'Bicicleta con 21 velocidades', 'Deportes'),
    ('Audífonos Bose QuietComfort 45', 'Audífonos bluetooth con cancelación de ruido', 'Audio'),
])
def test_productos_nuevos_de_verdad_no_dan_aviso(nombre, descripcion, categoria):
    assert _buscar(nombre=nombre, descripcion=descripcion, categorias=[categoria]) == []


def test_sin_servicio_de_embeddings_no_hay_aviso():
    salud.registrar_falla('embeddings', 'caído', confirmada=True)
    try:
        assert _buscar(nombre='Laptop Dell Inspiron 15') == []
    finally:
        salud.reiniciar()


def test_endpoint_del_vendedor(vendedor):
    respuesta = vendedor.post('/api/v1/vendor/catalog-requests/products/duplicados', json={
        'nombre': 'Laptop Dell Inspiron 15', 'categoria_slugs': ['computadoras'],
    })
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()['duplicados'][0]['nombre'] == 'Laptop Dell Inspiron 15'
    # Solo vendedores.
    assert client.post('/api/v1/vendor/catalog-requests/products/duplicados',
                       json={'nombre': 'Laptop'}).status_code in (401, 403)


def test_endpoint_del_vendedor_sin_elasticsearch(vendedor):
    app.dependency_overrides[get_es] = lambda: Elasticsearch('http://127.0.0.1:1', request_timeout=0.5, max_retries=0)
    try:
        respuesta = vendedor.post('/api/v1/vendor/catalog-requests/products/duplicados',
                                  json={'nombre': 'Licuadora Oster 600 W'})
    finally:
        app.dependency_overrides.pop(get_es, None)
    assert respuesta.status_code == 200 and respuesta.json() == {'duplicados': []}


@pytest.fixture
def solicitud_pendiente():
    with SessionLocal() as db:
        vendedor_id = db.query(Vendedor.id).join(Usuario, Usuario.id == Vendedor.usuario_id) \
            .filter(Usuario.email == 'vendedor1@tiendaya.gt').scalar()
        solicitud = SolicitudCatalogo(
            vendedor_id=vendedor_id, tipo='producto_nuevo', estado='pendiente',
            nombre='Audifonos Sony WH1000XM5', descripcion='Audífonos inalámbricos con cancelación de ruido',
            atributos={}, precio_propuesto=100, stock_propuesto=1,
        )
        db.add(solicitud)
        db.commit()
        solicitud_id = solicitud.id
    yield solicitud_id
    with SessionLocal() as db:
        db.query(SolicitudCatalogo).filter_by(id=solicitud_id).delete()
        db.commit()


def test_el_admin_ve_los_posibles_duplicados_al_revisar(admin, solicitud_pendiente):
    detalle = admin.get(f'/api/v1/admin/catalog-requests/{solicitud_pendiente}').json()
    assert detalle['posibles_duplicados'][0]['nombre'].startswith('Audífonos Sony')


def test_parecido_de_nombres_ignora_tildes_y_signos():
    assert duplicados.parecido_nombres('Laptop Dell Inspiron 15', 'laptop dell inspiron 15') == 1
    assert duplicados.parecido_nombres('Audífonos Sony', 'Audifonos, SONY') == 1
    assert duplicados.parecido_nombres('Laptop HP Envy 13', 'Laptop HP Pavilion 14') < duplicados.NOMBRE_POSIBLE
    assert duplicados.parecido_nombres('', 'Algo') == 0


@pytest.mark.parametrize('nombre, esperado', [
    ('Audifonos Sony WH1000XM5', 'Audífonos Sony'),   # cambia el guion y la tilde
    ('Licuadora Oster 600 W', 'Licuadora Oster'),      # cambia un espacio
    ('Dell Inspiron 15 3520 laptop', 'Laptop Dell'),   # cambia el orden
])
def test_solo_con_el_nombre_tambien_avisa(nombre, esperado):
    encontrados = _buscar(nombre=nombre)
    assert encontrados and encontrados[0]['nombre'].startswith(esperado)


def test_la_misma_familia_no_se_confunde_por_el_nombre():
    assert duplicados.parecido_nombres('Samsung Galaxy S23 Ultra', 'Samsung Galaxy A54') < duplicados.NOMBRE_POSIBLE
