"""Contrato de estados que puede controlar un vendedor."""

from app.api.v1.vendor import _estados_vendedor


def test_vendor_states_come_from_vendor_suborder_enum():
    states = _estados_vendedor()
    assert states == ['confirmado', 'preparando', 'enviado', 'entregado']
    assert 'pendiente' not in states
    assert 'cancelado' not in states
    assert 'reembolsado' not in states
