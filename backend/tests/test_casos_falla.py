"""Casos de falla específicos del laboratorio («¿qué pasa si Redis se cae justo al comprar?»).

Cada prueba arma el punto de falla del caso (``casos_falla_service``) y hace la
operación real por la API, como el navegador. El punto lanza el mismo error
que el driver del motor caído, en el instante exacto del caso, así que se
ejecuta el camino de recuperación de una caída real sin detener contenedores.
"""

import time
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core import fault_injection, salud
from app.core.db_mongo import get_mongo_db
from app.core.db_redis import get_redis
from app.core.time import utc_now
from app.main import app
from app.models.outbox import OutboxEvento
from app.models.pago import Pago
from app.models.pedido import Pedido, PedidoLinea
from app.models.promocion_flash import PromocionFlash, ReservaFlash
from app.services import casos_falla_service as casos
from app.services import cola_pedidos_service as cola
from app.services import flash_sale_service as flash
from app.services import redis_cart_service as rcs
from app.services.flash_sale_worker import resincronizar_pendientes
from app.services.outbox_service import project_event
from tests.conftest import URL_PASARELA
from tests.test_checkout import (  # noqa: F401  (reset_stock restaura el stock y borra los pedidos creados)
    DIRECCION_ID, METODO_PAGO_ID, OFERTA_TEST_ID, TestSession, USUARIO_COMPRADOR_ID, reset_stock,
)

USUARIO = USUARIO_COMPRADOR_ID
COMPRA = {'direccion_id': DIRECCION_ID, 'metodo_pago_id': METODO_PAGO_ID}


# ── Utilidades ────────────────────────────────────────────────────────────────

def _limpiar_cola():
    r = get_redis()
    for solicitud_id in r.lrange(f'cola_pedidos:usuario:{USUARIO}', 0, -1):
        r.lrem(cola.PENDIENTES, 0, solicitud_id)
        r.delete(cola._clave(solicitud_id))
    r.delete(f'cola_pedidos:usuario:{USUARIO}')


def _vaciar_carrito():
    get_redis().delete(rcs._key(USUARIO))
    with TestSession() as db:
        db.execute(text('DELETE FROM carritos_respaldo WHERE usuario_id = :u'), {'u': USUARIO})
        db.commit()


@pytest.fixture
def cliente(reset_stock):
    """Comprador autenticado con el carrito y la cola vacíos y ningún punto de falla activo."""
    c = TestClient(app, raise_server_exceptions=False)
    token = c.post('/api/v1/auth/login', json={
        'email': 'comprador1@gmail.com', 'password': 'password123',
    }).json()['access_token']
    c.headers['Authorization'] = f'Bearer {token}'
    r = get_redis()
    guardado = r.hgetall(rcs._key(USUARIO))
    _vaciar_carrito()
    _limpiar_cola()
    fault_injection.desactivar()
    yield c
    fault_injection.desactivar()
    salud.reiniciar()
    _vaciar_carrito()
    _limpiar_cola()
    if guardado:
        r.hset(rcs._key(USUARIO), mapping=guardado)


def _preparar(caso_id: str) -> None:
    """Como el botón «Preparar» del laboratorio: entorno limpio y los puntos del caso armados."""
    caso = casos.preparar(caso_id)
    assert caso['armado'] and caso['disparos'] == 0


def _disparos(caso_id: str) -> int:
    return next(c for c in casos.listar() if c['id'] == caso_id)['disparos']


def _agregar(c: TestClient, cantidad: int = 1) -> None:
    respuesta = c.post('/api/v1/cart/items', json={'oferta_id': OFERTA_TEST_ID, 'cantidad': cantidad})
    assert respuesta.status_code == 201, respuesta.text


def _comprar(c: TestClient, clave: str | None = None):
    return c.post('/api/v1/orders/checkout', json=COMPRA, headers={'Idempotency-Key': clave or str(uuid4())})


def _inventario() -> tuple[int, int]:
    with TestSession() as db:
        return tuple(db.execute(text("""
            SELECT cantidad_disponible, cantidad_reservada FROM inventario
            WHERE oferta_id = :o AND bodega = 'principal'
        """), {'o': OFERTA_TEST_ID}).one())


