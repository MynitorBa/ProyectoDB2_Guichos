#!/usr/bin/env python3
"""Instala índices y sincroniza la proyección comercial MySQL -> MongoDB.

Es seguro repetirlo: solo usa ``$set`` sobre productos existentes y la creación
de índices de PyMongo es idempotente. No elimina documentos ni historial.
"""

import os
import sys
from pathlib import Path

import pymysql
from bson import ObjectId
from dotenv import load_dotenv
from pymongo import MongoClient


BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.core.db_mongo import ensure_indexes  # noqa: E402


load_dotenv(BACKEND_DIR / '.env')


PRIMARY_OFFERS_SQL = """
    WITH oferta_stock AS (
      SELECT o.id AS oferta_id, o.producto_ref, o.precio_actual, o.moneda,
             o.vendedor_id, v.usuario_id AS vendedor_usuario_id,
             v.nombre_comercial,
             GREATEST(0, COALESCE(SUM(
               i.cantidad_disponible - i.cantidad_reservada
             ), 0)) AS stock
      FROM ofertas o
      JOIN vendedores v ON v.id = o.vendedor_id
      LEFT JOIN inventario i ON i.oferta_id = o.id
      WHERE o.estado = 'activa'
      GROUP BY o.id, o.producto_ref, o.precio_actual, o.moneda,
               o.vendedor_id, v.usuario_id, v.nombre_comercial
    ), ranked AS (
      SELECT oferta_stock.*,
             COUNT(*) OVER (PARTITION BY producto_ref) AS ofertas_count,
             ROW_NUMBER() OVER (
               PARTITION BY producto_ref
               ORDER BY (stock > 0) DESC, precio_actual, oferta_id
             ) AS rn
      FROM oferta_stock
    )
    SELECT oferta_id, producto_ref, precio_actual, moneda, vendedor_id,
           vendedor_usuario_id,
           nombre_comercial, stock, ofertas_count
    FROM ranked
    WHERE rn = 1
    ORDER BY producto_ref
"""


def projection_from_row(row: dict) -> dict:
    stock = max(0, int(row['stock'] or 0))
    return {
        'oferta_id': int(row['oferta_id']),
        'precio': float(row['precio_actual']),
        'moneda': row['moneda'],
        'stock': stock,
        'disponible': stock > 0,
        'vendedor_id': int(row['vendedor_id']),
        'vendedor_usuario_id': int(row['vendedor_usuario_id']),
        'vendedor_nombre': row['nombre_comercial'],
        'ofertas_count': int(row['ofertas_count']),
    }


def synchronize(connection, mongo) -> dict:
    ensure_indexes(mongo)
    with connection.cursor() as cursor:
        cursor.execute(PRIMARY_OFFERS_SQL)
        rows = cursor.fetchall()

    matched = 0
    modified = 0
    missing: list[str] = []
    for row in rows:
        producto_ref = row['producto_ref']
        try:
            object_id = ObjectId(producto_ref)
        except Exception:
            missing.append(producto_ref)
            continue
        result = mongo.productos.update_one(
            {'_id': object_id},
            {'$set': projection_from_row(row)},
        )
        matched += result.matched_count
        modified += result.modified_count
        if result.matched_count != 1:
            missing.append(producto_ref)

    return {
        'offers': len(rows),
        'matched': matched,
        'modified': modified,
        'missing': missing,
    }


def main() -> int:
    connection = pymysql.connect(
        host=os.getenv('MYSQL_HOST', 'localhost'),
        port=int(os.getenv('MYSQL_PORT', 3306)),
        db=os.getenv('MYSQL_DB', 'tiendaya'),
        user=os.getenv('MYSQL_USER', 'tiendaya'),
        password=os.getenv('MYSQL_PASSWORD', 'tiendaya123'),
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor,
    )
    client = MongoClient(
        os.getenv(
            'MONGO_URI',
            'mongodb://admin:adminpassword@localhost:27017/tiendaya?authSource=admin',
        ),
        serverSelectionTimeoutMS=5000,
    )
    try:
        mongo = client[os.getenv('MONGO_DB', 'tiendaya')]
        summary = synchronize(connection, mongo)
        print('Índices MongoDB de ejecución instalados.')
        print(
            'Proyecciones comerciales: '
            f"{summary['matched']}/{summary['offers']} encontradas; "
            f"{summary['modified']} actualizadas."
        )
        if summary['missing']:
            print(
                'ERROR: referencias sin documento MongoDB: '
                + ', '.join(summary['missing']),
                file=sys.stderr,
            )
            return 1
        return 0
    except Exception as exc:
        print(f'ERROR al sincronizar proyecciones MongoDB: {exc}', file=sys.stderr)
        return 1
    finally:
        connection.close()
        client.close()


if __name__ == '__main__':
    raise SystemExit(main())
