from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace

from app.core.db_mysql import SessionLocal
from app.core.time import utc_now
from app.models.inventario import Inventario
from app.models.oferta import Oferta
from app.services.offer_history_service import (
    _gt_day_end_utc,
    _vigente_en,
    historial_precios_diario,
    historial_operativo_unificado,
    reconstruir_ofertas_en_fecha,
)
from app.services.offer_service import actualizar_precio_oferta


def test_daily_sample_uses_last_price_at_end_of_gt_day():
    first = SimpleNamespace(
        vigente_desde=datetime(2026, 8, 26, 8, 0),
        vigente_hasta=datetime(2026, 8, 27, 2, 0),
        precio=100,
    )
    last = SimpleNamespace(
        vigente_desde=datetime(2026, 8, 27, 2, 0),
        vigente_hasta=None,
        precio=125,
    )

    sample = _gt_day_end_utc(date(2026, 8, 26))

    assert sample == datetime(2026, 8, 27, 5, 59, 59, 999999)
    assert _vigente_en([first, last], sample).precio == 125


def test_current_reconstruction_matches_all_mysql_offers():
    with SessionLocal() as db:
        product_ref = (
            db.query(Oferta.producto_ref)
            .group_by(Oferta.producto_ref)
            .order_by(Oferta.producto_ref)
            .first()[0]
        )
        expected = db.query(Oferta).filter_by(producto_ref=product_ref).all()
        reconstructed = reconstruir_ofertas_en_fecha(
            db, producto_ref=product_ref, instante_utc=utc_now()
        )

        assert {row['oferta_id'] for row in reconstructed} == {
            offer.id for offer in expected
        }
        for row in reconstructed:
            offer = db.get(Oferta, row['oferta_id'])
            inventory = db.query(Inventario).filter_by(
                oferta_id=offer.id, bodega='principal'
            ).first()
            assert row['precio'] == float(offer.precio_actual)
            assert row['estado'] == offer.estado
            assert row['stock_disponible'] == inventory.cantidad_disponible
            assert row['stock_reservado'] == inventory.cantidad_reservada


def test_daily_history_contains_one_series_per_offer():
    with SessionLocal() as db:
        product_ref = (
            db.query(Oferta.producto_ref)
            .group_by(Oferta.producto_ref)
            .order_by(Oferta.producto_ref)
            .first()[0]
        )
        expected_ids = {
            offer.id for offer in db.query(Oferta).filter_by(
                producto_ref=product_ref
            ).all()
        }
        result = historial_precios_diario(db, producto_ref=product_ref)

        assert {row['oferta_id'] for row in result['ofertas']} == expected_ids
        assert all(row['puntos'] for row in result['ofertas'])


def test_two_same_day_changes_keep_last_price_for_daily_history():
    with SessionLocal() as db:
        offer = db.query(Oferta).order_by(Oferta.id).first()
        original = offer.precio_actual
        actualizar_precio_oferta(
            db, oferta=offer, nuevo_precio=original + Decimal('1.00'),
            usuario_id=1, motivo='Primera modificación diaria de prueba',
        )
        db.flush()
        actualizar_precio_oferta(
            db, oferta=offer, nuevo_precio=original + Decimal('2.00'),
            usuario_id=1, motivo='Última modificación diaria de prueba',
        )
        db.flush()

        # El muestreo al cierre encuentra el segundo intervalo aún vigente.
        result = historial_precios_diario(
            db,
            producto_ref=offer.producto_ref,
            desde=date.today(),
            hasta=date.today(),
        )
        series = next(row for row in result['ofertas'] if row['oferta_id'] == offer.id)
        assert series['puntos'][-1]['precio'] == float(original + Decimal('2.00'))
        db.rollback()


def test_operational_history_exposes_price_state_and_inventory_sources():
    with SessionLocal() as db:
        offer = db.query(Oferta).order_by(Oferta.id).first()
        events = historial_operativo_unificado(
            db, producto_ref=offer.producto_ref
        )
        event_types = {event['tipo_evento'] for event in events}

        assert any(event_type.startswith('OFERTA_PRECIO_') for event_type in event_types)
        assert any(event_type.startswith('OFERTA_ESTADO_') for event_type in event_types)
        assert any(event_type.startswith('INVENTARIO_SALDO_') for event_type in event_types)
        assert all(event['fuente'] == 'mysql' for event in events)
