#!/usr/bin/env python3
"""Respalda y aplica la parte aditiva/reversible de la Fase 6B."""

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
MIGRATION = ROOT_DIR / 'database' / 'mysql' / '09_phase6b_additive.sql'
BACKUP_DIR = ROOT_DIR / 'backups'
load_dotenv(BACKEND_DIR / '.env')


def json_default(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(f'Tipo no serializable: {type(value).__name__}')


def mysql_connection(*, autocommit=False):
    return pymysql.connect(
        host=os.getenv('MYSQL_HOST', 'localhost'),
        port=int(os.getenv('MYSQL_PORT', 3306)),
        db=os.getenv('MYSQL_DB', 'tiendaya'),
        user=os.getenv('MYSQL_USER', 'tiendaya'),
        password=os.getenv('MYSQL_PASSWORD', 'tiendaya123'),
        charset='utf8mb4',
        autocommit=autocommit,
        cursorclass=pymysql.cursors.DictCursor,
    )


def verify_mongo_references(connection):
    with connection.cursor() as cursor:
        cursor.execute('SELECT id, producto_ref FROM productos ORDER BY id')
        products = cursor.fetchall()
    client = MongoClient(os.getenv('MONGO_URI'), serverSelectionTimeoutMS=5000)
    try:
        collection = client[os.getenv('MONGO_DB', 'tiendaya')].productos
        invalid = []
        for product in products:
            try:
                exists = collection.count_documents(
                    {'_id': ObjectId(product['producto_ref'])}, limit=1
                )
            except Exception:
                exists = 0
            if not exists:
                invalid.append(product['id'])
        if invalid:
            raise RuntimeError(
                f'Productos sin documento MongoDB correspondiente: {invalid}'
            )
    finally:
        client.close()


def create_backup(connection):
    tables = (
        'productos', 'producto_imagenes', 'resenas', 'inventario',
        'movimientos_inventario', 'carrito_items', 'pedido_lineas', 'ofertas',
    )
    payload = {
        'created_at': datetime.now().astimezone().isoformat(),
        'database': os.getenv('MYSQL_DB', 'tiendaya'),
        'phase': '6B-additive',
        'tables': {},
    }
    with connection.cursor() as cursor:
        for table in tables:
            cursor.execute(f'SELECT * FROM `{table}` ORDER BY 1')
            payload['tables'][table] = cursor.fetchall()
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    path = BACKUP_DIR / f'phase6b_pre_{datetime.now():%Y%m%d_%H%M%S}.json'
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=json_default),
        encoding='utf-8',
    )
    return path


def summary(connection):
    queries = {
        'producto_referencias': 'SELECT COUNT(*) n FROM producto_referencias',
        'resenas_nueva_fk': (
            'SELECT COUNT(*) n FROM resenas '
            'WHERE producto_referencia_id IS NOT NULL'
        ),
        'movimientos_con_inventario': (
            'SELECT COUNT(*) n FROM movimientos_inventario '
            'WHERE inventario_id IS NOT NULL'
        ),
    }
    result = {}
    with connection.cursor() as cursor:
        for key, query in queries.items():
            cursor.execute(query)
            result[key] = cursor.fetchone()['n']
    return result


def main():
    connection = mysql_connection(autocommit=True)
    try:
        print('Validando las 65 referencias contra MongoDB...')
        verify_mongo_references(connection)
        backup_path = create_backup(connection)
        print(f'Respaldo lógico creado: {backup_path}')
        total = run_sql_file(connection, MIGRATION)
        print(f'Fase 6B aditiva aplicada ({total} sentencias).')
        print(f'Resultado: {summary(connection)}')
        return 0
    except Exception as exc:
        print(f'ERROR al aplicar Fase 6B aditiva: {exc}', file=sys.stderr)
        return 1
    finally:
        connection.close()


if __name__ == '__main__':
    raise SystemExit(main())
