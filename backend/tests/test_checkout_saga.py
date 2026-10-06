"""Checkout como saga: reserva → cobro externo → confirmación o compensación.

Usa la pasarela simulada de ``conftest.py`` (proceso aparte) y los mismos
datos de prueba que ``test_checkout.py``, cuyo fixture ``reset_stock``
restaura inventario y elimina solo los pedidos creados aquí.
"""

from decimal import Decimal
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.db_redis import get_redis
from app.main import app
from app.models.checkout_saga import CheckoutSagaPaso
from app.models.pago import Pago
from app.models.pedido import Pedido
from app.schemas.checkout import CheckoutItem
from app.services import checkout_service as saga
from app.services import payment_gateway_client as pg
from app.services import redis_cart_service as rcs
from tests.conftest import URL_PASARELA
from tests.test_checkout import (  # noqa: F401  (reset_stock es autouse)
    DIRECCION_ID, METODO_PAGO_ID, OFERTA_TEST_ID, TestSession, USUARIO_COMPRADOR_ID, reset_stock,
)

CONTRA_ENTREGA_ID = 4
ITEMS = [CheckoutItem(oferta_id=OFERTA_TEST_ID, cantidad=2)]


def _inventario(db):
    return db.execute(text("""
        SELECT cantidad_disponible, cantidad_reservada FROM inventario
        WHERE oferta_id = :oid AND bodega = 'principal'
    """), {'oid': OFERTA_TEST_ID}).one()


def _pasos(db, pedido_id):
    return [
        (p.paso, p.resultado)
        for p in db.query(CheckoutSagaPaso).filter_by(pedido_id=pedido_id).order_by(CheckoutSagaPaso.id)
    ]


def _cobro(clave):
    respuesta = httpx.get(f'{URL_PASARELA}/cobros/{clave}', timeout=5)
    return None if respuesta.status_code == 404 else respuesta.json()


def _checkout(db, reset_stock, **kwargs):
    try:
        pedido = saga.procesar_checkout(
            db, usuario_id=USUARIO_COMPRADOR_ID, direccion_id=DIRECCION_ID,
            metodo_pago_id=kwargs.pop('metodo_pago_id', METODO_PAGO_ID), items=ITEMS, **kwargs,
        )
        reset_stock.append(pedido.id)
        return pedido, None
    except saga.CheckoutError as error:
        if error.pedido_id:
            reset_stock.append(error.pedido_id)
        return None, error


# ── Desenlaces del cobro ──────────────────────────────────────────────────────

def test_pago_aprobado_confirma_y_deja_bitacora(reset_stock):
    db = TestSession()
    try:
        antes = _inventario(db)
        pedido, error = _checkout(db, reset_stock)
        assert error is None and pedido.estado == 'confirmado'
        pago = db.query(Pago).filter_by(pedido_id=pedido.id).one()
        assert pago.estado == 'aprobado'
        assert pago.referencia_pasarela.startswith('ch_')
        assert _pasos(db, pedido.id) == [('reserva', 'ok'), ('cobro', 'aprobado'), ('confirmacion', 'ok')]
        despues = _inventario(db)
        assert despues.cantidad_disponible == antes.cantidad_disponible - 2
        assert despues.cantidad_reservada == antes.cantidad_reservada
        assert _cobro(pago.clave_idempotencia)['estado'] == 'aprobado'
    finally:
        db.close()


def test_pago_rechazado_compensa_y_libera_la_reserva(reset_stock, pasarela_en_modo):
    pasarela_en_modo('rechazar')
    db = TestSession()
    try:
        antes = _inventario(db)
        pedido, error = _checkout(db, reset_stock)
        assert pedido is None and error.code == 'PAYMENT_DECLINED'
        cancelado = db.get(Pedido, error.pedido_id)
        assert (cancelado.estado, cancelado.motivo_cancelacion) == ('cancelado', 'pago_rechazado')
        assert db.query(Pago).filter_by(pedido_id=cancelado.id).one().estado == 'rechazado'
        assert _inventario(db) == antes  # nada vendido, nada retenido
        assert _pasos(db, cancelado.id) == [('reserva', 'ok'), ('cobro', 'rechazado'), ('compensacion', 'ok')]
        tipos = {t for (t,) in db.execute(text(
            "SELECT tipo FROM movimientos_inventario WHERE pedido_id = :p"), {'p': cancelado.id})}
        assert tipos == {'reserva', 'liberacion'}
        # La venta nunca existió para el resto de componentes.
        eventos = {t for (t,) in db.execute(text(
            "SELECT tipo_evento FROM outbox_eventos WHERE agregado_tipo='pedido' AND agregado_id=:p"),
            {'p': str(cancelado.id)})}
        assert eventos <= {'inventario.actualizado'}
        assert db.execute(text(
            "SELECT COUNT(*) FROM notificaciones WHERE pedido_id = :p AND usuario_id = :u"),
            {'p': cancelado.id, 'u': USUARIO_COMPRADOR_ID}).scalar_one() == 1
    finally:
        db.close()


