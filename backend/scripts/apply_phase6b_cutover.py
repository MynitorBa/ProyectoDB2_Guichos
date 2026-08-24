#!/usr/bin/env python3
"""Respalda, valida y ejecuta el corte físico de la Fase 6B."""

import json
import os
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pymysql
from bson import ObjectId
from dotenv import load_dotenv
from pymongo import MongoClient

from run_sql_migration import run_sql_file


BACKEND_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BACKEND_DIR.parent
MIGRATION = ROOT_DIR / 'database' / 'mysql' / '10_phase6b_cutover.sql'
BACKUP_DIR = ROOT_DIR / 'backups'
load_dotenv(BACKEND_DIR / '.env')


def json_default(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bytes):
        return {'encoding': 'hex', 'data': value.hex()}
    raise TypeError(f'Tipo no serializable: {type(value).__name__}')


def mysql_connection():
    return pymysql.connect(
        host=os.getenv('MYSQL_HOST', 'localhost'),
        port=int(os.getenv('MYSQL_PORT', 3306)),
        db=os.getenv('MYSQL_DB', 'tiendaya'),
        user=os.getenv('MYSQL_USER', 'tiendaya'),
        password=os.getenv('MYSQL_PASSWORD', 'tiendaya123'),
        charset='utf8mb4',
        autocommit=True,
        cursorclass=pymysql.cursors.DictCursor,
    )


def validate_mongo(connection):
    with connection.cursor() as cursor:
        cursor.execute(
            'SELECT id, producto_ref FROM producto_referencias ORDER BY id'
        )
        refs = cursor.fetchall()
        cursor.execute(
            'SELECT p.id, p.producto_ref, pi.url '
            'FROM productos p JOIN producto_imagenes pi ON pi.producto_id = p.id '
            'ORDER BY p.id, pi.id'
        )
        legacy_images = cursor.fetchall()
    client = MongoClient(os.getenv('MONGO_URI'), serverSelectionTimeoutMS=5000)
    try:
        products = client[os.getenv('MONGO_DB', 'tiendaya')].productos
        missing = []
        for row in refs:
            try:
                found = products.count_documents(
                    {'_id': ObjectId(row['producto_ref'])}, limit=1
                )
            except Exception:
                found = 0
            if not found:
                missing.append(row)
        if missing:
            raise RuntimeError(
                f'Hay {len(missing)} referencias SQL sin producto MongoDB'
            )
        missing_images = []
        for row in legacy_images:
            doc = products.find_one(
                {'_id': ObjectId(row['producto_ref'])}, {'imagenes.url': 1}
            )
            urls = {
                image.get('url') for image in (doc or {}).get('imagenes', [])
                if isinstance(image, dict)
            }
            if row['url'] not in urls:
                missing_images.append(row['id'])
        if missing_images:
            raise RuntimeError(
                f'Hay {len(missing_images)} imágenes SQL no verificadas en MongoDB'
            )
        return len(refs), len(legacy_images)
    finally:
        client.close()


def create_backup(connection):
    tables = (
        'productos', 'producto_imagenes', 'producto_referencias', 'resenas',
        'inventario', 'movimientos_inventario', 'carrito_items',
        'pedido_lineas', 'ofertas', 'oferta_precios_historial',
    )
    payload = {
        'created_at': datetime.now().astimezone().isoformat(),
        'database': os.getenv('MYSQL_DB', 'tiendaya'),
        'phase': '6B-physical-cutover',
        'tables': {},
    }
    with connection.cursor() as cursor:
        for table in tables:
            cursor.execute(f'SELECT * FROM `{table}` ORDER BY 1')
            payload['tables'][table] = cursor.fetchall()
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    path = BACKUP_DIR / f'phase6b_cutover_{datetime.now():%Y%m%d_%H%M%S}.json'
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=json_default),
        encoding='utf-8',
    )
    return path


def validate_final_schema(connection):
    forbidden_tables = {'productos', 'producto_imagenes'}
    forbidden_columns = {
        ('carrito_items', 'producto_id'),
        ('inventario', 'producto_id'),
        ('movimientos_inventario', 'producto_id'),
        ('pedido_lineas', 'producto_id'),
        ('resenas', 'producto_id'),
    }
    with connection.cursor() as cursor:
        cursor.execute(
            'SELECT TABLE_NAME FROM information_schema.TABLES '
            'WHERE TABLE_SCHEMA = DATABASE()'
        )
        tables = {row['TABLE_NAME'] for row in cursor.fetchall()}
        cursor.execute(
            'SELECT TABLE_NAME, COLUMN_NAME FROM information_schema.COLUMNS '
            'WHERE TABLE_SCHEMA = DATABASE()'
        )
        columns = {
            (row['TABLE_NAME'], row['COLUMN_NAME']) for row in cursor.fetchall()
        }
        cursor.execute(
            "SELECT COUNT(*) n FROM information_schema.ROUTINES "
            "WHERE ROUTINE_SCHEMA = DATABASE() "
            "AND ROUTINE_NAME = 'sp_crear_pedido'"
        )
        old_procedure = cursor.fetchone()['n']
    leftovers = sorted(forbidden_tables & tables) + sorted(
        f'{table}.{column}'
        for table, column in forbidden_columns & columns
    )
    if old_procedure:
        leftovers.append('sp_crear_pedido')
    if leftovers:
        raise RuntimeError(f'Objetos heredados restantes: {leftovers}')


def legacy_products_exist(connection):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) n FROM information_schema.TABLES "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'productos'"
        )
        return bool(cursor.fetchone()['n'])


def main():
    connection = mysql_connection()
    try:
        if not legacy_products_exist(connection):
            validate_final_schema(connection)
            print('El corte físico 6B ya estaba aplicado; no se modificó la base.')
            return 0
        total_refs, total_images = validate_mongo(connection)
        print(
            f'MongoDB verificado: {total_refs} referencias y '
            f'{total_images} imágenes heredadas'
        )
        backup = create_backup(connection)
        print(f'Respaldo previo al corte: {backup}')
        statements = run_sql_file(connection, MIGRATION)
        validate_final_schema(connection)
        print(f'Corte físico 6B aplicado ({statements} sentencias).')
        return 0
    except Exception as exc:
        print(f'ERROR en corte físico 6B: {exc}', file=sys.stderr)
        return 1
    finally:
        connection.close()


if __name__ == '__main__':
    raise SystemExit(main())
