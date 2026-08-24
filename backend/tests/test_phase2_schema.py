"""Pruebas de contrato para la estructura aditiva de Fase 2."""

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text


load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

DB_URL = (
    f"mysql+pymysql://{os.getenv('MYSQL_USER', 'tiendaya')}:"
    f"{os.getenv('MYSQL_PASSWORD', 'tiendaya123')}@"
    f"{os.getenv('MYSQL_HOST', 'localhost')}:"
    f"{os.getenv('MYSQL_PORT', '3306')}/"
    f"{os.getenv('MYSQL_DB', 'tiendaya')}?charset=utf8mb4"
)

engine = create_engine(DB_URL, pool_pre_ping=True)


def test_phase2_tables_exist():
    required = {
        'ofertas', 'oferta_precios_historial',
        'pedido_vendedores', 'pedido_direcciones', 'outbox_eventos',
    }
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT TABLE_NAME
            FROM information_schema.TABLES
            WHERE TABLE_SCHEMA = DATABASE()
        """))
        installed = {row[0] for row in rows}
    assert required <= installed


def test_phase2_columns_are_required_after_cutover():
    required = {
        ('inventario', 'oferta_id'),
        ('pedido_lineas', 'pedido_vendedor_id'),
        ('pedido_lineas', 'oferta_id'),
        ('pedido_lineas', 'sku_snapshot'),
        ('pedido_lineas', 'vendedor_nombre_snapshot'),
    }
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT TABLE_NAME, COLUMN_NAME, IS_NULLABLE
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
        """))
        columns = {(row[0], row[1]): row[2] for row in rows}
    assert required <= set(columns)
    assert all(columns[column] == 'NO' for column in required)


def test_phase2_foreign_keys_exist():
    required = {
        'fk_oferta_vendedor', 'fk_oph_oferta', 'fk_oph_usuario',
        'fk_pv_pedido', 'fk_pv_vendedor', 'fk_pd_pedido',
        'fk_inv_oferta', 'fk_pl_pedido_vendedor', 'fk_pl_oferta',
    }
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT CONSTRAINT_NAME
            FROM information_schema.REFERENTIAL_CONSTRAINTS
            WHERE CONSTRAINT_SCHEMA = DATABASE()
        """))
        installed = {row[0] for row in rows}
    assert required <= installed


def test_phase2_transition_is_closed():
    """Después del corte ninguna referencia operativa nueva admite NULL."""
    with engine.connect() as conn:
        nullable = conn.execute(text("""
            SELECT COUNT(*)
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND (
                (TABLE_NAME = 'inventario' AND COLUMN_NAME = 'oferta_id')
                OR (TABLE_NAME = 'pedido_lineas' AND COLUMN_NAME IN (
                    'pedido_vendedor_id', 'oferta_id', 'sku_snapshot',
                    'vendedor_nombre_snapshot'
                ))
              )
              AND IS_NULLABLE = 'NO'
        """)).scalar_one()
    assert nullable == 5
