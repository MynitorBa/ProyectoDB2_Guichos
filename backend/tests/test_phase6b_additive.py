"""Integridad de la identidad mínima de producto y las nuevas FKs."""

from sqlalchemy import text

from app.core.db_mongo import get_mongo_db
from app.core.db_mysql import engine


def test_phase6b_structure_is_installed():
    with engine.connect() as conn:
        table = conn.execute(text("""
            SELECT COUNT(*) FROM information_schema.TABLES
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'producto_referencias'
        """)).scalar_one()
        fks = {
            row[0]
            for row in conn.execute(text("""
                SELECT CONSTRAINT_NAME
                FROM information_schema.REFERENTIAL_CONSTRAINTS
                WHERE CONSTRAINT_SCHEMA = DATABASE()
                  AND CONSTRAINT_NAME IN (
                    'fk_res_producto_referencia', 'fk_mi_inventario'
                  )
            """))
        }
        nullable = conn.execute(text("""
            SELECT TABLE_NAME, COLUMN_NAME, IS_NULLABLE
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE() AND (
              (TABLE_NAME = 'resenas' AND COLUMN_NAME = 'producto_referencia_id')
              OR (TABLE_NAME = 'movimientos_inventario' AND COLUMN_NAME = 'inventario_id')
            )
        """)).all()
    assert table == 1
    assert fks == {'fk_res_producto_referencia', 'fk_mi_inventario'}
    assert len(nullable) == 2
    assert all(row[2] == 'NO' for row in nullable)


def test_legacy_product_storage_is_physically_retired():
    with engine.connect() as conn:
        legacy_tables = conn.execute(text("""
            SELECT COUNT(*) FROM information_schema.TABLES
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'productos'
        """)).scalar_one()
        legacy_columns = conn.execute(text("""
            SELECT COUNT(*) FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND COLUMN_NAME = 'producto_id'
              AND TABLE_NAME IN (
                'carrito_items', 'inventario', 'movimientos_inventario',
                'pedido_lineas', 'resenas'
              )
        """)).scalar_one()
        count = conn.execute(text(
            'SELECT COUNT(*) FROM producto_referencias'
        )).scalar_one()
    assert legacy_tables == 0
    assert legacy_columns == 0
    assert count == get_mongo_db().productos.count_documents({})


def test_reviews_and_movements_have_consistent_new_references():
    with engine.connect() as conn:
        bad_reviews = conn.execute(text("""
            SELECT COUNT(*) FROM resenas r
            LEFT JOIN producto_referencias pr
              ON pr.id = r.producto_referencia_id
            WHERE pr.id IS NULL
        """)).scalar_one()
        bad_movements = conn.execute(text("""
            SELECT COUNT(*) FROM movimientos_inventario mi
            LEFT JOIN inventario i ON i.id = mi.inventario_id
            WHERE i.id IS NULL
        """)).scalar_one()
        review_count = conn.execute(text('SELECT COUNT(*) FROM resenas')).scalar_one()
        movement_count = conn.execute(text(
            'SELECT COUNT(*) FROM movimientos_inventario'
        )).scalar_one()
    assert bad_reviews == 0
    assert bad_movements == 0
    # La migración deja como mínimo los 42 registros de reseñas y los 29
    # movimientos del conjunto inicial. En una base funcional estos totales
    # pueden crecer legítimamente después de compras, reseñas o ajustes.
    assert review_count >= 42
    assert movement_count >= 29
