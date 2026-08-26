"""Contrato relacional y validaciones del flujo de solicitudes."""

import pytest
from pydantic import ValidationError
from sqlalchemy import text

from app.api.v1.admin import OfferCreate
from app.api.v1.catalog_requests import OfferProposalCreate, ProductProposalCreate
from app.core.db_mongo import get_mongo_db
from app.core.db_mysql import engine
from app.schemas.producto import ProductoCreate
from app.services.category_attribute_service import (
    AttributeValidationError,
    validate_category_attributes,
)
from app.services.sku_service import generate_product_sku


def test_catalog_request_schema_and_foreign_keys_are_installed():
    with engine.connect() as connection:
        tables = {row[0] for row in connection.execute(text("""
            SELECT TABLE_NAME FROM information_schema.TABLES
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME IN (
              'solicitudes_catalogo', 'solicitud_catalogo_categorias',
              'solicitud_catalogo_imagenes'
            )
        """))}
        owner_column = connection.execute(text("""
            SELECT COUNT(*) FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'producto_imagenes'
              AND COLUMN_NAME = 'subida_por'
        """)).scalar_one()
        fks = {row[0] for row in connection.execute(text("""
            SELECT CONSTRAINT_NAME FROM information_schema.REFERENTIAL_CONSTRAINTS
            WHERE CONSTRAINT_SCHEMA = DATABASE() AND CONSTRAINT_NAME IN (
              'fk_sc_vendedor', 'fk_sc_producto_solicitado',
              'fk_sc_revisada_por', 'fk_sc_producto_resultado',
              'fk_sc_oferta_resultado', 'fk_scc_solicitud',
              'fk_scc_categoria', 'fk_sci_solicitud', 'fk_sci_imagen',
              'fk_pi_subida_por'
            )
        """))}
    assert tables == {
        'solicitudes_catalogo', 'solicitud_catalogo_categorias',
        'solicitud_catalogo_imagenes',
    }
    assert owner_column == 1
    assert len(fks) == 10


def test_offer_request_rejects_images_and_invalid_commercial_values():
    valid = {'producto_ref': 'a' * 24, 'precio': 10, 'stock': 1}
    OfferProposalCreate(**valid)
    with pytest.raises(ValidationError):
        OfferProposalCreate(**valid, imagen_ids=[1])
    with pytest.raises(ValidationError):
        OfferProposalCreate(**{**valid, 'precio': 0})
    with pytest.raises(ValidationError):
        OfferProposalCreate(**{**valid, 'stock': -1})


def test_new_product_request_requires_categories():
    with pytest.raises(ValidationError):
        ProductProposalCreate(
            nombre='Producto', categoria_slugs=[], precio=10, stock=1
        )


def test_manual_sku_is_rejected_in_every_creation_contract():
    with pytest.raises(ValidationError):
        ProductProposalCreate(
            nombre='Producto', categoria_slugs=['computadoras'],
            precio=10, stock=1, sku='MANUAL-1',
        )
    with pytest.raises(ValidationError):
        OfferProposalCreate(
            producto_ref='a' * 24, precio=10, stock=1, sku='MANUAL-2',
        )
    with pytest.raises(ValidationError):
        ProductoCreate(
            nombre='Producto', categoria_slugs=['computadoras'], precio=10,
            vendedor_usuario_id=1, sku='MANUAL-3',
        )
    with pytest.raises(ValidationError):
        OfferCreate(vendedor_id=1, precio=10, stock=1, sku='MANUAL-4')


def test_product_sku_uses_category_prefix_and_expected_format():
    sku = generate_product_sku(get_mongo_db(), 'COM')
    assert len(sku) == 12
    assert sku.startswith('COM-')
    assert all(character in '0123456789ABCDEF' for character in sku[4:])


def test_attributes_are_combined_and_validated_for_all_categories():
    mongo = get_mongo_db()
    slugs = ['computadoras', 'audio']
    definitions = {}
    for schema in mongo.categoria_esquemas.find(
        {'categoria_slug': {'$in': slugs}}
    ):
        for field in schema.get('atributos', []):
            definitions[field['nombre']] = field
    values = {}
    for name, field in definitions.items():
        if field['tipo'] == 'number':
            values[name] = 1
        elif field['tipo'] == 'boolean':
            values[name] = False
        else:
            values[name] = 'Prueba'
    normalized = validate_category_attributes(mongo, slugs, values)
    assert set(normalized) == set(definitions)
    required_name = next(
        name for name, field in definitions.items() if field.get('requerido')
    )
    values.pop(required_name)
    with pytest.raises(AttributeValidationError):
        validate_category_attributes(mongo, slugs, values)
