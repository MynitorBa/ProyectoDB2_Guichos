"""Contrato estructural e integridad cruzada de variantes dinámicas."""

from bson import ObjectId
from sqlalchemy import text

from app.core.db_mongo import get_mongo_db
from app.core.db_mysql import engine
from app.services.variant_service import (
    generate_variant_sku, normalize_variant_attributes, variant_key,
)


def test_variant_identity_is_independent_from_attribute_order():
    first = normalize_variant_attributes({'RAM': '32 GB', 'Color': 'Negro'})
    second = normalize_variant_attributes({'color': 'Negro', 'ram': '32 GB'})
    assert first == second
    assert variant_key(first) == variant_key(second)
    assert generate_variant_sku('COM-ABC12345', first) == generate_variant_sku(
        'COM-ABC12345', second
    )


def test_dynamic_variant_mysql_contract_is_installed():
    with engine.connect() as conn:
        nullable = conn.execute(text("""
            SELECT IS_NULLABLE FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'ofertas'
              AND COLUMN_NAME = 'producto_variante_id'
        """)).scalar_one()
        fks = {
            row[0] for row in conn.execute(text("""
                SELECT CONSTRAINT_NAME
                FROM information_schema.REFERENTIAL_CONSTRAINTS
                WHERE CONSTRAINT_SCHEMA = DATABASE()
                  AND CONSTRAINT_NAME IN (
                    'fk_pvr_producto', 'fk_oferta_variante',
                    'fk_sc_variante_solicitada'
                  )
            """))
        }
        unique_index = conn.execute(text("""
            SELECT COUNT(*) FROM information_schema.STATISTICS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'ofertas'
              AND INDEX_NAME = 'uq_oferta_vendedor_variante'
              AND NON_UNIQUE = 0
        """)).scalar_one()
    assert nullable == 'NO'
    assert fks == {
        'fk_pvr_producto', 'fk_oferta_variante',
        'fk_sc_variante_solicitada',
    }
    assert unique_index > 0


def test_every_offer_uses_a_variant_of_its_product():
    with engine.connect() as conn:
        invalid = conn.execute(text("""
            SELECT COUNT(*)
            FROM ofertas o
            LEFT JOIN producto_variante_referencias pvr
              ON pvr.id = o.producto_variante_id
            LEFT JOIN producto_referencias pr
              ON pr.id = pvr.producto_referencia_id
            WHERE pvr.id IS NULL OR pr.producto_ref <> o.producto_ref
        """)).scalar_one()
    assert invalid == 0


def test_variant_registry_matches_mongo_documents():
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT pvr.id, pvr.variante_ref, pr.producto_ref
            FROM producto_variante_referencias pvr
            JOIN producto_referencias pr ON pr.id = pvr.producto_referencia_id
        """)).mappings().all()
        products_without_variant = conn.execute(text("""
            SELECT COUNT(*)
            FROM producto_referencias pr
            LEFT JOIN producto_variante_referencias pvr
              ON pvr.producto_referencia_id = pr.id
            WHERE pvr.id IS NULL
        """)).scalar_one()

    variants = get_mongo_db().producto_variantes
    mismatches = []
    for row in rows:
        document = variants.find_one(
            {'_id': ObjectId(row['variante_ref'])}, {'producto_ref': 1}
        )
        if not document or document.get('producto_ref') != row['producto_ref']:
            mismatches.append(row['id'])
    assert products_without_variant == 0
    assert mismatches == []


def test_mongo_variant_identity_indexes_are_unique():
    indexes = get_mongo_db().producto_variantes.index_information()
    assert indexes['uidx_variante_producto_clave']['unique'] is True
    assert indexes['uidx_variante_sku']['unique'] is True
