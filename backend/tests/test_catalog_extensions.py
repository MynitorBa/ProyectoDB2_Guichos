"""Integridad de imágenes BLOB y clasificación múltiple del catálogo."""

from sqlalchemy import text

from app.core.db_mysql import engine
from app.schemas.producto import ProductoCreate


def test_catalog_extension_tables_columns_and_fks_are_installed():
    with engine.connect() as connection:
        tables = {row[0] for row in connection.execute(text("""
            SELECT TABLE_NAME FROM information_schema.TABLES
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME IN (
                'producto_imagenes', 'producto_referencia_categorias'
              )
        """))}
        sku_prefix = connection.execute(text("""
            SELECT COUNT(*) FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'categorias'
              AND COLUMN_NAME = 'sku_prefix'
        """)).scalar_one()
        fks = {row[0] for row in connection.execute(text("""
            SELECT CONSTRAINT_NAME
            FROM information_schema.REFERENTIAL_CONSTRAINTS
            WHERE CONSTRAINT_SCHEMA = DATABASE()
              AND CONSTRAINT_NAME IN (
                'fk_pi_referencia', 'fk_prc_referencia', 'fk_prc_categoria'
              )
        """))}
    assert tables == {'producto_imagenes', 'producto_referencia_categorias'}
    assert sku_prefix == 1
    assert fks == {'fk_pi_referencia', 'fk_prc_referencia', 'fk_prc_categoria'}


def test_every_product_has_one_matching_primary_category():
    with engine.connect() as connection:
        invalid = connection.execute(text("""
            SELECT COUNT(*)
            FROM producto_referencias pr
            LEFT JOIN (
              SELECT producto_referencia_id,
                     COUNT(*) AS total,
                     SUM(es_principal = 1) AS principales,
                     MAX(CASE WHEN es_principal = 1 THEN categoria_id END)
                       AS categoria_principal
              FROM producto_referencia_categorias
              GROUP BY producto_referencia_id
            ) prc ON prc.producto_referencia_id = pr.id
            WHERE prc.total IS NULL OR prc.principales <> 1
               OR prc.categoria_principal <> pr.categoria_id
        """)).scalar_one()
    assert invalid == 0


def test_product_payload_rejects_negative_commercial_values():
    valid = {
        'nombre': 'Producto de prueba',
        'precio': 10,
        'categoria_slugs': ['computadoras'],
        'stock': 1,
    }
    ProductoCreate(**valid)
    for field in ('precio', 'stock'):
        payload = {**valid, field: -1}
        try:
            ProductoCreate(**payload)
        except ValueError:
            continue
        raise AssertionError(f'{field} negativo fue aceptado')
