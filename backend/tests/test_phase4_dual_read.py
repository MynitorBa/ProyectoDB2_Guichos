"""Contrato de lectura dual MongoDB + ofertas MySQL."""

import os

from dotenv import load_dotenv
from pymongo import MongoClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.services.catalog_service import listar_productos, obtener_producto


load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
DB_URL = (
    f"mysql+pymysql://{os.getenv('MYSQL_USER', 'tiendaya')}:"
    f"{os.getenv('MYSQL_PASSWORD', 'tiendaya123')}@"
    f"{os.getenv('MYSQL_HOST', 'localhost')}:"
    f"{os.getenv('MYSQL_PORT', '3306')}/"
    f"{os.getenv('MYSQL_DB', 'tiendaya')}?charset=utf8mb4"
)
engine = create_engine(DB_URL, pool_pre_ping=True)
Session = sessionmaker(bind=engine)


def mongo_database():
    client = MongoClient(os.getenv('MONGO_URI'), serverSelectionTimeoutMS=5000)
    return client, client[os.getenv('MONGO_DB', 'tiendaya')]


def test_phase4_cart_offer_contract_is_installed():
    with engine.connect() as conn:
        column = conn.execute(text("""
            SELECT COUNT(*) FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'carrito_items' AND COLUMN_NAME = 'oferta_id'
        """)).scalar_one()
        fk = conn.execute(text("""
            SELECT COUNT(*) FROM information_schema.REFERENTIAL_CONSTRAINTS
            WHERE CONSTRAINT_SCHEMA = DATABASE()
              AND CONSTRAINT_NAME = 'fk_ci_oferta'
        """)).scalar_one()
        unique_offer = conn.execute(text("""
            SELECT COUNT(*) FROM information_schema.STATISTICS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'carrito_items'
              AND INDEX_NAME = 'uq_ci_carrito_oferta'
        """)).scalar_one()
    assert column == 1
    assert fk == 1
    assert unique_offer >= 1


def test_catalog_uses_mysql_offer_price_and_stock():
    client, mongo = mongo_database()
    db = Session()
    try:
        result = listar_productos(mongo, db, page=1, page_size=10)
        assert result['dual_read']['source'] == 'mongodb+mysql'
        assert result['items']
        for item in result['items']:
            row = db.execute(text("""
                SELECT o.precio_actual,
                       GREATEST(0, SUM(i.cantidad_disponible - i.cantidad_reservada)) stock
                FROM ofertas o
                JOIN inventario i ON i.oferta_id = o.id
                WHERE o.id = :offer_id
                GROUP BY o.id, o.precio_actual
            """), {'offer_id': item['oferta_id']}).one()
            assert item['precio'] == float(row[0])
            assert item['stock'] == int(row[1])
    finally:
        db.close()
        client.close()


def test_product_detail_exposes_all_active_offers():
    client, mongo = mongo_database()
    db = Session()
    try:
        doc = mongo.productos.find_one({'estado': 'activo'})
        detail = obtener_producto(mongo, str(doc['_id']), db)
        expected = db.execute(text("""
            SELECT COUNT(*) FROM ofertas
            WHERE producto_ref = :ref AND estado = 'activa'
        """), {'ref': str(doc['_id'])}).scalar_one()
        assert detail['ofertas_count'] == expected
        assert len(detail['ofertas']) == expected
        assert detail['oferta_id'] == detail['ofertas'][0]['oferta_id']
    finally:
        db.close()
        client.close()
