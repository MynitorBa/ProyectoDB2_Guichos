from datetime import datetime, timedelta
from types import SimpleNamespace

from app.services.fraud_detection_service import correlacionar_cantidades_exactas


def row(**values):
    return SimpleNamespace(**values)


def test_f07_matches_exact_quantity_once():
    base = datetime(2026, 10, 1, 12)
    result = correlacionar_cantidades_exactas(
        [row(linea_id=1, pedido_id=10, oferta_id=7, cantidad=4, fecha=base)],
        [row(movimiento_id=20, oferta_id=7, cantidad=4, fecha=base + timedelta(days=2))],
    )
    assert [(p['linea_id'], p['movimiento_id']) for p in result['pares']] == [(1, 20)]
    assert result['ambiguos'] == []


def test_f07_excludes_wrong_quantity_before_purchase_and_outside_window():
    base = datetime(2026, 10, 1, 12)
    purchases = [row(linea_id=1, pedido_id=10, oferta_id=7, cantidad=4, fecha=base)]
    movements = [
        row(movimiento_id=20, oferta_id=7, cantidad=3, fecha=base + timedelta(days=1)),
        row(movimiento_id=21, oferta_id=7, cantidad=4, fecha=base - timedelta(hours=1)),
        row(movimiento_id=22, oferta_id=7, cantidad=4, fecha=base + timedelta(days=31)),
    ]
    result = correlacionar_cantidades_exactas(purchases, movements)
    assert result == {'pares': [], 'ambiguos': []}


def test_f07_does_not_reuse_one_restock_for_ambiguous_purchases():
    base = datetime(2026, 10, 1, 12)
    purchases = [
        row(linea_id=1, pedido_id=10, oferta_id=7, cantidad=4, fecha=base),
        row(linea_id=2, pedido_id=11, oferta_id=7, cantidad=4, fecha=base + timedelta(hours=1)),
    ]
    movements = [
        row(movimiento_id=20, oferta_id=7, cantidad=4, fecha=base + timedelta(days=1)),
    ]
    result = correlacionar_cantidades_exactas(purchases, movements)
    assert result['pares'] == []
    assert result['ambiguos'][0]['lineas_candidatas'] == [1, 2]


def test_f07_multiple_restock_candidates_are_ambiguous():
    base = datetime(2026, 10, 1, 12)
    result = correlacionar_cantidades_exactas(
        [row(linea_id=1, pedido_id=10, oferta_id=7, cantidad=4, fecha=base)],
        [
            row(movimiento_id=20, oferta_id=7, cantidad=4, fecha=base + timedelta(days=1)),
            row(movimiento_id=21, oferta_id=7, cantidad=4, fecha=base + timedelta(days=2)),
        ],
    )
    assert result['pares'] == []
    assert len(result['ambiguos']) == 2
    assert all(row['movimientos_candidatos'] == [20, 21] for row in result['ambiguos'])
