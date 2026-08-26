"""Pruebas de integridad y cobertura del backfill de Fase 3."""

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


def scalar(conn, query):
    return conn.execute(text(query)).scalar_one()


def test_every_product_has_offer_and_current_price():
    with engine.connect() as conn:
        products = scalar(conn, 'SELECT COUNT(*) FROM producto_referencias')
        covered = scalar(conn, """
            SELECT COUNT(DISTINCT p.id)
            FROM producto_referencias p
            JOIN ofertas o ON o.producto_ref = p.producto_ref
        """)
        without_current_price = scalar(conn, """
            SELECT COUNT(*)
            FROM ofertas o
            LEFT JOIN oferta_precios_historial h
              ON h.oferta_id = o.id AND h.vigente_hasta IS NULL
            WHERE h.id IS NULL
        """)
    assert covered == products
    assert without_current_price == 0


def test_inventory_is_linked_to_the_matching_offer():
    with engine.connect() as conn:
        invalid = scalar(conn, """
            SELECT COUNT(*)
            FROM inventario i
            LEFT JOIN ofertas o ON o.id = i.oferta_id
            WHERE o.id IS NULL
        """)
    assert invalid == 0


def test_order_lines_have_consistent_offer_vendor_and_snapshots():
    with engine.connect() as conn:
        invalid = scalar(conn, """
            SELECT COUNT(*)
            FROM pedido_lineas pl
            LEFT JOIN ofertas o ON o.id = pl.oferta_id
            LEFT JOIN pedido_vendedores pv ON pv.id = pl.pedido_vendedor_id
            LEFT JOIN vendedores v ON v.id = o.vendedor_id
            WHERE o.id IS NULL OR pv.id IS NULL
               OR pv.pedido_id <> pl.pedido_id
               OR pv.vendedor_id <> o.vendedor_id
               OR o.producto_ref <> pl.producto_ref
               OR pl.sku_snapshot IS NULL
               OR pl.vendedor_nombre_snapshot IS NULL
               OR pl.vendedor_nombre_snapshot <> v.nombre_comercial
        """)
    assert invalid == 0


def test_vendor_order_subtotals_match_historical_lines():
    with engine.connect() as conn:
        invalid = scalar(conn, """
            SELECT COUNT(*)
            FROM pedido_vendedores pv
            JOIN (
              SELECT pedido_vendedor_id, SUM(subtotal_linea) AS subtotal
              FROM pedido_lineas
              GROUP BY pedido_vendedor_id
            ) x ON x.pedido_vendedor_id = pv.id
            WHERE pv.subtotal <> x.subtotal
        """)
        groups = scalar(conn, """
            SELECT COUNT(*) FROM (
              SELECT pedido_id, vendedor_id
              FROM pedido_vendedores
              GROUP BY pedido_id, vendedor_id
            ) x
        """)
        parts = scalar(conn, 'SELECT COUNT(*) FROM pedido_vendedores')
    assert invalid == 0
    assert groups == parts


def test_every_order_has_an_address_snapshot():
    with engine.connect() as conn:
        orders = scalar(conn, 'SELECT COUNT(*) FROM pedidos')
        snapshots = scalar(conn, 'SELECT COUNT(*) FROM pedido_direcciones')
        empty_names = scalar(conn, """
            SELECT COUNT(*) FROM pedido_direcciones
            WHERE TRIM(receptor_nombre) = ''
        """)
    assert snapshots == orders
    assert empty_names == 0
