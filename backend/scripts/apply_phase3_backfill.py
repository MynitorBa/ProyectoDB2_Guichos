#!/usr/bin/env python3
"""Respalda el estado afectado y aplica el backfill transaccional de Fase 3."""

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
MIGRATION = ROOT_DIR / 'database' / 'mysql' / '07_phase3_backfill.sql'
BACKUP_DIR = ROOT_DIR / 'backups'

load_dotenv(BACKEND_DIR / '.env')
load_dotenv(ROOT_DIR / '.env')


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

    client = MongoClient(
        os.getenv(
            'MONGO_URI',
            'mongodb://admin:adminpassword@localhost:27017/tiendaya?authSource=admin',
        ),
        serverSelectionTimeoutMS=5000,
    )
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
        'productos', 'inventario', 'pedidos', 'pedido_lineas', 'direcciones',
        'ofertas', 'oferta_precios_historial', 'pedido_vendedores',
        'pedido_direcciones',
    )
    payload = {
        'created_at': datetime.now().astimezone().isoformat(),
        'database': os.getenv('MYSQL_DB', 'tiendaya'),
        'tables': {},
    }
    with connection.cursor() as cursor:
        for table in tables:
            cursor.execute(f'SELECT * FROM `{table}` ORDER BY 1')
            payload['tables'][table] = cursor.fetchall()

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    path = BACKUP_DIR / f'phase3_pre_{datetime.now():%Y%m%d_%H%M%S}.json'
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=json_default),
        encoding='utf-8',
    )
    return path


def summary(connection):
    queries = {
        'productos': 'SELECT COUNT(*) AS n FROM productos',
        'ofertas': 'SELECT COUNT(*) AS n FROM ofertas',
        'precios_vigentes': (
            'SELECT COUNT(*) AS n FROM oferta_precios_historial '
            'WHERE vigente_hasta IS NULL'
        ),
        'inventarios_relacionados': (
            'SELECT COUNT(*) AS n FROM inventario WHERE oferta_id IS NOT NULL'
        ),
        'pedido_vendedores': 'SELECT COUNT(*) AS n FROM pedido_vendedores',
        'snapshots_direccion': 'SELECT COUNT(*) AS n FROM pedido_direcciones',
        'lineas_completas': (
            'SELECT COUNT(*) AS n FROM pedido_lineas '
            'WHERE oferta_id IS NOT NULL AND pedido_vendedor_id IS NOT NULL '
            'AND sku_snapshot IS NOT NULL '
            'AND vendedor_nombre_snapshot IS NOT NULL'
        ),
    }
    result = {}
    with connection.cursor() as cursor:
        for label, query in queries.items():
            cursor.execute(query)
            result[label] = cursor.fetchone()['n']
    return result


def main():
    connection = mysql_connection(autocommit=True)
    try:
        print('Validando referencias de productos contra MongoDB...')
        verify_mongo_references(connection)
        before = summary(connection)
        backup_path = create_backup(connection)
        print(f'Respaldo lógico creado: {backup_path}')
        total = run_sql_file(connection, MIGRATION)
        after = summary(connection)
        print(f'Fase 3 aplicada correctamente ({total} sentencias).')
        print(f'Antes:   {before}')
        print(f'Después: {after}')
        return 0
    except Exception as exc:
        print(f'ERROR al aplicar Fase 3: {exc}', file=sys.stderr)
        return 1
    finally:
        connection.close()


if __name__ == '__main__':
    raise SystemExit(main())
