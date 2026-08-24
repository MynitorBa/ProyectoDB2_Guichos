"""Integridad final entre categorías, referencias y ofertas."""

from bson import ObjectId
from sqlalchemy import text

from app.core.db_mongo import get_mongo_db
from app.core.db_mysql import engine


def test_phase7_column_and_foreign_keys_are_installed():
    with engine.connect() as conn:
        nullable = conn.execute(text("""
            SELECT IS_NULLABLE FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'producto_referencias'
              AND COLUMN_NAME = 'categoria_id'
        """)).scalar_one()
        fks = {
            row[0] for row in conn.execute(text("""
                SELECT CONSTRAINT_NAME
                FROM information_schema.REFERENTIAL_CONSTRAINTS
                WHERE CONSTRAINT_SCHEMA = DATABASE()
                  AND CONSTRAINT_NAME IN (
                    'fk_pr_categoria', 'fk_oferta_producto_referencia'
                  )
            """))
        }
    assert nullable == 'NO'
    assert fks == {'fk_pr_categoria', 'fk_oferta_producto_referencia'}


def test_every_reference_has_category_and_every_offer_has_reference():
    with engine.connect() as conn:
        invalid_categories = conn.execute(text("""
            SELECT COUNT(*) FROM producto_referencias pr
            LEFT JOIN categorias c ON c.id = pr.categoria_id
            WHERE c.id IS NULL
        """)).scalar_one()
        invalid_offers = conn.execute(text("""
            SELECT COUNT(*) FROM ofertas o
            LEFT JOIN producto_referencias pr
              ON pr.producto_ref = o.producto_ref
            WHERE pr.id IS NULL
        """)).scalar_one()
    assert invalid_categories == 0
    assert invalid_offers == 0


def test_mysql_category_matches_mongo_document_slug():
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT pr.id, pr.producto_ref, c.slug
            FROM producto_referencias pr
            JOIN categorias c ON c.id = pr.categoria_id
        """)).mappings().all()
    products = get_mongo_db().productos
    mismatches = []
    for row in rows:
        doc = products.find_one(
            {'_id': ObjectId(row['producto_ref'])}, {'categoria.slug': 1}
        )
        if not doc or doc.get('categoria', {}).get('slug') != row['slug']:
            mismatches.append(row['id'])
    assert mismatches == []
