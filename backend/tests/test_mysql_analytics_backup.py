from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

from app.services.analytics_mysql_backup import MySQLAnalyticsAdapter, summarize_week
from app.services import analytics_mysql_backup as backup
from app.services.analytics_service import product_trends, vendor_offer_summary
from app.api.v1 import analytics as analytics_api
from app.services.outbox_service import enqueue_outbox


def _row(line, *, refunded=False, vendor=3, offer=7, flash=False):
    return {
        'pedido_linea_id': line, 'pedido_id': line, 'oferta_id': offer,
        'producto_ref': 'abc', 'producto_nombre_snapshot': 'Producto',
        'sku_snapshot': 'SKU-1', 'vendedor_id': vendor,
        'fecha_hora': datetime(2026, 9, 14, 8, tzinfo=timezone.utc),
        'cantidad': 2, 'subtotal': Decimal('20.00'),
        'estado_pago': 'reembolsado' if refunded else 'aprobado',
        'promocion_flash_id': 1 if flash else None,
    }


def test_backup_uses_same_paid_refund_and_flash_rules_as_cassandra():
    products, vendor_products, offers = summarize_week([
        _row(1, flash=True), _row(2, refunded=True), _row(3, vendor=4, offer=8),
    ])
    assert len(products) == 1
    item = products[0]
    assert item['semana_inicio'] == date(2026, 9, 14)
    assert item['unidades_vendidas'] == 4
    assert item['ingresos_brutos'] == Decimal('60.00')
    assert item['ingresos_reembolsados'] == Decimal('20.00')
    assert item['ingresos_netos'] == Decimal('40.00')
    assert item['pedidos_distintos'] == 2
    assert item['vendedores_distintos'] == 2
    assert item['ofertas_distintas'] == 2
    assert item['unidades_flash'] == 2
    assert len(vendor_products) == 2
    assert len(offers) == 2


def test_backup_keeps_guatemala_monday_boundary():
    row = _row(1)
    row['fecha_hora'] = datetime(2026, 9, 14, 5, tzinfo=timezone.utc)
    products, _, _ = summarize_week([row])
    assert products[0]['semana_inicio'] == date(2026, 9, 7)


def test_existing_trend_contract_accepts_backup_adapter():
    class BackupAdapter:
        def execute(self, query, params):
            if 'resumen_productos_semana' in query and params[0] == date(2026, 9, 14):
                return [SimpleNamespace(
                    producto_ref='abc', producto_nombre_snapshot='Producto', imagen_snapshot=None,
                    unidades_vendidas=2, ingresos_brutos=Decimal('20.00'),
                    ingresos_reembolsados=Decimal('0.00'), ingresos_netos=Decimal('20.00'),
                    pedidos_distintos=1, vendedores_distintos=1, ofertas_distintas=1,
                    unidades_flash=0,
                )]
            return []

    adapter = BackupAdapter()
    assert product_trends(date(2026, 9, 14), adapter)[0]['unidades'] == 2


def test_cassandra_failure_uses_ready_mysql_backup(monkeypatch):
    class ReadyAdapter:
        def __init__(self, db):
            assert db is not None

        def ready(self):
            return True

    monkeypatch.setattr(analytics_api.salud, 'disponible', lambda motor: False)
    monkeypatch.setattr(analytics_api, 'MySQLAnalyticsAdapter', ReadyAdapter)
    values, source, _ = analytics_api._analytics_call(
        lambda week, cassandra: [week], object(), date(2026, 9, 14))
    assert values == [date(2026, 9, 14)]
    assert source == 'mysql_respaldo'


def test_vendor_backup_query_keeps_authenticated_vendor_filter():
    calls = []

    class FakeDB:
        def execute(self, statement, params):
            calls.append((str(statement), params))
            return []

    adapter = MySQLAnalyticsAdapter(FakeDB())
    assert vendor_offer_summary(14, date(2026, 9, 14), adapter) == []
    assert len(calls) == 1
    assert calls[0][1] == {'vendor': 14, 'week': date(2026, 9, 14)}
    assert 'vendedor_id=:vendor' in calls[0][0]


def test_reprocessing_same_week_replaces_rows_instead_of_adding(monkeypatch):
    monkeypatch.setattr(backup, '_paid_lines', lambda db, week: [_row(1)])
    monkeypatch.setattr('app.core.db_mongo.get_mongo_db', lambda: object())
    monkeypatch.setattr(backup, '_product_images', lambda mongo, refs: {})

    class FakeDB:
        def __init__(self):
            self.tables = {table: [] for table in backup.TABLES}
            self.commits = 0

        def execute(self, statement, values=None):
            sql = str(statement)
            if sql.startswith('SELECT producto_ref, imagen_snapshot'):
                return SimpleNamespace(all=lambda: [])
            for table in backup.TABLES:
                if sql.startswith(f'DELETE FROM {table}'):
                    self.tables[table].clear()
                if sql.startswith(f'INSERT INTO {table}'):
                    self.tables[table].extend(values)
            return []

        def commit(self):
            self.commits += 1

        def rollback(self):
            raise AssertionError('No debe fallar el recálculo')

    db = FakeDB()
    first = backup.rebuild_week_mysql(date(2026, 9, 14), db)
    second = backup.rebuild_week_mysql(date(2026, 9, 14), db)
    assert first['lineas'] == second['lineas'] == 1
    assert [len(db.tables[table]) for table in backup.TABLES] == [1, 1, 1]
    assert db.commits == 2


def test_analytics_outbox_keeps_cassandra_and_mysql_independent():
    class FakeSession:
        def __init__(self):
            self.rows = []

        def add(self, row):
            self.rows.append(row)

    db = FakeSession()
    enqueue_outbox(db, tipo_evento='analytics.pedido_actualizado', agregado_tipo='pedido',
                   agregado_id=12, producto_ref=None, payload={})
    assert {event.destino for event in db.rows} == {
        'cassandra', 'analitica_mysql', 'busqueda',
    }
    assert all(event.agregado_id == '12' for event in db.rows)