def _pedidos_del_usuario() -> int:
    with TestSession() as db:
        return db.query(Pedido).filter_by(usuario_id=USUARIO).count()


def _verificar_un_cobro(pedido_id: int) -> None:
    """El pedido quedó confirmado con un solo pago aprobado y un solo cargo en la pasarela."""
    with TestSession() as db:
        pedido = db.get(Pedido, pedido_id)
        assert pedido.estado == 'confirmado'
        [pago] = db.query(Pago).filter_by(pedido_id=pedido_id).all()
        assert pago.estado == 'aprobado'
        clave = pago.clave_idempotencia
    cargo = httpx.get(f'{URL_PASARELA}/cobros/{clave}', timeout=5).json()
    assert cargo['estado'] == 'aprobado'


def _items_del_carrito(c: TestClient) -> dict[int, int]:
    return {i['oferta_id']: i['cantidad'] for i in c.get('/api/v1/cart/').json()['items']}


def _esperar_cola(solicitud_id: str, reset_stock) -> dict:
    """MySQL «volvió»: la cola procesa la solicitud (o el backend de desarrollo, si está corriendo)."""
    salud.reiniciar()
    r = get_redis()
    limite = time.time() + 20
    while time.time() < limite:
        cola.procesar_pendientes(r)
        solicitud = cola.obtener(r, solicitud_id)
        if solicitud['estado'] != 'en_cola':
            if solicitud.get('pedido_id'):
                reset_stock.append(solicitud['pedido_id'])
            return solicitud
        time.sleep(0.3)
    pytest.fail('La cola no procesó la solicitud a tiempo')


def _eventos(pedido_id: int, tipo: str) -> list[OutboxEvento]:
    with TestSession() as db:
        eventos = db.query(OutboxEvento).filter_by(
            agregado_tipo='pedido', agregado_id=str(pedido_id), tipo_evento=tipo).all()
        db.expunge_all()
        return eventos


# ── Al presionar «Comprar» ────────────────────────────────────────────────────

def test_c01_redis_cae_al_leer_el_carrito(cliente, reset_stock):
    _agregar(cliente)
    _preparar('C01')

    compra = _comprar(cliente)

    assert compra.status_code == 201, compra.text
    reset_stock.append(compra.json()['pedido_id'])
    assert _disparos('C01') == 1
    _verificar_un_cobro(compra.json()['pedido_id'])
    assert _items_del_carrito(cliente) == {}           # aún sobre la copia en MySQL
    salud.reiniciar()                                   # Redis volvió
    assert _items_del_carrito(cliente) == {}
    assert not get_redis().exists(rcs._key(USUARIO))    # lo comprado no reapareció en Redis


def test_c02_mysql_no_responde_al_recibir_la_compra(cliente, reset_stock):
    _agregar(cliente)
    antes = (_pedidos_del_usuario(), _inventario())
    _preparar('C02')

    compra = _comprar(cliente)

    assert compra.status_code == 202, compra.text
    assert compra.json()['codigo'] == 'ORDER_QUEUED'
    assert (_pedidos_del_usuario(), _inventario()) == antes   # nada reservado ni cobrado
    solicitud = _esperar_cola(compra.json()['solicitud_id'], reset_stock)
    assert solicitud['estado'] == 'procesado', solicitud
    _verificar_un_cobro(solicitud['pedido_id'])


def test_c03_mysql_cae_a_mitad_de_la_reserva(cliente, reset_stock):
    _agregar(cliente)
    antes = (_pedidos_del_usuario(), _inventario())
    _preparar('C03')

    compra = _comprar(cliente)

    # Ni error para el cliente ni nada a medias en MySQL: la compra pasa a la cola.
    assert compra.status_code == 202, compra.text
    assert compra.json()['codigo'] == 'ORDER_QUEUED'
    assert (_pedidos_del_usuario(), _inventario()) == antes
    assert not salud.disponible('mysql')                # la tienda pasa a solo lectura un momento
    solicitud = _esperar_cola(compra.json()['solicitud_id'], reset_stock)
    assert solicitud['estado'] == 'procesado', solicitud
    _verificar_un_cobro(solicitud['pedido_id'])
    assert _inventario() == (antes[1][0] - 1, antes[1][1])


