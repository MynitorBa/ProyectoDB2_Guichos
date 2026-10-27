"""Plan B de MySQL: modo de solo lectura y pedidos en cola sin cobrar.

MySQL «caído» combina dos cosas: el circuito abierto (los caminos que lo
consultan primero van directo al respaldo) y una sesión de SQLAlchemy contra
un puerto sin servidor (lo que intente MySQL falla como con el contenedor
detenido). La base real de las demás pruebas no se toca.
"""

from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core import salud
from app.core.db_mongo import get_mongo_db
from app.core.db_mysql import get_db
from app.core.db_redis import get_redis
from app.main import app
from app.services import cola_pedidos_service as cola
from app.services import lectura_respaldo_service as lectura
from app.services import redis_cart_service as rcs
from tests.test_checkout import (  # noqa: F401  (reset_stock limpia los pedidos creados)
    DIRECCION_ID, METODO_PAGO_ID, OFERTA_TEST_ID, TestSession, USUARIO_COMPRADOR_ID, reset_stock,
)

USUARIO = USUARIO_COMPRADOR_ID
_muerto = sessionmaker(bind=create_engine(
    'mysql+pymysql://nadie:nada@127.0.0.1:1/tiendaya', connect_args={'connect_timeout': 1},
))


def _db_caida():
    sesion = _muerto()
    try:
        yield sesion
    finally:
        sesion.close()


def _token(cliente: TestClient) -> dict:
    token = cliente.post('/api/v1/auth/login', json={
        'email': 'comprador1@gmail.com', 'password': 'password123',
    }).json()['access_token']
    return {'Authorization': f'Bearer {token}'}


def _limpiar_cola():
    r = get_redis()
    for solicitud_id in r.lrange(f'cola_pedidos:usuario:{USUARIO}', 0, -1):
        r.lrem(cola.PENDIENTES, 0, solicitud_id)
        r.delete(cola._clave(solicitud_id))
    r.delete(f'cola_pedidos:usuario:{USUARIO}')


@pytest.fixture
def cliente():
    """Cliente autenticado (con MySQL arriba) y carrito y cola limpios."""
    c = TestClient(app)
    encabezados = _token(c)
    c.get('/api/v1/auth/me', headers=encabezados)          # deja la copia del perfil
    c.get('/api/v1/addresses/', headers=encabezados)       # y la de direcciones
    c.get('/api/v1/categories/')                           # y la de categorías
    c.headers.update(encabezados)
    r = get_redis()
    guardado = r.hgetall(rcs._key(USUARIO))
    r.delete(rcs._key(USUARIO))
    _limpiar_cola()
    yield c
    app.dependency_overrides.pop(get_db, None)
    r.delete(rcs._key(USUARIO))
    if guardado:
        r.hset(rcs._key(USUARIO), mapping=guardado)
    _limpiar_cola()


def _mysql_caido():
    salud.registrar_falla('mysql', 'caído', confirmada=True)
    app.dependency_overrides[get_db] = _db_caida


# ── Copias de lectura ─────────────────────────────────────────────────────────

def test_consultar_guarda_copia_y_la_sirve_sin_mysql():
    assert lectura.consultar('prueba:plan_b', lambda: {'valor': 1}) == {'valor': 1}
    salud.registrar_falla('mysql', 'caído', confirmada=True)
    assert lectura.consultar('prueba:plan_b', lambda: pytest.fail('no debe consultar MySQL')) == {'valor': 1}
    with pytest.raises(lectura.MySQLNoDisponible):
        lectura.consultar('prueba:sin_copia', lambda: None)


def test_sesion_perfil_categorias_y_direcciones_sin_mysql(cliente):
    _mysql_caido()
    perfil = cliente.get('/api/v1/auth/me')
    assert perfil.status_code == 200 and perfil.json()['id'] == USUARIO
    assert cliente.get('/api/v1/categories/').json()
    assert any(d['id'] == DIRECCION_ID for d in cliente.get('/api/v1/addresses/').json())
    # Sin roles mientras tanto: lo de administración queda fuera.
    assert cliente.get('/api/v1/reviews/admin/fraude/resumen').status_code == 403


def test_un_token_invalido_sigue_rechazado_sin_mysql(cliente):
    _mysql_caido()
    assert cliente.get('/api/v1/auth/me', headers={'Authorization': 'Bearer falso'}).status_code == 401


# ── Catálogo con precios referenciales ───────────────────────────────────────

def test_catalogo_detalle_y_busqueda_sin_mysql(cliente):
    _mysql_caido()
    listado = cliente.get('/api/v1/products/', params={'page_size': 50}).json()
    assert listado['total'] > 0
    assert all(item['precio_referencial'] for item in listado['items'])
    con_precio = next(item for item in listado['items'] if item.get('oferta_id'))
    assert con_precio['precio'] is not None

    detalle = cliente.get(f"/api/v1/products/{con_precio['_id']}").json()
    assert detalle['precio_referencial'] is True
    assert [o['oferta_id'] for o in detalle['ofertas']] == [con_precio['oferta_id']]

    busqueda = cliente.get('/api/v1/search', params={'q': 'laptop'}).json()
    assert busqueda['items'] and all(i['precio_referencial'] for i in busqueda['items'])


# ── Carrito y pedidos en cola ─────────────────────────────────────────────────

def _oferta_principal() -> tuple[int, Decimal]:
    doc = get_mongo_db().productos.find_one({'estado': 'activo', 'oferta_id': {'$ne': None}, 'disponible': True})
    return int(doc['oferta_id']), Decimal(str(doc['precio']))


