#!/usr/bin/env python3
"""Relaciona categorías, referencias mínimas y ofertas con FKs MySQL."""

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
MIGRATION = ROOT_DIR / 'database' / 'mysql' / '11_phase7_reference_integrity.sql'
BACKUP_DIR = ROOT_DIR / 'backups'
load_dotenv(BACKEND_DIR / '.env')


def json_default(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(f'Tipo no serializable: {type(value).__name__}')


def connect_mysql():
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


def create_backup(connection):
    payload = {
        'created_at': datetime.now().astimezone().isoformat(),
        'phase': '7-reference-integrity',
        'tables': {},
    }
    with connection.cursor() as cursor:
        for table in ('categorias', 'producto_referencias', 'ofertas'):
            cursor.execute(f'SELECT * FROM `{table}` ORDER BY 1')
            payload['tables'][table] = cursor.fetchall()
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    path = BACKUP_DIR / f'phase7_refs_{datetime.now():%Y%m%d_%H%M%S}.json'
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=json_default),
        encoding='utf-8',
    )
    return path


def resolve_categories(connection):
    with connection.cursor() as cursor:
        cursor.execute('SELECT id, slug FROM categorias')
        category_ids = {row['slug']: row['id'] for row in cursor.fetchall()}
        cursor.execute(
            'SELECT id, producto_ref FROM producto_referencias ORDER BY id'
        )
        refs = cursor.fetchall()

    client = MongoClient(os.getenv('MONGO_URI'), serverSelectionTimeoutMS=5000)
    try:
        products = client[os.getenv('MONGO_DB', 'tiendaya')].productos
        assignments = []
        errors = []
        for row in refs:
            try:
                doc = products.find_one(
                    {'_id': ObjectId(row['producto_ref'])},
                    {'categoria.slug': 1},
                )
            except Exception:
                doc = None
            slug = (doc or {}).get('categoria', {}).get('slug')
            if not doc:
                errors.append(f"referencia {row['id']}: documento inexistente")
            elif not slug:
                errors.append(f"referencia {row['id']}: categoría sin slug")
            elif slug not in category_ids:
                errors.append(
                    f"referencia {row['id']}: slug '{slug}' no existe en MySQL"
                )
            else:
                assignments.append((category_ids[slug], row['id']))
        if errors:
            raise RuntimeError('; '.join(errors[:10]))
        return assignments
    finally:
        client.close()


def ensure_column_and_backfill(connection, assignments):
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT COUNT(*) n FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'producto_referencias'
              AND COLUMN_NAME = 'categoria_id'
        """)
        if not cursor.fetchone()['n']:
            cursor.execute(
                'ALTER TABLE producto_referencias '
                'ADD COLUMN categoria_id INT UNSIGNED NULL AFTER producto_ref'
            )
        cursor.executemany(
            'UPDATE producto_referencias SET categoria_id = %s WHERE id = %s',
            assignments,
        )


def summary(connection):
    with connection.cursor() as cursor:
        cursor.execute('SELECT COUNT(*) n FROM producto_referencias')
        refs = cursor.fetchone()['n']
        cursor.execute(
            'SELECT COUNT(*) n FROM producto_referencias '
            'WHERE categoria_id IS NOT NULL'
        )
        categorized = cursor.fetchone()['n']
        cursor.execute('SELECT COUNT(*) n FROM ofertas')
        offers = cursor.fetchone()['n']
    return {'referencias': refs, 'categorizadas': categorized, 'ofertas': offers}


def main():
    connection = connect_mysql()
    try:
        assignments = resolve_categories(connection)
        backup = create_backup(connection)
        print(f'Respaldo creado: {backup}')
        ensure_column_and_backfill(connection, assignments)
        statements = run_sql_file(connection, MIGRATION)
        print(f'Integridad de referencias aplicada ({statements} sentencias).')
        print(f'Resultado: {summary(connection)}')
        return 0
    except Exception as exc:
        print(f'ERROR en Fase 7 de referencias: {exc}', file=sys.stderr)
        return 1
    finally:
        connection.close()


if __name__ == '__main__':
    raise SystemExit(main())