def test_c04_deadlock_al_reservar_se_reintenta(cliente, reset_stock):
    _agregar(cliente)
    _preparar('C04')
    clave = str(uuid4())

    compra = _comprar(cliente, clave)

    assert compra.status_code == 201, compra.text
    reset_stock.append(compra.json()['pedido_id'])
    assert _disparos('C04') == 1
    with TestSession() as db:
        assert db.query(Pedido).filter_by(clave_idempotencia=clave).count() == 1
    _verificar_un_cobro(compra.json()['pedido_id'])


def test_c04_deadlock_persistente_responde_409_sin_dejar_nada(cliente, reset_stock):
    _agregar(cliente)
    antes = (_pedidos_del_usuario(), _inventario())
    fault_injection.activar('checkout.mysql_deadlock', 'siempre')

    compra = _comprar(cliente)

    assert compra.status_code == 409, compra.text
    assert compra.json()['code'] == 'CONCURRENT_UPDATE'
    assert fault_injection.disparos('checkout.mysql_deadlock') >= 3
    assert (_pedidos_del_usuario(), _inventario()) == antes
    assert _items_del_carrito(cliente) == {OFERTA_TEST_ID: 1}   # el carrito se conserva


# ── Después de cobrar o de confirmar ──────────────────────────────────────────

def test_c05_respuesta_perdida_y_reintento(cliente, reset_stock):
    _agregar(cliente)
    _preparar('C05')
    clave = str(uuid4())

    perdida = _comprar(cliente, clave)

    assert perdida.status_code == 500
    with TestSession() as db:
        pedido = db.query(Pedido).filter_by(clave_idempotencia=clave).one()
    reset_stock.append(pedido.id)
    _verificar_un_cobro(pedido.id)                      # ya estaba cobrado y confirmado

    reintento = _comprar(cliente, clave)                # el navegador conserva la clave

    assert reintento.status_code == 200, reintento.text
    assert reintento.json()['codigo'] == 'IDEMPOTENT_REPLAY'
    assert reintento.json()['pedido_id'] == pedido.id
    with TestSession() as db:
        assert db.query(Pedido).filter_by(usuario_id=USUARIO, clave_idempotencia=clave).count() == 1
    _verificar_un_cobro(pedido.id)                      # sigue siendo un solo cargo


def test_c06_redis_cae_al_vaciar_el_carrito(cliente, reset_stock):
    _agregar(cliente)
    _preparar('C06')

    compra = _comprar(cliente)

    assert compra.status_code == 201, compra.text
    pedido_id = compra.json()['pedido_id']
    reset_stock.append(pedido_id)
    assert _disparos('C06') == 1
    _verificar_un_cobro(pedido_id)
    assert _eventos(pedido_id, 'carrito.limpiar')       # respaldo de la limpieza por el outbox
    assert _items_del_carrito(cliente) == {}
    salud.reiniciar()
    assert _items_del_carrito(cliente) == {}            # lo comprado no reaparece al volver Redis


# ── Ventas flash ──────────────────────────────────────────────────────────────

@pytest.fixture
def promocion(reset_stock):
    """Promoción activa de 2 unidades sobre la oferta de prueba, con su cupo reservado como en la API."""
    with TestSession() as db:
        vendedor = db.execute(text("""
            SELECT v.usuario_id FROM ofertas o JOIN vendedores v ON v.id = o.vendedor_id WHERE o.id = :o
        """), {'o': OFERTA_TEST_ID}).scalar_one()
        ahora = utc_now()
        promo = PromocionFlash(
            oferta_id=OFERTA_TEST_ID, creado_por=vendedor, precio_promocional=Decimal('1.00'),
            unidades_totales=2, unidades_vendidas=0, max_por_usuario=1, segundos_reserva=300,
            inicia_en=ahora - timedelta(seconds=5), finaliza_en=ahora + timedelta(minutes=10), estado='activa',
        )
        db.add(promo)
        db.flush()
        db.execute(text("""
            UPDATE inventario SET cantidad_reservada = cantidad_reservada + 2
            WHERE oferta_id = :o AND bodega = 'principal'
        """), {'o': OFERTA_TEST_ID})
        db.execute(text("""
            INSERT INTO movimientos_inventario (inventario_id, tipo, cantidad, motivo, usuario_id, fecha)
            SELECT id, 'reserva', 2, :motivo, :usuario, :fecha FROM inventario
            WHERE oferta_id = :o AND bodega = 'principal'
        """), {'o': OFERTA_TEST_ID, 'motivo': f'Promoción flash #{promo.id}', 'usuario': vendedor, 'fecha': ahora})
        db.commit()
        promo_id = promo.id
    yield promo_id
    get_redis().delete(*flash._keys(promo_id))
    with TestSession() as db:
        db.execute(text('DELETE FROM flash_resincronizar WHERE promocion_id = :p'), {'p': promo_id})
        db.execute(text('DELETE FROM reservas_flash WHERE promocion_id = :p'), {'p': promo_id})
        db.execute(text('DELETE FROM movimientos_inventario WHERE pedido_id IS NULL AND motivo = :m'),
                   {'m': f'Promoción flash #{promo_id}'})
        db.execute(text('DELETE FROM promociones_flash WHERE id = :p'), {'p': promo_id})
        db.commit()