def test_carrito_y_checkout_sin_mysql_dejan_el_pedido_en_cola(cliente):
    oferta_id, precio = _oferta_principal()
    _mysql_caido()
    agregado = cliente.post('/api/v1/cart/items', json={'oferta_id': oferta_id, 'cantidad': 2})
    assert agregado.status_code == 201, agregado.text
    carrito = cliente.get('/api/v1/cart/').json()
    assert carrito['solo_lectura'] is True and carrito['total'] == float(precio * 2)

    clave = str(uuid4())
    cuerpo = {'direccion_id': DIRECCION_ID, 'metodo_pago_id': METODO_PAGO_ID}
    primera = cliente.post('/api/v1/orders/checkout', json=cuerpo, headers={'Idempotency-Key': clave})
    assert primera.status_code == 202, primera.text
    assert primera.json()['codigo'] == 'ORDER_QUEUED'

    repetida = cliente.post('/api/v1/orders/checkout', json=cuerpo, headers={'Idempotency-Key': clave})
    assert repetida.json()['solicitud_id'] == primera.json()['solicitud_id']
    otra = cliente.post('/api/v1/orders/checkout', json=cuerpo, headers={'Idempotency-Key': str(uuid4())})
    assert otra.status_code == 409 and otra.json()['detail']['code'] == 'ORDER_ALREADY_QUEUED'

    [solicitud] = cliente.get('/api/v1/orders/cola').json()
    assert solicitud['estado'] == 'en_cola'
    assert solicitud['items'] == [{'oferta_id': oferta_id, 'cantidad': 2, 'precio_al_agregar': str(precio)}]


def test_las_ofertas_flash_no_pueden_quedar_en_cola():
    with pytest.raises(cola.SolicitudInvalida) as error:
        cola.encolar(get_redis(), usuario_id=USUARIO, items=[
            {'oferta_id': 1, 'cantidad': 1, 'precio_al_agregar': '1.00', 'promocion_flash_id': 3},
        ], direccion_id=DIRECCION_ID, metodo_pago_id=METODO_PAGO_ID, idempotency_key=None)
    assert error.value.codigo == 'FLASH_REQUIRES_DATABASE'


def _precio_actual() -> Decimal:
    with TestSession() as db:
        return Decimal(db.execute(text('SELECT precio_actual FROM ofertas WHERE id = :o'),
                                  {'o': OFERTA_TEST_ID}).scalar_one())


def test_al_volver_mysql_la_cola_pasa_por_la_saga_y_se_confirma(cliente, reset_stock):
    r = get_redis()
    solicitud = cola.encolar(r, usuario_id=USUARIO, items=[
        {'oferta_id': OFERTA_TEST_ID, 'cantidad': 1, 'precio_al_agregar': str(_precio_actual())},
    ], direccion_id=DIRECCION_ID, metodo_pago_id=METODO_PAGO_ID, idempotency_key=None)

    assert cola.procesar_pendientes(r) == 1
    procesada = cola.obtener(r, solicitud['id'])
    reset_stock.append(procesada['pedido_id'])
    assert procesada['estado'] == 'procesado'
    with TestSession() as db:
        estado = db.execute(text('SELECT estado FROM pedidos WHERE id = :p'),
                            {'p': procesada['pedido_id']}).scalar_one()
        avisos = db.execute(text("SELECT COUNT(*) FROM notificaciones WHERE pedido_id = :p "
                                 "AND tipo = 'pedido_en_cola'"), {'p': procesada['pedido_id']}).scalar_one()
    assert estado == 'confirmado' and avisos == 1
    assert r.llen(cola.PENDIENTES) == 0 or solicitud['id'] not in r.lrange(cola.PENDIENTES, 0, -1)


def test_si_el_precio_cambio_no_se_cobra_y_requiere_atencion(cliente, reset_stock):
    r = get_redis()
    solicitud = cola.encolar(r, usuario_id=USUARIO, items=[
        {'oferta_id': OFERTA_TEST_ID, 'cantidad': 1, 'precio_al_agregar': str(_precio_actual() - 1)},
    ], direccion_id=DIRECCION_ID, metodo_pago_id=METODO_PAGO_ID, idempotency_key=None)
    try:
        cola.procesar_pendientes(r)
        procesada = cola.obtener(r, solicitud['id'])
        assert procesada['estado'] == 'requiere_atencion'
        assert procesada['codigo'] == 'PRICE_CHANGED'
        with TestSession() as db:
            assert db.execute(text('SELECT COUNT(*) FROM pedidos WHERE clave_idempotencia = :c'),
                              {'c': solicitud['clave_idempotencia']}).scalar_one() == 0
    finally:
        with TestSession() as db:
            db.execute(text("DELETE FROM notificaciones WHERE usuario_id = :u AND tipo = 'pedido_en_cola' "
                            "AND pedido_id IS NULL"), {'u': USUARIO})
            db.commit()


def test_sin_mysql_el_procesamiento_se_detiene_y_la_solicitud_espera(cliente, monkeypatch):
    r = get_redis()
    solicitud = cola.encolar(r, usuario_id=USUARIO, items=[
        {'oferta_id': OFERTA_TEST_ID, 'cantidad': 1, 'precio_al_agregar': '1.00'},
    ], direccion_id=DIRECCION_ID, metodo_pago_id=METODO_PAGO_ID, idempotency_key=None)
    import app.core.db_mysql as db_mysql
    monkeypatch.setattr(db_mysql, 'SessionLocal', _muerto)
    assert cola.procesar_pendientes(r) == 0
    assert cola.obtener(r, solicitud['id'])['estado'] == 'en_cola'
    assert solicitud['id'] in r.lrange(cola.PENDIENTES, 0, -1)
