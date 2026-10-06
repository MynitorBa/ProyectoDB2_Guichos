"""Recuperación del checkout tras fallas: reconciliador, recolector e invariantes.

Cada prueba provoca una falla concreta (con la pasarela simulada o con un
punto de falla), deja al sistema "a medias" y comprueba que la recuperación lo
lleva a un estado correcto sin cobrar dos veces ni retener inventario.
"""

from datetime import timedelta
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core import fault_injection
from app.core.config import settings
from app.core.db_elastic import get_es
from app.core.db_mongo import get_mongo_db
from app.core.time import utc_now
from app.main import app
from app.models.outbox import OutboxEvento
from app.models.pago import Pago
from app.models.pedido import Pedido
from app.services import checkout_service as saga
from app.services import consistency_service
from app.services import outbox_service as outbox
from app.services import payment_gateway_client as pg
from app.services.checkout_recovery_worker import reconciliar_pagos, recolectar_vencidos
from tests.conftest import URL_PASARELA
from tests.test_checkout import (  # noqa: F401  (reset_stock es autouse)
    DIRECCION_ID, METODO_PAGO_ID, OFERTA_TEST_ID, TestSession, USUARIO_COMPRADOR_ID, reset_stock,
)
from tests.test_checkout_saga import ITEMS, _inventario, _pasos


@pytest.fixture
def fallas():
    anterior = settings.FAULT_INJECTION_ENABLED
    settings.FAULT_INJECTION_ENABLED = True
    yield fault_injection
    fault_injection.desactivar()
    settings.FAULT_INJECTION_ENABLED = anterior


def _checkout_con_clave(db, reset_stock, **kwargs):
    """Ejecuta el checkout; si se interrumpe, devuelve el pedido que dejó creado."""
    clave = str(uuid4())
    error = None
    try:
        saga.procesar_checkout(
            db, usuario_id=USUARIO_COMPRADOR_ID, direccion_id=DIRECCION_ID,
            metodo_pago_id=METODO_PAGO_ID, items=ITEMS, clave_idempotencia=clave, **kwargs,
        )
    except (saga.CheckoutError, fault_injection.FallaSimulada) as exc:
        error = exc
        db.rollback()
    pedido = db.query(Pedido).filter_by(clave_idempotencia=clave).one()
    reset_stock.append(pedido.id)
    return pedido, error


def _vencer_reserva(db, pedido_id):
    db.execute(text('UPDATE pedidos SET reserva_expira_en = :t WHERE id = :p'),
               {'t': utc_now() - timedelta(minutes=1), 'p': pedido_id})
    db.commit()


def _cobros(clave):
    return [c for c in httpx.get(f'{URL_PASARELA}/cobros', timeout=5).json() if c['clave'] == clave]


def _invariantes_de_reserva_ok(db):
    return (consistency_service.reservas_explicadas(db)['ok']
            and consistency_service.cancelados_liberan_reserva(db)['ok']
            and consistency_service.inventario_coherente(db)['ok'])


# ── Reconciliador: pagos en verificación ──────────────────────────────────────

def test_reconciliador_confirma_un_pago_que_si_se_cobro(reset_stock, pasarela_en_modo):
    pasarela_en_modo('timeout', demora_timeout_s=1.5)
    lenta = pg.PasarelaPagos(base_url=URL_PASARELA, timeout=0.5, reintentos=1)
    db = TestSession()
    try:
        antes = _inventario(db)
        pedido, error = _checkout_con_clave(db, reset_stock, pasarela=lenta)
        assert error.code == 'PAYMENT_PENDING'
        pasarela_en_modo('aprobar')
        resumen = reconciliar_pagos(db, pg.get_pasarela())
        assert resumen.get(saga.CONFIRMADO) == 1
        db.expire_all()
        assert db.get(Pedido, pedido.id).estado == 'confirmado'
        assert _inventario(db).cantidad_disponible == antes.cantidad_disponible - 2
        assert ('reconciliador', 'aprobado') in _pasos(db, pedido.id)
        assert len(_cobros(pedido.clave_idempotencia)) == 1
        assert _invariantes_de_reserva_ok(db)
    finally:
        db.close()