def test_falla_despues_de_cobrar_se_resuelve_con_reintento_idempotente(reset_stock, pasarela_en_modo):
    """La pasarela cobra y responde 500; el reintento con la misma clave confirma sin cobrar dos veces."""
    pasarela_en_modo('cobrar_y_fallar')
    db = TestSession()
    try:
        pedido, error = _checkout(db, reset_stock)
        assert error is None and pedido.estado == 'confirmado'
        pago = db.query(Pago).filter_by(pedido_id=pedido.id).one()
        assert pago.intentos == 2
        assert 'HTTP 500' in pago.ultimo_error
        cobros = [c for c in httpx.get(f'{URL_PASARELA}/cobros', timeout=5).json()
                  if c['clave'] == pago.clave_idempotencia]
        assert len(cobros) == 1
    finally:
        db.close()


def test_timeout_deja_el_pago_en_verificacion_y_se_resuelve_consultando(reset_stock, pasarela_en_modo):
    pasarela_en_modo('timeout', demora_timeout_s=1.5)
    pasarela = pg.PasarelaPagos(base_url=URL_PASARELA, timeout=0.5, reintentos=1)
    db = TestSession()
    try:
        antes = _inventario(db)
        pedido, error = _checkout(db, reset_stock, pasarela=pasarela)
        assert error.code == 'PAYMENT_PENDING'
        pendiente = db.get(Pedido, error.pedido_id)
        pago = db.query(Pago).filter_by(pedido_id=pendiente.id).one()
        assert (pendiente.estado, pago.estado) == ('pendiente', 'en_verificacion')
        # El stock sigue retenido mientras no se sabe si se cobró.
        assert _inventario(db).cantidad_reservada == antes.cantidad_reservada + 2

        # Lo que hará el reconciliador: consultar la pasarela con la misma clave.
        consulta = pasarela.consultar(pago.clave_idempotencia)
        assert consulta.estado == pg.APROBADO
        assert saga.aplicar_resultado_cobro(db, pendiente.id, consulta, pasarela, 'reconciliador') == saga.CONFIRMADO
        db.expire_all()
        assert db.get(Pedido, pendiente.id).estado == 'confirmado'
        assert _inventario(db).cantidad_disponible == antes.cantidad_disponible - 2
        assert _inventario(db).cantidad_reservada == antes.cantidad_reservada
    finally:
        db.close()


def test_sin_respuesta_y_sin_cargo_se_compensa_al_consultar(reset_stock, pasarela_en_modo):
    """503 en todos los intentos: resultado desconocido; la consulta confirma que nunca se cobró."""
    pasarela_en_modo('error_antes')
    db = TestSession()
    try:
        antes = _inventario(db)
        pedido, error = _checkout(db, reset_stock)
        assert error.code == 'PAYMENT_PENDING'
        pago = db.query(Pago).filter_by(pedido_id=error.pedido_id).one()
        pasarela = pg.get_pasarela()
        consulta = pasarela.consultar(pago.clave_idempotencia)
        assert consulta.estado == pg.NO_ENCONTRADO
        assert saga.aplicar_resultado_cobro(db, error.pedido_id, consulta, pasarela) == saga.NO_ENVIADO
        db.expire_all()
        assert db.get(Pedido, error.pedido_id).estado == 'cancelado'
        assert _inventario(db) == antes
    finally:
        db.close()


