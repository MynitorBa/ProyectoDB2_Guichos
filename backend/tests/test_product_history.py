"""
Pruebas del servicio de historial de productos.
"""
import pytest
from datetime import datetime, timedelta
from pymongo import MongoClient
import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

MONGO_URI = os.getenv('MONGO_URI', 'mongodb://admin:adminpassword@localhost:27017/tiendaya?authSource=admin')
MONGO_DB  = os.getenv('MONGO_DB', 'tiendaya')


@pytest.fixture
def mongo_db():
    client = MongoClient(MONGO_URI)
    db = client[MONGO_DB]
    yield db
    client.close()


def test_reconstruir_estado_en_fecha(mongo_db):
    """Verifica que la reconstrucción devuelve el estado correcto en una fecha intermedia."""
    from app.services.product_history_service import reconstruir_estado, registrar_evento

    # Crear un producto de prueba para el test
    ahora = datetime.utcnow()
    doc = mongo_db.productos.insert_one({
        'sku': 'TEST-HIST-001',
        'nombre': 'Producto de prueba historial',
        'precio': 100.0,
        'estado': 'activo',
        'disponible': True,
    })
    prod_id = str(doc.inserted_id)

    try:
        # Registrar evento de creación
        registrar_evento(
            mongo_db, prod_id, 'PRODUCTO_CREADO',
            {}, {'nombre': 'Producto de prueba historial', 'precio': 100.0,
                 'descripcion': 'Original', 'disponible': True, 'atributos': {}, 'estado': 'activo'},
            usuario_id='1'
        )
        # Forzar timestamps para simular historia
        mongo_db.producto_eventos.update_one(
            {'producto_id': prod_id, 'version': 1},
            {'$set': {'timestamp': ahora - timedelta(days=30)}}
        )

        # Cambio de precio hace 20 días
        registrar_evento(
            mongo_db, prod_id, 'PRECIO_ACTUALIZADO',
            {'precio': 100.0}, {'precio': 90.0}, usuario_id='1'
        )
        mongo_db.producto_eventos.update_one(
            {'producto_id': prod_id, 'version': 2},
            {'$set': {'timestamp': ahora - timedelta(days=20)}}
        )

        # Cambio de precio hace 5 días (precio actual)
        registrar_evento(
            mongo_db, prod_id, 'PRECIO_ACTUALIZADO',
            {'precio': 90.0}, {'precio': 110.0}, usuario_id='1'
        )
        mongo_db.producto_eventos.update_one(
            {'producto_id': prod_id, 'version': 3},
            {'$set': {'timestamp': ahora - timedelta(days=5)}}
        )

        # Reconstruir hace 15 días → precio debería ser 90.0 (después del primer cambio)
        estado_15 = reconstruir_estado(mongo_db, prod_id, ahora - timedelta(days=15))
        assert estado_15 is not None
        assert estado_15['precio'] == 90.0, f'Precio esperado 90.0, obtenido: {estado_15["precio"]}'

        # Reconstruir hace 25 días → precio original 100.0
        estado_25 = reconstruir_estado(mongo_db, prod_id, ahora - timedelta(days=25))
        assert estado_25 is not None
        assert estado_25['precio'] == 100.0, f'Precio esperado 100.0, obtenido: {estado_25["precio"]}'

        # Reconstruir hoy → precio actual 110.0
        estado_hoy = reconstruir_estado(mongo_db, prod_id, ahora)
        assert estado_hoy is not None
        assert estado_hoy['precio'] == 110.0, f'Precio esperado 110.0, obtenido: {estado_hoy["precio"]}'

        # Reconstruir antes de la creación → None
        estado_antes = reconstruir_estado(mongo_db, prod_id, ahora - timedelta(days=60))
        assert estado_antes is None

    finally:
        # Limpiar
        mongo_db.productos.delete_one({'_id': doc.inserted_id})
        mongo_db.producto_eventos.delete_many({'producto_id': prod_id})


def test_historial_completitud(mongo_db):
    """Verifica que todos los productos migrados tienen al menos un evento."""
    total_productos = mongo_db.productos.count_documents({})
    if total_productos == 0:
        pytest.skip('No hay productos en MongoDB (ejecutar migración primero)')

    productos_sin_historial = 0
    for prod in mongo_db.productos.find({}, {'_id': 1}):
        prod_id = str(prod['_id'])
        count = mongo_db.producto_eventos.count_documents({'producto_id': prod_id})
        if count == 0:
            productos_sin_historial += 1

    assert productos_sin_historial == 0, (
        f'{productos_sin_historial} productos sin historial de eventos. '
        f'Ejecuta seed_mongo_events.py'
    )
