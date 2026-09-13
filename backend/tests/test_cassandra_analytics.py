from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

from app.core.db_cassandra import close_cassandra, get_cassandra_session
from app.core.db_mysql import SessionLocal
from app.services.analytics_service import (
    _paid_lines,
    _week_for_row,
    current_week_start,
    product_trends,
    rebuild_all,
)
from app.services.outbox_service import project_event


def test_week_is_monday_in_guatemala():
    # Lunes 00:30 UTC todavía es domingo en Guatemala.
    assert current_week_start(datetime(2026, 9, 14, 0, 30, tzinfo=timezone.utc)) == date(2026, 9, 7)
    assert current_week_start(datetime(2026, 9, 14, 6, 0, tzinfo=timezone.utc)) == date(2026, 9, 14)


def test_backfill_is_idempotent_and_matches_mysql():
    cassandra = get_cassandra_session()
    with SessionLocal() as db:
        source = _paid_lines(db)
        first = rebuild_all(db, cassandra)
        second = rebuild_all(db, cassandra)
    assert first == second
    assert first['lineas'] == len(source)
    assert cassandra.execute('SELECT COUNT(*) FROM ventas_producto_semana').one()[0] == len(source)

    expected_net = sum(
        (row['subtotal'] for row in source if row['estado_pago'] != 'reembolsado'),
        Decimal('0.00'),
    )
    expected_refunded = sum(
        (row['subtotal'] for row in source if row['estado_pago'] == 'reembolsado'),
        Decimal('0.00'),
    )
    weeks = {_week_for_row(row) for row in source}
    actual_net = Decimal('0.00')
    actual_refunded = Decimal('0.00')
    for week in weeks:
        summaries = list(cassandra.execute(
                'SELECT ingresos_netos, ingresos_reembolsados FROM resumen_productos_semana WHERE semana_inicio=%s',
                (week,),
            ))
        actual_net += sum((row.ingresos_netos for row in summaries), Decimal('0.00'))
        actual_refunded += sum(
            (row.ingresos_reembolsados for row in summaries), Decimal('0.00')
        )
        trends = product_trends(week, cassandra)
        assert all('variacion_unidades' in item for item in trends)
    assert actual_net == expected_net
    assert actual_refunded == expected_refunded
    close_cassandra()


def test_outbox_dispatches_analytics_without_mongo(monkeypatch):
    captured = []
    monkeypatch.setattr(
        'app.services.analytics_service.project_order',
        lambda order_id: captured.append(order_id),
    )
    project_event(SimpleNamespace(
        tipo_evento='analytics.pedido_actualizado',
        agregado_id='341',
        producto_ref=None,
    ))
    assert captured == [341]
