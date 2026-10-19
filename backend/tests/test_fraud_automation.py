from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services import fraud_detection_service as fraud
from app.services.fraud_analysis_worker import serve
from app.core.config import Settings


class _Result:
    def __init__(self, rows=None, row=None):
        self.rows = rows or []
        self.row = row

    def data(self):
        return self.rows

    def single(self):
        return self.row


class _Neo:
    def __init__(self, results=None):
        self.results = list(results or [])
        self.calls = []

    def run(self, query, **params):
        self.calls.append((query, params))
        return self.results.pop(0) if self.results else _Result()


def test_f01_separates_public_verified_from_historical_reviews():
    public = _Neo()
    fraud.detectar_bombardeo(public)
    assert 'r.verificada = true' in public.calls[0][0]
    assert "r.estado = 'aprobada'" in public.calls[0][0]

    historical = _Neo()
    fraud.detectar_bombardeo(
        historical, segmento=fraud.SEGMENTO_HISTORICO,
    )
    assert 'r.verificada = false' in historical.calls[0][0]


def test_f02_returns_one_aggregated_row_per_user_and_vendor():
    neo = _Neo()
    fraud.detectar_reviewer_unico_vendedor(neo, min_resenas=2)
    query = neo.calls[0][0]
    assert 'collect(DISTINCT v)' in query
    assert 'count(DISTINCT r)' in query
    assert 'vendedores[0] AS v' in query
    assert 'MATCH (u)-[:ESCRIBIO]->(r2' not in query


def test_f03_keeps_pair_order_and_segments_both_reviews():
    neo = _Neo()
    fraud.detectar_cluster_coordinado(neo)
    query = neo.calls[0][0]
    assert 'u1.id < u2.id' in query
    assert 'r1.verificada = true' in query
    assert 'r2.verificada = true' in query
    assert 'count(DISTINCT p)' in query


def test_f04_total_is_independent_from_display_limit():
    neo = _Neo([
        _Result(rows=[{'resena_id': 'mysql:1'}]),
        _Result(row={'total': 73}),
    ])
    items = fraud.detectar_sin_compra(neo, limite=5)
    total = fraud.contar_sin_compra(neo)
    assert len(items) == 1
    assert total == 73
    assert neo.calls[0][1]['limite'] == 5
    assert 'LIMIT' not in neo.calls[1][0]


def test_f05_has_configurable_recent_window_and_discloses_ownership_limit():
    now = datetime(2026, 10, 18, 12, 0, 0)
    neo = _Neo()
    fraud.detectar_autocompras(neo, ventana_dias=30, ahora=now)
    query, params = neo.calls[0]
    assert 'c.pagada = true' in query
    assert 'datetime(c.fecha) >= datetime($desde)' in query
    assert params['desde'] == (now - timedelta(days=30)).isoformat()
    assert 'propiedad_historica_verificada' in query

    historical = _Neo()
    fraud.detectar_autocompras(historical, historico=True, ahora=now)
    assert 'datetime(c.fecha) >= datetime($desde)' not in historical.calls[0][0]
    assert 'historial_completo_propietario_actual' == historical.calls[0][1]['alcance']


def test_f06_pairs_only_after_sale_and_never_reuses_a_sale():
    base = datetime(2026, 10, 1, 10, 0, 0)
    sales = [
        SimpleNamespace(id=1, fecha=base),
        SimpleNamespace(id=2, fecha=base + timedelta(hours=1)),
    ]
    replenishments = [
        SimpleNamespace(id=10, fecha=base + timedelta(hours=2)),
        SimpleNamespace(id=11, fecha=base + timedelta(hours=3)),
        SimpleNamespace(id=12, fecha=base - timedelta(hours=1)),
    ]
    pairs = fraud.correlacionar_ventas_reposiciones(sales, replenishments)
    assert pairs == [(2, 10), (1, 11)]
    assert len({sale for sale, _ in pairs}) == len(pairs)


def test_f06_paid_sale_query_requires_order_line_payment_and_valid_state():
    source = Path(fraud.__file__).read_text(encoding='utf-8')
    assert "MovimientoInventario.tipo == 'salida'" in source
    assert "Pago.estado == 'aprobado'" in source
    assert "Pedido.estado.in_([" in source
    assert "'confirmado', 'preparando', 'enviado_parcial', 'enviado'" in source
    assert 'MovimientoInventario.cantidad == cantidad_lineas' in source
    assert 'MovimientoInventario.pedido_id.isnot(None)' in source


class _StopAfter:
    def __init__(self, calls):
        self.calls = calls
        self.waits = []

    def is_set(self):
        return False

    def wait(self, seconds):
        self.waits.append(seconds)
        return len(self.waits) > self.calls


def test_worker_uses_controlled_3600_second_interval_and_stops_cleanly():
    stop = _StopAfter(calls=1)
    origins = []
    serve(
        stop, interval_seconds=3600,
        due_seconds=lambda: 0,
        run_once=lambda origin: origins.append(origin) or {'estado': 'exitosa'},
    )
    assert origins == ['automatico']
    assert stop.waits == [0, 3600.0]


def test_worker_is_disabled_by_default():
    assert Settings.model_fields['FRAUD_ANALYSIS_ENABLED'].default is False


def test_migration_is_additive_and_f07_is_not_implemented():
    root = Path(__file__).resolve().parents[2]
    migration = (root / 'database/mysql/23_fraud_automation.sql').read_text(encoding='utf-8')
    assert 'CREATE TABLE IF NOT EXISTS fraud_analysis_runs' in migration
    assert "COLUMN_NAME='activa'" in migration
    assert 'COINCIDE_CANTIDAD' not in migration
    assert 'MovimientoInventario' not in migration


def test_invalid_review_segment_is_rejected():
    with pytest.raises(ValueError):
        fraud.detectar_bombardeo(_Neo(), segmento='mezcladas')