def _reservar_flash(c: TestClient, promo_id: int) -> dict:
    respuesta = c.post(f'/api/v1/flash-sales/{promo_id}/reserve', json={'cantidad': 1})
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()


def _reservas(promo_id: int) -> list[ReservaFlash]:
    with TestSession() as db:
        filas = db.query(ReservaFlash).filter_by(promocion_id=promo_id).all()
        db.expunge_all()
        return filas


def test_c07_redis_cae_al_cerrar_la_reserva_flash(cliente, promocion, reset_stock):
    reserva = _reservar_flash(cliente, promocion)
    _preparar('C07')

    compra = _comprar(cliente)

    assert compra.status_code == 201, compra.text
    pedido_id = compra.json()['pedido_id']
    reset_stock.append(pedido_id)
    assert _disparos('C07') == 1
    [fila] = _reservas(promocion)
    assert (fila.estado, fila.pedido_id) == ('convertida', pedido_id)   # la venta durable está en MySQL
    r = get_redis()
    assert flash.obtener_reserva(r, promocion, USUARIO)['token'] == reserva['token']  # Redis aún no lo sabe

    [evento] = _eventos(pedido_id, 'flash.consumir')
    with TestSession() as db:
        project_event(db.get(OutboxEvento, evento.id), db)               # lo que hace el worker del outbox

    assert flash.obtener_reserva(r, promocion, USUARIO) is None
    assert flash.obtener_estado(r, promocion)['disponibles'] == 1       # la unidad vendida no volvió al cupo


def test_c08_redis_cae_al_validar_la_reserva_flash(cliente, promocion, reset_stock):
    _reservar_flash(cliente, promocion)
    _preparar('C08')

    compra = _comprar(cliente)

    assert compra.status_code == 201, compra.text
    reset_stock.append(compra.json()['pedido_id'])
    assert _disparos('C08') == 1
    assert Decimal(str(compra.json()['total'])) == Decimal('1.00')     # precio promocional reservado
    [fila] = _reservas(promocion)
    assert fila.estado == 'convertida'
    with TestSession() as db:
        promo = db.get(PromocionFlash, promocion)
        assert promo.unidades_vendidas == 1
        assert flash.disponibles_mysql(db, promo) == 1


def test_c11_redis_reserva_flash_y_no_responde(cliente, promocion):
    _preparar('C11')

    reserva = _reservar_flash(cliente, promocion)

    assert _disparos('C11') == 1
    [fila] = _reservas(promocion)
    assert (fila.token, fila.estado) == (reserva['token'], 'reservada')   # una sola reserva, en MySQL
    r = get_redis()
    with TestSession() as db:
        assert flash.pendiente_resincronizar(db, promocion)
        assert resincronizar_pendientes(db, r) == 1                     # el worker reconstruye la promoción
        promo = db.get(PromocionFlash, promocion)
        flash.rehidratar_si_falta(r, promo, db.query(ReservaFlash).filter_by(
            promocion_id=promocion, estado='reservada').all())
        assert flash.disponibles_mysql(db, promo) == 1
    assert flash.obtener_estado(r, promocion)['disponibles'] == 1       # la unidad no cuenta dos veces
    assert flash.obtener_reserva(r, promocion, USUARIO)['token'] == reserva['token']
    assert OFERTA_TEST_ID in _items_del_carrito(cliente)