def test_pasarela_inalcanzable_compensa_de_inmediato(reset_stock):
    """Sin conexión la solicitud nunca salió: no hay ambigüedad, se cancela y libera."""
    caida = pg.PasarelaPagos(base_url='http://127.0.0.1:1', timeout=0.5, reintentos=1)
    db = TestSession()
    try:
        antes = _inventario(db)
        pedido, error = _checkout(db, reset_stock, pasarela=caida)
        assert error.code == 'PAYMENT_UNAVAILABLE'
        cancelado = db.get(Pedido, error.pedido_id)
        assert cancelado.motivo_cancelacion == 'pasarela_no_disponible'
        assert _inventario(db) == antes
    finally:
        db.close()


def test_cobro_aprobado_de_pedido_no_cumplible_se_reembolsa(reset_stock):
    db = TestSession()
    try:
        antes = _inventario(db)
        pedido = saga.reservar_pedido(
            db, usuario_id=USUARIO_COMPRADOR_ID, direccion_id=DIRECCION_ID,
            metodo_pago_id=METODO_PAGO_ID, items=ITEMS,
        )
        reset_stock.append(pedido.id)
        pasarela = pg.get_pasarela()
        resultado = saga.cobrar_pedido(db, pedido.id, pasarela)
        assert resultado.estado == pg.APROBADO
        # Simula que la reserva se perdió entre el cobro y la confirmación.
        db.execute(text("""
            UPDATE inventario SET cantidad_reservada = :r
            WHERE oferta_id = :oid AND bodega = 'principal'
        """), {'r': antes.cantidad_reservada, 'oid': OFERTA_TEST_ID})
        db.commit()
        assert saga.aplicar_resultado_cobro(db, pedido.id, resultado, pasarela) == saga.REEMBOLSADO
        db.expire_all()
        cancelado = db.get(Pedido, pedido.id)
        pago = db.query(Pago).filter_by(pedido_id=pedido.id).one()
        assert (cancelado.estado, pago.estado) == ('cancelado', 'reembolsado')
        assert _cobro(pago.clave_idempotencia)['estado'] == 'reembolsado'
        assert _inventario(db) == antes
    finally:
        db.close()


def test_contra_entrega_confirma_sin_pasar_por_la_pasarela(reset_stock):
    db = TestSession()
    try:
        pedido, error = _checkout(db, reset_stock, metodo_pago_id=CONTRA_ENTREGA_ID)
        assert error is None and pedido.estado == 'confirmado'
        pago = db.query(Pago).filter_by(pedido_id=pedido.id).one()
        assert pago.estado == 'pendiente'  # se cobra al entregar
        assert _cobro(pago.clave_idempotencia) is None
        assert ('cobro', 'aprobado') not in _pasos(db, pedido.id)
    finally:
        db.close()


# ── Transiciones protegidas e idempotencia ────────────────────────────────────

def test_confirmar_y_compensar_son_idempotentes(reset_stock):
    db = TestSession()
    try:
        pedido, _ = _checkout(db, reset_stock)
        despues = _inventario(db)
        saga.confirmar_pedido(db, pedido.id)  # segunda confirmación: sin efecto
        saga.compensar_pedido(db, pedido.id, 'pago_rechazado')  # no deshace una venta confirmada
        db.expire_all()
        assert db.get(Pedido, pedido.id).estado == 'confirmado'
        assert _inventario(db) == despues
        assert [p for p, _ in _pasos(db, pedido.id)].count('confirmacion') == 1
    finally:
        db.close()


def test_misma_clave_no_crea_un_segundo_pedido(reset_stock):
    from sqlalchemy.exc import IntegrityError

    clave = str(uuid4())
    db = TestSession()
    try:
        pedido, _ = _checkout(db, reset_stock, clave_idempotencia=clave)
        with pytest.raises(IntegrityError):
            saga.procesar_checkout(
                db, usuario_id=USUARIO_COMPRADOR_ID, direccion_id=DIRECCION_ID,
                metodo_pago_id=METODO_PAGO_ID, items=ITEMS, clave_idempotencia=clave,
            )
        db.rollback()
        assert db.query(Pedido).filter_by(clave_idempotencia=clave).count() == 1
    finally:
        db.close()


# ── Endpoint HTTP ─────────────────────────────────────────────────────────────