def test_reconciliador_espera_y_luego_compensa_un_cobro_inexistente(reset_stock, pasarela_en_modo):
    pasarela_en_modo('error_antes')
    db = TestSession()
    try:
        antes = _inventario(db)
        pedido, error = _checkout_con_clave(db, reset_stock)
        assert error.code == 'PAYMENT_PENDING'
        pasarela_en_modo('aprobar')
        # Dentro del periodo de gracia la solicitud podría seguir en tránsito.
        assert reconciliar_pagos(db, pg.get_pasarela()) == {'sin_cambios': 1}
        db.execute(text('UPDATE pedidos SET fecha_creacion = :t WHERE id = :p'),
                   {'t': utc_now() - timedelta(seconds=settings.RECONCILIADOR_GRACIA_S + 5), 'p': pedido.id})
        db.commit()
        assert reconciliar_pagos(db, pg.get_pasarela()) == {saga.NO_ENVIADO: 1}
        db.expire_all()
        cancelado = db.get(Pedido, pedido.id)
        assert (cancelado.estado, cancelado.motivo_cancelacion) == ('cancelado', 'pago_no_recibido')
        assert _inventario(db) == antes
        assert _invariantes_de_reserva_ok(db)
    finally:
        db.close()


# ── Recolector: el proceso cayó a mitad de la saga ────────────────────────────

def test_caida_antes_de_cobrar_libera_la_reserva_al_vencer(reset_stock, fallas):
    fallas.activar('checkout.despues_reserva')
    db = TestSession()
    try:
        antes = _inventario(db)
        pedido, error = _checkout_con_clave(db, reset_stock)
        assert isinstance(error, fallas.FallaSimulada)
        assert pedido.estado == 'pendiente'
        assert _inventario(db).cantidad_reservada == antes.cantidad_reservada + 2
        assert recolectar_vencidos(db, pg.get_pasarela()) == {}  # aún no vence
        _vencer_reserva(db, pedido.id)
        assert recolectar_vencidos(db, pg.get_pasarela()) == {saga.NO_ENVIADO: 1}
        db.expire_all()
        assert db.get(Pedido, pedido.id).estado == 'cancelado'
        assert _inventario(db) == antes
        assert _cobros(pedido.clave_idempotencia) == []
        assert _invariantes_de_reserva_ok(db)
    finally:
        db.close()


def test_caida_despues_de_cobrar_confirma_sin_volver_a_cobrar(reset_stock, fallas):
    fallas.activar('checkout.despues_cobro')
    db = TestSession()
    try:
        antes = _inventario(db)
        pedido, error = _checkout_con_clave(db, reset_stock)
        assert isinstance(error, fallas.FallaSimulada)
        assert db.query(Pago).filter_by(pedido_id=pedido.id).one().estado == 'pendiente'
        _vencer_reserva(db, pedido.id)
        assert recolectar_vencidos(db, pg.get_pasarela()) == {saga.CONFIRMADO: 1}
        db.expire_all()
        assert db.get(Pedido, pedido.id).estado == 'confirmado'
        assert _inventario(db).cantidad_disponible == antes.cantidad_disponible - 2
        assert len(_cobros(pedido.clave_idempotencia)) == 1
        assert ('recolector', 'aprobado') in _pasos(db, pedido.id)
    finally:
        db.close()