# ── Otros momentos ────────────────────────────────────────────────────────────

def test_c09_mongo_cae_al_armar_las_lineas(cliente, reset_stock):
    _agregar(cliente)
    with TestSession() as db:
        producto_ref = db.execute(text('SELECT producto_ref FROM ofertas WHERE id = :o'),
                                  {'o': OFERTA_TEST_ID}).scalar_one()
    from bson import ObjectId
    nombre = get_mongo_db().productos.find_one({'_id': ObjectId(producto_ref)})['nombre']
    _preparar('C09')

    compra = _comprar(cliente)

    assert compra.status_code == 201, compra.text
    pedido_id = compra.json()['pedido_id']
    reset_stock.append(pedido_id)
    assert _disparos('C09') == 1
    with TestSession() as db:
        [linea] = db.query(PedidoLinea).filter_by(pedido_id=pedido_id).all()
        assert linea.producto_nombre == nombre != linea.sku_snapshot
    _verificar_un_cobro(pedido_id)


def test_c10_redis_cae_al_agregar_al_carrito(cliente):
    _preparar('C10')

    _agregar(cliente, cantidad=2)

    assert _disparos('C10') == 1
    assert _items_del_carrito(cliente) == {OFERTA_TEST_ID: 2}
    salud.reiniciar()                                   # Redis volvió
    assert _items_del_carrito(cliente) == {OFERTA_TEST_ID: 2}
    assert set(get_redis().hgetall(rcs._key(USUARIO))) == {str(OFERTA_TEST_ID)}


def test_c12_embeddings_caen_al_buscar(cliente):
    # Frases nuevas: una consulta ya vista usaría su vector guardado en Redis.
    sufijo = uuid4().hex[:6]
    _preparar('C12')

    sin_vector = cliente.get('/api/v1/search', params={'q': f'audífonos para correr {sufijo}'})

    assert sin_vector.status_code == 200, sin_vector.text
    assert _disparos('C12') == 1
    assert sin_vector.json()['semantica'] is False and sin_vector.json()['degradado'] is False
    # Con el circuito abierto, las siguientes ni siquiera intentan el servicio (sin timeout)...
    assert not salud.disponible('embeddings')
    assert cliente.get('/api/v1/search', params={'q': f'teclado mecánico {sufijo}'}).json()['semantica'] is False
    salud.reiniciar()                                   # ...y al volver el servicio son híbridas otra vez
    con_vector = cliente.get('/api/v1/search', params={'q': f'mouse inalámbrico ergonómico {sufijo}'})
    assert con_vector.json()['semantica'] is True


# ── El laboratorio ────────────────────────────────────────────────────────────

def test_cada_caso_tiene_puntos_existentes_y_su_prueba(cliente):
    nombres = set(globals())
    for caso in casos.listar():
        assert caso['puntos'] and all(p in fault_injection.PUNTOS for p in caso['puntos'])
        assert caso['prueba'].split('::')[1] in nombres, caso['id']


def test_preparar_un_caso_deja_solo_sus_puntos_y_la_pasarela_aprobando(cliente, pasarela_en_modo):
    pasarela_en_modo('rechazar')
    fault_injection.activar('outbox.mongo', 'siempre')
    admin = TestClient(app)
    token = admin.post('/api/v1/auth/login', json={
        'email': 'admin@tiendaya.gt', 'password': 'password123'}).json()['access_token']
    admin.headers['Authorization'] = f'Bearer {token}'

    caso = admin.post('/api/v1/admin/fallas/casos/C06/preparar')

    assert caso.status_code == 200, caso.text
    assert caso.json()['armado'] is True
    activos = {p['punto']: p['modo'] for p in fault_injection.estado()['puntos'] if p['modo']}
    assert activos == {'checkout.redis_vaciar_carrito': 'una_vez'}
    assert httpx.get(f'{URL_PASARELA}/control', timeout=5).json()['modo'] == 'aprobar'
    assert admin.post('/api/v1/admin/fallas/casos/C99/preparar').status_code == 404
    assert cliente.get('/api/v1/admin/fallas/casos').status_code == 403   # el comprador no puede
