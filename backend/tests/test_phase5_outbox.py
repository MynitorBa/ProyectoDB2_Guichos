"""Pruebas del productor, consumidor, idempotencia y reintento del outbox."""

import time
from decimal import Decimal

from bson import ObjectId

from app.core.db_mongo import get_mongo_db
from app.core.db_mysql import SessionLocal
from app.models.outbox import OutboxEvento
from app.models.oferta import Oferta, OfertaPrecioHistorial
from app.services.outbox_service import (
    enqueue_outbox,
    process_batch,
    project_event,
)
from app.services.offer_service import actualizar_precio_oferta


def wait_for_state(event_id: str, expected: set[str], timeout=5):
    deadline = time.time() + timeout
    while time.time() < deadline:
        with SessionLocal() as db:
            event = db.get(OutboxEvento, event_id)
            if event and event.estado in expected:
                return event.estado
        process_batch(1)
        time.sleep(0.05)
    return None


def product_context():
    with SessionLocal() as db:
        offer = db.get(Oferta, 65)
        ref = offer.producto_ref
    doc = get_mongo_db().productos.find_one({'_id': ObjectId(ref)})
    return ref, int(doc.get('stock', 0)), bool(doc.get('disponible', False))


def test_outbox_projects_once_and_history_is_idempotent():
    ref, stock, available = product_context()
    with SessionLocal() as db:
        event = enqueue_outbox(
            db,
            tipo_evento='inventario.prueba',
            agregado_tipo='prueba',
            agregado_id='idempotencia',
            producto_ref=ref,
            payload={
                'projection': {'stock': stock, 'disponible': available},
                'history': {
                    'tipo_evento': 'DISPONIBILIDAD_CAMBIADA',
                    'datos_anteriores': {'stock': stock},
                    'datos_nuevos': {'stock': stock, 'disponible': available},
                    'usuario_id': None,
                },
            },
        )
        event_id = event.id
        db.commit()

    try:
        assert wait_for_state(event_id, {'procesado'}) == 'procesado'
        with SessionLocal() as db:
            event = db.get(OutboxEvento, event_id)
            project_event(event)
            project_event(event)
        assert get_mongo_db().producto_eventos.count_documents(
            {'outbox_id': event_id}
        ) == 1
    finally:
        get_mongo_db().producto_eventos.delete_many({'outbox_id': event_id})
        with SessionLocal() as db:
            event = db.get(OutboxEvento, event_id)
            if event:
                db.delete(event)
                db.commit()


def test_outbox_error_can_be_retried_safely():
    ref, stock, available = product_context()
    with SessionLocal() as db:
        event = enqueue_outbox(
            db,
            tipo_evento='inventario.prueba_reintento',
            agregado_tipo='prueba',
            agregado_id='reintento',
            producto_ref='0' * 24,
            payload={'projection': {'stock': stock, 'disponible': available}},
        )
        event_id = event.id
        db.commit()

    try:
        assert wait_for_state(event_id, {'error'}) == 'error'
        with SessionLocal() as db:
            event = db.get(OutboxEvento, event_id)
            first_attempts = event.intentos
            assert event.ultimo_error
            event.producto_ref = ref
            event.estado = 'pendiente'
            event.procesado_en = None
            db.commit()
        assert wait_for_state(event_id, {'procesado'}) == 'procesado'
        with SessionLocal() as db:
            event = db.get(OutboxEvento, event_id)
            assert event.intentos > first_attempts
            assert event.ultimo_error is None
    finally:
        with SessionLocal() as db:
            event = db.get(OutboxEvento, event_id)
            if event:
                db.delete(event)
                db.commit()


def test_price_service_is_atomic_with_history_and_outbox():
    with SessionLocal() as db:
        offer = db.get(Oferta, 65)
        original_price = offer.precio_actual
        original_version = offer.version
        changed = actualizar_precio_oferta(
            db,
            oferta=offer,
            nuevo_precio=original_price + Decimal('1.00'),
            usuario_id=1,
            motivo='Prueba transaccional con rollback',
        )
        db.flush()
        assert changed is True
        assert offer.version == original_version + 1
        current_prices = db.query(OfertaPrecioHistorial).filter_by(
            oferta_id=offer.id, vigente_hasta=None
        ).count()
        pending_events = db.query(OutboxEvento).filter_by(
            agregado_tipo='oferta', agregado_id=str(offer.id), estado='pendiente'
        ).count()
        assert current_prices == 1
        assert pending_events >= 1
        db.rollback()

    with SessionLocal() as db:
        offer = db.get(Oferta, 65)
        assert offer.precio_actual == original_price
        assert offer.version == original_version