def test_falla_de_la_transaccion_de_confirmacion_no_deja_nada_a_medias(reset_stock, fallas):
    fallas.activar('checkout.confirmacion')
    db = TestSession()
    try:
        antes = _inventario(db)
        pedido, error = _checkout_con_clave(db, reset_stock)
        assert isinstance(error, fallas.FallaSimulada)
        # El rollback deshizo todo lo de la confirmación: sigue la reserva, no la venta.
        db.expire_all()
        assert db.get(Pedido, pedido.id).estado == 'pendiente'
        assert _inventario(db).cantidad_disponible == antes.cantidad_disponible
        assert _inventario(db).cantidad_reservada == antes.cantidad_reservada + 2
        assert ('confirmacion', 'ok') not in _pasos(db, pedido.id)
        _vencer_reserva(db, pedido.id)
        assert recolectar_vencidos(db, pg.get_pasarela()) == {saga.CONFIRMADO: 1}
        db.expire_all()
        assert db.get(Pedido, pedido.id).estado == 'confirmado'
        assert len(_cobros(pedido.clave_idempotencia)) == 1
        assert _invariantes_de_reserva_ok(db)
    finally:
        db.close()


def test_recolector_sin_respuesta_de_la_pasarela_pasa_a_verificacion(reset_stock, fallas):
    fallas.activar('checkout.despues_reserva')
    caida = pg.PasarelaPagos(base_url='http://127.0.0.1:1', timeout=0.3, reintentos=0)
    db = TestSession()
    try:
        pedido, _ = _checkout_con_clave(db, reset_stock)
        _vencer_reserva(db, pedido.id)
        assert recolectar_vencidos(db, caida) == {saga.EN_VERIFICACION: 1}
        db.expire_all()
        assert db.query(Pago).filter_by(pedido_id=pedido.id).one().estado == 'en_verificacion'
        # Cuando la pasarela vuelve, el reconciliador lo cierra.
        db.execute(text('UPDATE pedidos SET fecha_creacion = :t WHERE id = :p'),
                   {'t': utc_now() - timedelta(minutes=10), 'p': pedido.id})
        db.commit()
        assert reconciliar_pagos(db, pg.get_pasarela()) == {saga.NO_ENVIADO: 1}
    finally:
        db.close()


# ── Outbox con un destino fallando ────────────────────────────────────────────

def test_falla_simulada_en_un_destino_del_outbox_se_recupera(fallas):
    ref = str(get_mongo_db().productos.find_one({'sku': 'TECH-LAP-001'}, {'_id': 1})['_id'])
    fallas.activar('outbox.mongo', 'siempre')
    with TestSession() as db:
        evento = outbox.enqueue_outbox(db, tipo_evento='inventario.actualizado', agregado_tipo='prueba',
                                       agregado_id='falla-outbox', producto_ref=ref, payload={},
                                       destinos=('mongo',))
        db.commit()
        evento_id = evento.id
    try:
        for _ in range(50):
            outbox._pausas.clear()
            if not outbox.process_one():
                break
            with TestSession() as db:
                if db.get(OutboxEvento, evento_id).estado == 'error':
                    break
        with TestSession() as db:
            fallido = db.get(OutboxEvento, evento_id)
            assert fallido.estado == 'error' and 'Falla simulada' in fallido.ultimo_error
            fallas.desactivar('outbox.mongo')
            fallido.siguiente_intento_en = utc_now() - timedelta(seconds=1)
            db.commit()
        for _ in range(50):
            outbox._pausas.clear()
            with TestSession() as db:
                if db.get(OutboxEvento, evento_id).estado == 'procesado':
                    break
            if not outbox.process_one():
                break
        with TestSession() as db:
            assert db.get(OutboxEvento, evento_id).estado == 'procesado'
    finally:
        with TestSession() as db:
            db.query(OutboxEvento).filter_by(id=evento_id).delete()
            db.commit()
        outbox._pausas.clear()


# ── Invariantes ───────────────────────────────────────────────────────────────

def test_invariantes_se_cumplen_y_detectan_una_reserva_huerfana(reset_stock):
    db = TestSession()
    try:
        resultado = consistency_service.verificar(db, get_mongo_db(), get_es())
        # I6 se omite aquí: el registro de la pasarela de pruebas conserva cobros
        # de pedidos que otras pruebas ya borraron (en producción nunca se borran).
        violados = {i['id'] for i in resultado['invariantes'] if i['ok'] is False} - {'I6'}
        assert violados == set()
        # Una unidad reservada sin promoción ni pedido que la explique.
        db.execute(text("""
            UPDATE inventario SET cantidad_reservada = cantidad_reservada + 1
            WHERE oferta_id = :oid AND bodega = 'principal'
        """), {'oid': OFERTA_TEST_ID})
        db.commit()
        violado = consistency_service.reservas_explicadas(db)
        assert violado['ok'] is False
        assert violado['ejemplos'][0]['oferta_id'] == OFERTA_TEST_ID
    finally:
        db.close()


