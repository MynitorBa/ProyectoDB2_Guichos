#!/usr/bin/env python3
"""
Inicializa el evento documental PRODUCTO_CREADO de productos sin historial.

Precio, oferta e inventario pertenecen a los historiales temporales de MySQL;
no se fabrican fechas anteriores a la creación ni eventos operativos en MongoDB.
"""
import sys
import os
import argparse
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from pymongo import MongoClient
from dotenv import load_dotenv

from app.core.time import utc_now

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

MONGO_URI = os.getenv('MONGO_URI', 'mongodb://admin:adminpassword@localhost:27017/tiendaya?authSource=admin')
MONGO_DB  = os.getenv('MONGO_DB', 'tiendaya')

def generar_eventos_producto(producto: dict) -> list[dict]:
    """Genera únicamente el origen documental verificable del producto."""
    pid = str(producto['_id'])
    precio_actual = producto.get('precio', 100)
    desc_actual   = producto.get('descripcion', '')
    disponible    = producto.get('disponible', True)
    atributos     = producto.get('atributos', {})
    estado        = producto.get('estado', 'activo')

    eventos = []
    version = 1

    ts_creacion = producto.get('fecha_creacion') or utc_now()
    if isinstance(ts_creacion, str):
        ts_creacion = datetime.fromisoformat(ts_creacion)

    eventos.append({
        'producto_id': pid,
        'tipo_evento': 'PRODUCTO_CREADO',
        'datos_anteriores': {},
        'datos_nuevos': {
            'nombre': producto.get('nombre'),
            'precio': precio_actual,
            'descripcion': desc_actual,
            'disponible': True,
            'atributos': atributos,
            'estado': 'activo',
        },
        'usuario_id': '1',
        'timestamp': ts_creacion,
        'version': version,
    })
    return eventos


def main(*, reset: bool = False):
    client = MongoClient(MONGO_URI)
    mongo  = client[MONGO_DB]

    productos = list(mongo.productos.find({}))
    if not productos:
        print('No hay productos en MongoDB. Ejecuta primero migrate_products_to_mongo.py')
        sys.exit(1)

    if reset:
        mongo.producto_eventos.delete_many({})
        print('Colección producto_eventos limpiada.')

    ids_productos = {str(producto['_id']) for producto in productos}
    productos_con_historial = set(
        mongo.producto_eventos.distinct('producto_id')
    ) & ids_productos

    todos_eventos = []
    for producto in productos:
        if str(producto['_id']) in productos_con_historial:
            continue
        todos_eventos.extend(generar_eventos_producto(producto))

    if todos_eventos:
        mongo.producto_eventos.insert_many(todos_eventos)

    print(f'Productos encontrados: {len(productos)}')
    print(f'Productos ya historiados: {len(productos_con_historial)}')
    print(f'Productos procesados: {len(productos) - len(productos_con_historial)}')
    print(f'Eventos generados:    {len(todos_eventos)}')
    nuevos = len(productos) - len(productos_con_historial)
    if nuevos:
        print(f'Promedio eventos/producto nuevo: {len(todos_eventos)/nuevos:.1f}')
        print('\nEjemplo — primeros 3 eventos del primer producto:')
        pid = str(productos[0]['_id'])
        for e in mongo.producto_eventos.find({'producto_id': pid}).sort('version', 1).limit(3):
            print(f"  v{e['version']} | {e['tipo_evento']} | {e['timestamp'].strftime('%Y-%m-%d')}")

    client.close()
    print('\nHistorial generado correctamente.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Inicializa historial documental faltante.')
    parser.add_argument(
        '--reset',
        action='store_true',
        help='Elimina todo el historial antes de regenerarlo (operación destructiva).',
    )
    args = parser.parse_args()
    main(reset=args.reset)
