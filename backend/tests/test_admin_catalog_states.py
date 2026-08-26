"""El catálogo público y el inventario administrativo tienen alcances distintos."""

from app.core.db_mongo import get_mongo_db
from app.core.db_mysql import SessionLocal
from app.services.catalog_service import listar_productos


def test_admin_listing_includes_every_product_state():
    mongo = get_mongo_db()
    with SessionLocal() as db:
        admin = listar_productos(
            mongo, db, estado=None, page=1, page_size=100, orden='nombre_asc'
        )
        public = listar_productos(
            mongo, db, estado='activo', page=1, page_size=100
        )

    assert admin['total'] == mongo.productos.count_documents({})
    assert public['total'] == mongo.productos.count_documents({'estado': 'activo'})
    assert admin['total'] >= public['total']


def test_admin_listing_can_filter_inactive_products_and_search_sku():
    mongo = get_mongo_db()
    inactive = mongo.productos.find_one({'estado': 'inactivo'})
    if not inactive:
        return
    with SessionLocal() as db:
        result = listar_productos(
            mongo,
            db,
            estado='inactivo',
            q=inactive.get('sku') or inactive.get('nombre'),
            page=1,
            page_size=100,
        )
    assert str(inactive['_id']) in {item['_id'] for item in result['items']}
