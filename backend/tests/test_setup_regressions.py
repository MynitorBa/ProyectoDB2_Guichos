"""Regresiones del instalador descubiertas al probar la rama en otro equipo."""

import sys
from pathlib import Path

from bson import ObjectId
from sqlalchemy import text

from app.core.db_mongo import get_mongo_db
from app.core.db_mysql import engine


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS_DIR))

import seed_mongo_events  # noqa: E402,F401
from sync_mongo_projections import (  # noqa: E402
    PRIMARY_OFFERS_SQL,
    projection_from_row,
)


def test_seed_module_imports_datetime_and_is_loadable():
    assert seed_mongo_events.datetime is not None
    assert callable(seed_mongo_events.generar_eventos_producto)


def test_projection_contains_the_commercial_fields_verified_by_setup():
    projection = projection_from_row({
        'oferta_id': 8,
        'precio_actual': 1299,
        'moneda': 'GTQ',
        'stock': 44,
        'vendedor_id': 1,
        'vendedor_usuario_id': 2,
        'nombre_comercial': 'TechZone Guatemala',
        'ofertas_count': 2,
    })
    assert projection == {
        'oferta_id': 8,
        'precio': 1299.0,
        'moneda': 'GTQ',
        'stock': 44,
        'disponible': True,
        'vendedor_id': 1,
        'vendedor_usuario_id': 2,
        'vendedor_nombre': 'TechZone Guatemala',
        'ofertas_count': 2,
    }


def test_runtime_index_and_all_existing_projections_are_synchronized():
    mongo = get_mongo_db()
    index = mongo.producto_eventos.index_information().get(
        'uidx_evento_outbox', {}
    )
    assert index.get('unique') is True

    with engine.connect() as connection:
        rows = connection.execute(text(PRIMARY_OFFERS_SQL)).mappings().all()

    mismatches = []
    for row in rows:
        doc = mongo.productos.find_one(
            {'_id': ObjectId(row['producto_ref'])},
            {'precio': 1, 'stock': 1, 'vendedor_id': 1,
             'vendedor_nombre': 1, 'oferta_id': 1, 'ofertas_count': 1},
        )
        expected = projection_from_row(dict(row))
        if not doc or any(doc.get(key) != expected[key] for key in (
            'precio', 'stock', 'vendedor_id', 'vendedor_nombre',
            'oferta_id', 'ofertas_count',
        )):
            mismatches.append(row['producto_ref'])
    assert mismatches == []