def test_invariante_de_pasarela_cuadra_cobros_con_pedidos(reset_stock, pasarela_en_modo):
    db = TestSession()
    try:
        confirmado, _ = _checkout_con_clave(db, reset_stock)
        pasarela_en_modo('rechazar')
        rechazado, _ = _checkout_con_clave(db, reset_stock)
        claves = {confirmado.clave_idempotencia, rechazado.clave_idempotencia}
        resultado = consistency_service.pasarela_coincide(db, claves)
        assert resultado['ok'] is True
        assert '2 cobro(s)' in resultado['detalle']
        # Un cobro aprobado cuyo pedido figura cancelado sí es una violación.
        db.execute(text("UPDATE pedidos SET estado = 'cancelado' WHERE id = :p"), {'p': confirmado.id})
        db.commit()
        violado = consistency_service.pasarela_coincide(db, claves)
        assert violado['ok'] is False
        assert violado['ejemplos'] == [{
            'clave': confirmado.clave_idempotencia, 'cobro': 'aprobado',
            'pedido_id': confirmado.id, 'pedido': 'cancelado', 'pago': 'aprobado',
        }]
    finally:
        db.close()


# ── Endpoints de administración ───────────────────────────────────────────────

@pytest.fixture(scope='module')
def admin():
    cliente = TestClient(app)
    token = cliente.post('/api/v1/auth/login', json={
        'email': 'admin@tiendaya.gt', 'password': 'password123',
    }).json()['access_token']
    cliente.headers['Authorization'] = f'Bearer {token}'
    return cliente


def test_endpoints_de_fallas_respetan_la_bandera(admin):
    anterior = settings.FAULT_INJECTION_ENABLED
    try:
        settings.FAULT_INJECTION_ENABLED = False
        bloqueado = admin.post('/api/v1/admin/fallas', json={'punto': 'checkout.despues_cobro'})
        assert bloqueado.status_code == 403
        settings.FAULT_INJECTION_ENABLED = True
        activado = admin.post('/api/v1/admin/fallas', json={'punto': 'checkout.despues_cobro', 'modo': 'siempre'})
        assert activado.status_code == 200
        puntos = {p['punto']: p['modo'] for p in admin.get('/api/v1/admin/fallas').json()['puntos']}
        assert puntos['checkout.despues_cobro'] == 'siempre'
        assert admin.post('/api/v1/admin/fallas', json={'punto': 'inventado'}).status_code == 422
        assert admin.post('/api/v1/admin/fallas/pasarela', json={'modo': 'rechazar'}).json()['modo'] == 'rechazar'
    finally:
        admin.post('/api/v1/admin/fallas/pasarela', json={'modo': 'aprobar'})
        fault_injection.desactivar()
        settings.FAULT_INJECTION_ENABLED = anterior


def test_endpoints_de_consistencia_y_bitacora(admin, reset_stock):
    db = TestSession()
    try:
        pedido, _ = _checkout_con_clave(db, reset_stock)
    finally:
        db.close()
    bitacora = admin.get('/api/v1/admin/checkout/saga', params={'pedido_id': pedido.id}).json()
    assert [p['paso'] for p in reversed(bitacora)] == ['reserva', 'cobro', 'confirmacion']
    assert bitacora[0]['pedido_estado'] == 'confirmado'
    consistencia = admin.get('/api/v1/admin/consistencia').json()
    assert {i['id'] for i in consistencia['invariantes']} == {f'I{n}' for n in range(1, 8)}
    assert admin.post('/api/v1/admin/checkout/recuperar').status_code == 200
