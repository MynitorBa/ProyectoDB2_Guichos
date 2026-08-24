#!/usr/bin/env python3
"""
Genera historial sintético de eventos para los últimos 6 meses.
Produce entre 4 y 8 eventos por producto: cambios de precio, descripción,
disponibilidad y atributos. La secuencia es cronológica y verosímil.

Cada producto tiene su evento PRODUCTO_CREADO y luego eventos posteriores,
de modo que se puede demostrar la reconstrucción de estado en cualquier fecha.
"""
import sys
import os
import random
from datetime import timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from pymongo import MongoClient
from dotenv import load_dotenv

from app.core.time import utc_now

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

MONGO_URI = os.getenv('MONGO_URI', 'mongodb://admin:adminpassword@localhost:27017/tiendaya?authSource=admin')
MONGO_DB  = os.getenv('MONGO_DB', 'tiendaya')

random.seed(42)


def fecha_hace_dias(dias: int, variacion: int = 0) -> datetime:
    d = utc_now() - timedelta(days=dias)
    if variacion:
        d += timedelta(hours=random.randint(-variacion, variacion))
    return d


def generar_eventos_producto(producto: dict) -> list[dict]:
    """Genera una secuencia creíble de eventos para un producto."""
    pid = str(producto['_id'])
    precio_actual = producto.get('precio', 100)
    desc_actual   = producto.get('descripcion', '')
    disponible    = producto.get('disponible', True)
    atributos     = producto.get('atributos', {})
    estado        = producto.get('estado', 'activo')

    eventos = []
    version = 1

    # ── Evento 1: PRODUCTO_CREADO (hace ~6 meses) ─────────────────────────────
    ts_creacion = producto.get('fecha_creacion') or fecha_hace_dias(180)
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
    version += 1

    # ── Evento 2: PRECIO_ACTUALIZADO (hace ~4 meses — precio de lanzamiento era más alto) ─
    precio_lanzamiento = round(precio_actual * 1.08, 2)
    ts_precio1 = fecha_hace_dias(120, 12)
    eventos.append({
        'producto_id': pid,
        'tipo_evento': 'PRECIO_ACTUALIZADO',
        'datos_anteriores': {'precio': precio_lanzamiento},
        'datos_nuevos': {'precio': precio_actual},
        'usuario_id': '1',
        'timestamp': ts_precio1,
        'version': version,
    })
    version += 1

    # ── Evento 3: DESCRIPCION_ACTUALIZADA (hace ~3 meses — mejoró el copy) ───
    ts_desc = fecha_hace_dias(90, 6)
    nueva_desc = f"{desc_actual} — Actualizado con descripción mejorada."
    eventos.append({
        'producto_id': pid,
        'tipo_evento': 'DESCRIPCION_ACTUALIZADA',
        'datos_anteriores': {'descripcion': desc_actual},
        'datos_nuevos': {'descripcion': nueva_desc},
        'usuario_id': '1',
        'timestamp': ts_desc,
        'version': version,
    })
    version += 1

    # ── Evento 4: DISPONIBILIDAD_CAMBIADA (hace ~2 meses — agotado temporalmente) ─
    ts_disp_off = fecha_hace_dias(60, 4)
    eventos.append({
        'producto_id': pid,
        'tipo_evento': 'DISPONIBILIDAD_CAMBIADA',
        'datos_anteriores': {'disponible': True},
        'datos_nuevos': {'disponible': False},
        'usuario_id': '1',
        'timestamp': ts_disp_off,
        'version': version,
    })
    version += 1

    # ── Evento 5: DISPONIBILIDAD_CAMBIADA (hace ~50 días — repuesto el stock) ─
    ts_disp_on = fecha_hace_dias(50, 3)
    eventos.append({
        'producto_id': pid,
        'tipo_evento': 'DISPONIBILIDAD_CAMBIADA',
        'datos_anteriores': {'disponible': False},
        'datos_nuevos': {'disponible': True},
        'usuario_id': '1',
        'timestamp': ts_disp_on,
        'version': version,
    })
    version += 1

    # ── Evento 6: PRECIO_ACTUALIZADO (hace ~30 días — oferta de temporada) ──
    precio_oferta = round(precio_actual * 0.90, 2)
    ts_precio2 = fecha_hace_dias(30, 6)
    eventos.append({
        'producto_id': pid,
        'tipo_evento': 'PRECIO_ACTUALIZADO',
        'datos_anteriores': {'precio': precio_actual},
        'datos_nuevos': {'precio': precio_oferta},
        'usuario_id': '1',
        'timestamp': ts_precio2,
        'version': version,
    })
    version += 1

    # ── Evento 7: PRECIO_ACTUALIZADO (hace ~10 días — fin de oferta) ─────────
    ts_precio3 = fecha_hace_dias(10, 3)
    eventos.append({
        'producto_id': pid,
        'tipo_evento': 'PRECIO_ACTUALIZADO',
        'datos_anteriores': {'precio': precio_oferta},
        'datos_nuevos': {'precio': precio_actual},
        'usuario_id': '1',
        'timestamp': ts_precio3,
        'version': version,
    })
    version += 1

    # ── Evento 8 (opcional): ATRIBUTOS_ACTUALIZADOS en el 30% de los productos ─
    if random.random() < 0.3 and atributos:
        ts_attr = fecha_hace_dias(5, 2)
        nuevo_attr = dict(atributos)
        keys = list(nuevo_attr.keys())
        if keys:
            nuevo_attr['nota_adicional'] = 'Especificación revisada por el vendedor'
        eventos.append({
            'producto_id': pid,
            'tipo_evento': 'ATRIBUTOS_ACTUALIZADOS',
            'datos_anteriores': {'atributos': atributos},
            'datos_nuevos': {'atributos': nuevo_attr},
            'usuario_id': '1',
            'timestamp': ts_attr,
            'version': version,
        })
        version += 1

    return eventos


def main():
    client = MongoClient(MONGO_URI)
    mongo  = client[MONGO_DB]

    productos = list(mongo.productos.find({}))
    if not productos:
        print('No hay productos en MongoDB. Ejecuta primero migrate_products_to_mongo.py')
        sys.exit(1)

    # Limpiar eventos existentes para que el script sea idempotente
    mongo.producto_eventos.delete_many({})
    print(f'Colección producto_eventos limpiada.')

    todos_eventos = []
    for producto in productos:
        todos_eventos.extend(generar_eventos_producto(producto))

    if todos_eventos:
        mongo.producto_eventos.insert_many(todos_eventos)

    print(f'Productos procesados: {len(productos)}')
    print(f'Eventos generados:    {len(todos_eventos)}')
    print(f'Promedio eventos/producto: {len(todos_eventos)/len(productos):.1f}')
    print('\nEjemplo — primeros 3 eventos del primer producto:')
    pid = str(productos[0]['_id'])
    for e in mongo.producto_eventos.find({'producto_id': pid}).sort('version', 1).limit(3):
        print(f"  v{e['version']} | {e['tipo_evento']} | {e['timestamp'].strftime('%Y-%m-%d')}")

    client.close()
    print('\nHistorial generado correctamente.')


if __name__ == '__main__':
    main()