@pytest.fixture
def cliente_comprador():
    """Cliente autenticado; respalda y restaura el carrito Redis real del comprador."""
    r = get_redis()
    clave_carrito = f'carrito:{USUARIO_COMPRADOR_ID}'
    respaldo, ttl = r.hgetall(clave_carrito), r.ttl(clave_carrito)
    cliente = TestClient(app)
    token = cliente.post('/api/v1/auth/login', json={
        'email': 'comprador1@gmail.com', 'password': 'password123',
    }).json()['access_token']
    cliente.headers['Authorization'] = f'Bearer {token}'

    def llenar_carrito():
        r.delete(clave_carrito)
        with TestSession() as db:
            precio = db.execute(text('SELECT precio_actual FROM ofertas WHERE id = :o'),
                                {'o': OFERTA_TEST_ID}).scalar_one()
        rcs.agregar_item(r, USUARIO_COMPRADOR_ID, OFERTA_TEST_ID, 1, Decimal(precio), None)

    yield cliente, llenar_carrito
    r.delete(clave_carrito)
    if respaldo:
        r.hset(clave_carrito, mapping=respaldo)
        if ttl and ttl > 0:
            r.expire(clave_carrito, ttl)


def _post_checkout(cliente, clave):
    return cliente.post(
        '/api/v1/orders/checkout',
        json={'direccion_id': DIRECCION_ID, 'metodo_pago_id': METODO_PAGO_ID},
        headers={'Idempotency-Key': clave} if clave else {},
    )


def test_api_reintento_con_la_misma_clave_devuelve_el_mismo_pedido(reset_stock, cliente_comprador):
    cliente, llenar_carrito = cliente_comprador
    llenar_carrito()
    clave = str(uuid4())
    primero = _post_checkout(cliente, clave)
    assert primero.status_code == 201, primero.text
    reset_stock.append(primero.json()['pedido_id'])
    assert primero.json()['codigo'] == 'CONFIRMED'

    repetido = _post_checkout(cliente, clave)  # p. ej. el navegador reintenta tras un timeout
    assert repetido.status_code == 200
    assert repetido.headers['Idempotent-Replayed'] == 'true'
    assert repetido.json()['pedido_id'] == primero.json()['pedido_id']
    assert repetido.json()['codigo'] == 'IDEMPOTENT_REPLAY'

    llenar_carrito()  # misma clave, pero otra compra
    with TestSession() as db:
        db.execute(text("UPDATE pedidos SET huella_solicitud = 'otra' WHERE id = :p"),
                   {'p': primero.json()['pedido_id']})
        db.commit()
    distinto = _post_checkout(cliente, clave)
    assert distinto.status_code == 422
    assert distinto.json()['detail']['code'] == 'IDEMPOTENCY_KEY_MISMATCH'


def test_api_pago_rechazado_responde_402_y_conserva_el_carrito(reset_stock, cliente_comprador, pasarela_en_modo):
    cliente, llenar_carrito = cliente_comprador
    llenar_carrito()
    pasarela_en_modo('rechazar')
    respuesta = _post_checkout(cliente, str(uuid4()))
    assert respuesta.status_code == 402
    detalle = respuesta.json()['detail']
    reset_stock.append(detalle['pedido_id'])
    assert detalle['code'] == 'PAYMENT_DECLINED'
    assert detalle['carrito_conservado'] is True
    assert [i['oferta_id'] for i in rcs.obtener_carrito(get_redis(), USUARIO_COMPRADOR_ID)] == [OFERTA_TEST_ID]


def test_api_pago_en_verificacion_responde_202_y_bloquea_otra_compra(reset_stock, cliente_comprador, pasarela_en_modo):
    cliente, llenar_carrito = cliente_comprador
    llenar_carrito()
    pasarela_en_modo('error_antes')
    pendiente = _post_checkout(cliente, str(uuid4()))
    assert pendiente.status_code == 202
    cuerpo = pendiente.json()
    reset_stock.append(cuerpo['pedido_id'])
    assert (cuerpo['codigo'], cuerpo['estado'], cuerpo['requiere_seguimiento']) == ('PAYMENT_PENDING', 'pendiente', True)

    pasarela_en_modo('aprobar')
    otra = _post_checkout(cliente, str(uuid4()))
    assert otra.status_code == 409
    assert otra.json()['detail']['code'] == 'PAYMENT_PENDING_EXISTS'
    with TestSession() as db:  # la deja resuelta para no afectar otras pruebas
        saga.compensar_pedido(db, cuerpo['pedido_id'], 'pago_no_recibido')
