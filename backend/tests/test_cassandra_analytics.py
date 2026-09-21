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
    product_weekly_trend,
    rebuild_all,
)
from app.services.outbox_service import project_event


def test_week_is_monday_in_guatemala():
    # Lunes 00:30 UTC todavía es domingo en Guatemala.
    assert current_week_start(datetime(2026, 9, 14, 0, 30, tzinfo=timezone.utc)) == date(2026, 9, 7)
    assert current_week_start(datetime(2026, 9, 14, 6, 0, tzinfo=timezone.utc)) == date(2026, 9, 14)


def _summary(product_ref, week, units):
    return SimpleNamespace(
        producto_ref=product_ref,
        semana_inicio=week,
        producto_nombre_snapshot='Producto de prueba',
        imagen_snapshot=None,
        unidades_vendidas=units,
        ingresos_brutos=Decimal(units * 10),
        ingresos_reembolsados=Decimal('0.00'),
        ingresos_netos=Decimal(units * 10),
        pedidos_distintos=units,
        vendedores_distintos=1,
        ofertas_distintas=1,
        unidades_flash=0,
    )


def test_product_without_current_sales_remains_in_weekly_comparison():
    class FakeCassandra:
        def execute(self, _query, params):
            return [] if params[0] == date(2026, 9, 14) else [
                _summary('abc', date(2026, 9, 7), 3)
            ]

    rows = product_trends(date(2026, 9, 14), FakeCassandra())
    assert rows[0]['producto_ref'] == 'abc'
    assert rows[0]['unidades'] == 0
    assert rows[0]['unidades_semana_anterior'] == 3
    assert rows[0]['variacion_unidades'] == -3
    assert rows[0]['variacion_porcentaje'] == -100.0


def test_product_comparison_accepts_up_to_four_previous_weeks():
    class FakeCassandra:
        def execute(self, _query, params):
            units = {
                date(2026, 9, 21): 5,
                date(2026, 9, 14): 4,
                date(2026, 9, 7): 3,
                date(2026, 8, 31): 2,
                date(2026, 8, 24): 1,
            }
            return [_summary('abc', params[0], units[params[0]])]

    rows = product_trends(
        date(2026, 9, 21), FakeCassandra(), comparison_weeks=4
    )
    assert [week['unidades'] for week in rows[0]['semanas']] == [5, 4, 3, 2, 1]
    assert rows[0]['variacion_unidades'] == 1


def test_product_timeline_fills_weeks_without_sales_with_zero():
    class FakeCassandra:
        def execute(self, _query, _params):
            return [_summary('abc', date(2026, 9, 7), 2)]

    rows = product_weekly_trend(
        'abc', date(2026, 9, 7), date(2026, 9, 21), FakeCassandra()
    )
    assert [item['unidades'] for item in rows] == [2, 0, 0]
    assert rows[1]['variacion_unidades'] == -2
    assert rows[1]['variacion_porcentaje'] == -100.0


def test_backfill_is_idempotent_and_matches_mysql():
    cassandra = get_cassandra_session()
    with SessionLocal() as db:
        source = _paid_lines(db)
        first = rebuild_all(db, cassandra)
        second = rebuild_all(db, cassandra)
    assert first == second
    assert first['lineas'] == len(source)
    assert cassandra.execute('SELECT COUNT(*) FROM ventas_producto_semana').one()[0] == len(source)
    assert cassandra.execute('SELECT COUNT(*) FROM tendencia_producto_semana').one()[0] == len({
        (_week_for_row(row), row['producto_ref']) for row in source
    })
    assert cassandra.execute(
        'SELECT COUNT(*) FROM tendencia_producto_vendedor_semana'
    ).one()[0] == len({
        (row['vendedor_id'], row['producto_ref'], _week_for_row(row)) for row in source
    })

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
