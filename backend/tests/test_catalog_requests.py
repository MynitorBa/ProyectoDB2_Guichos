"""Contrato relacional y validaciones del flujo de solicitudes."""

import pytest
from pydantic import ValidationError
from sqlalchemy import text

from app.api.v1.catalog_requests import OfferProposalCreate, ProductProposalCreate
from app.core.db_mysql import engine


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
