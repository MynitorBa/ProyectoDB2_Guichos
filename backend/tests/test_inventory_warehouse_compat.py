"""Regresión de bodegas sin abrir conexiones ni escribir en bases de datos."""

import unittest
from types import SimpleNamespace as Row
from unittest.mock import patch

from app.services import checkout_service, offer_service


def inventory(identifier, warehouse, available, reserved=0, offer_id=77):
    return Row(id=identifier, oferta_id=offer_id, bodega=warehouse,
               cantidad_disponible=available, cantidad_reservada=reserved)


class QueryRows:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *args):
        return self

    def order_by(self, *args):
        return self

    def with_for_update(self):
        return self

    def all(self):
        return self.rows


class ScalarRows:
    def __init__(self, rows):
        self.rows = rows

    def scalars(self):
        return self

    def all(self):
        return self.rows

    def scalar_one(self):
        if len(self.rows) != 1:
            raise AssertionError('Se esperaba exactamente un resultado')
        return self.rows[0]

    def __iter__(self):
        return iter(self.rows)


class LockedSession:
    def __init__(self, results, flash_inventory_ids=()):
        self.results = iter(results)
        self.flash_inventory_ids = flash_inventory_ids
        self.rolled_back = False

    def execute(self, statement):
        return ScalarRows(next(self.results))

    def rollback(self):
        self.rolled_back = True

    def query(self, model):
        return QueryRows([(identifier,) for identifier in self.flash_inventory_ids])


class WarehouseCompatibilityTests(unittest.TestCase):
    def test_principal_only(self):
        self.assertEqual(offer_service.seleccionar_inventario(
            [inventory(1, 'principal', 8)], 5).id, 1)

    def test_demo_only(self):
        self.assertEqual(offer_service.seleccionar_inventario(
            [inventory(2, 'demo-principal', 8)], 5).id, 2)

    def test_principal_has_priority_when_both_cover_line(self):
        rows = [inventory(2, 'demo-principal', 100), inventory(1, 'principal', 8)]
        self.assertEqual(offer_service.seleccionar_inventario(rows, 5).id, 1)

    def test_fallback_without_splitting_line(self):
        rows = [inventory(1, 'principal', 3), inventory(2, 'demo-principal', 5)]
        self.assertEqual(offer_service.stock_comprable(rows), 5)
        self.assertEqual(offer_service.seleccionar_inventario(rows, 5).id, 2)
        self.assertIsNone(offer_service.seleccionar_inventario(rows, 8))

    def test_both_insufficient_or_missing(self):
        rows = [inventory(1, 'principal', 3), inventory(2, 'demo-principal', 5)]
        self.assertIsNone(offer_service.seleccionar_inventario(rows, 6))
        self.assertIsNone(offer_service.seleccionar_inventario([], 1))

    def test_reserved_units_reduce_stock_without_adding_warehouses(self):
        rows = [inventory(1, 'principal', 8, 6), inventory(2, 'demo-principal', 5, 1)]
        self.assertEqual(offer_service.stock_comprable(rows), 4)
        self.assertEqual(offer_service.seleccionar_inventario(rows, 3).id, 2)

    def test_catalog_and_cart_use_stock_of_one_warehouse(self):
        rows = [inventory(1, 'principal', 3), inventory(2, 'demo-principal', 5)]
        session = Row(query=lambda model: QueryRows(rows))
        self.assertEqual(offer_service.stock_by_offer(session, [77]), {77: 5})

    def test_confirm_and_compensation_recover_original_reservation_row(self):
        # T2 usa el movimiento persistido por T1 incluso si principal adquirió stock.
        primary = inventory(1, 'principal', 100)
        demo = inventory(2, 'demo-principal', 5, 2)
        movement = Row(inventario_id=2)
        session = LockedSession([[Row(id=77)], [], [primary, demo], [movement]])
        _, _, selected = checkout_service._bloquear_recursos(session, Row(id=900), [77])
        self.assertIs(selected[77], demo)

    def test_pending_order_without_identifiable_reservation_does_not_guess(self):
        session = LockedSession([[Row(id=77)], [],
                                 [inventory(1, 'principal', 100)], []])
        with self.assertRaises(checkout_service.PedidoNoCumplible):
            checkout_service._bloquear_recursos(session, Row(id=900), [77])
        self.assertTrue(session.rolled_back)

    def test_flash_keeps_its_principal_inventory(self):
        reservation = Row(promocion_id=12)
        session = LockedSession([
            [Row(id=77)], [reservation], [Row(id=12, oferta_id=77)],
            [inventory(1, 'principal', 5, 2), inventory(2, 'demo-principal', 100)], [],
        ], flash_inventory_ids=(1,))
        _, _, selected = checkout_service._bloquear_recursos(session, Row(id=900), [77])
        self.assertEqual(selected[77].id, 1)

    def test_flash_created_in_demo_keeps_its_inventory(self):
        session = LockedSession([
            [Row(id=77)], [Row(promocion_id=12)], [Row(id=12, oferta_id=77)],
            [inventory(1, 'principal', 100), inventory(2, 'demo-principal', 5, 2)], [],
        ], flash_inventory_ids=(2,))
        _, _, selected = checkout_service._bloquear_recursos(session, Row(id=900), [77])
        self.assertEqual(selected[77].id, 2)

    def test_flash_without_original_inventory_movement_does_not_guess(self):
        session = LockedSession([
            [Row(id=77)], [Row(promocion_id=12)], [Row(id=12, oferta_id=77)],
            [inventory(1, 'principal', 100)], [],
        ])
        with self.assertRaises(checkout_service.PedidoNoCumplible):
            checkout_service._bloquear_recursos(session, Row(id=900), [77])
        self.assertTrue(session.rolled_back)

    def test_edit_existing_demo_row_without_creating_another(self):
        demo = inventory(2, 'demo-principal', 8, 2)
        added = []
        session = Row(query=lambda model: QueryRows([demo]), add=added.append,
                      flush=lambda: None)
        offer = Row(id=77, producto_ref='a' * 24, version=1, estado='activa')
        with patch.object(offer_service, 'registrar_saldo_inventario'), patch.object(
            offer_service, 'enqueue_primary_offer_projection'
        ):
            offer_service.editar_oferta(session, oferta=offer, usuario_id=1, stock=4)
        self.assertEqual(demo.cantidad_disponible, 4)
        self.assertFalse(any(isinstance(row, offer_service.Inventario) for row in added))

    def test_edit_cannot_ignore_reservations_in_other_warehouse(self):
        rows = [inventory(1, 'principal', 8, 0), inventory(2, 'demo-principal', 10, 5)]
        session = Row(query=lambda model: QueryRows(rows))
        offer = Row(id=77, version=1)
        with self.assertRaises(offer_service.HTTPException):
            offer_service.editar_oferta(session, oferta=offer, usuario_id=1, stock=4)

    def test_edit_targets_warehouse_that_supplies_advertised_stock(self):
        primary = inventory(1, 'principal', 2)
        demo = inventory(2, 'demo-principal', 100)
        self.assertIs(offer_service.inventario_operativo([primary, demo]), demo)
        self.assertIs(offer_service.inventario_operativo(
            [primary, inventory(2, 'demo-principal', 2)]), primary)


if __name__ == '__main__':
    unittest.main()
