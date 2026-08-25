#!/usr/bin/env python3
"""Instala de forma idempotente imágenes SQL y categorías múltiples."""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

import pymysql
from dotenv import load_dotenv

from run_sql_migration import run_sql_file


BACKEND_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BACKEND_DIR.parent
MIGRATION = ROOT_DIR / 'database' / 'mysql' / '12_catalog_images_categories.sql'
BACKUP_DIR = ROOT_DIR / 'backups'
load_dotenv(BACKEND_DIR / '.env')


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


def main() -> int:
    connection = connect_mysql()
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT TABLE_NAME FROM information_schema.TABLES
                WHERE TABLE_SCHEMA = DATABASE()
            """)
            tables = {row['TABLE_NAME'] for row in cursor.fetchall()}
            if 'productos' in tables:
                raise RuntimeError(
                    'Primero debe completarse el corte del catálogo heredado.'
                )
            required = {'categorias', 'producto_referencias'}
            missing = sorted(required - tables)
            if missing:
                raise RuntimeError(f'Faltan tablas base: {", ".join(missing)}')

            cursor.execute("""
                SELECT COUNT(*) AS n FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'categorias'
                  AND COLUMN_NAME = 'sku_prefix'
            """)
            if not cursor.fetchone()['n']:
                cursor.execute(
                    'ALTER TABLE categorias '
                    'ADD COLUMN sku_prefix VARCHAR(3) NULL AFTER slug'
                )
            cursor.execute("""
                SELECT COUNT(*) AS n FROM information_schema.STATISTICS
                WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'categorias'
                  AND INDEX_NAME = 'uq_categorias_sku_prefix'
            """)
            if not cursor.fetchone()['n']:
                cursor.execute(
                    'ALTER TABLE categorias ADD UNIQUE INDEX '
                    'uq_categorias_sku_prefix (sku_prefix)'
                )

            cursor.execute(
                'SELECT id, categoria_id FROM producto_referencias ORDER BY id'
            )
            snapshot = cursor.fetchall()
            BACKUP_DIR.mkdir(parents=True, exist_ok=True)
            backup = BACKUP_DIR / (
                f'catalog_extensions_{datetime.now():%Y%m%d_%H%M%S}.json'
            )
            backup.write_text(json.dumps({
                'created_at': datetime.now().astimezone().isoformat(),
                'producto_referencias': snapshot,
            }, ensure_ascii=False, indent=2), encoding='utf-8')

        statements = run_sql_file(connection, MIGRATION)
        with connection.cursor() as cursor:
            # Compatibilidad con una ejecución interrumpida de una versión
            # previa que intentaba usar una columna generada. MySQL no permite
            # CASCADE cuando la columna base participa en esa expresión.
            cursor.execute("""
                SELECT COUNT(*) AS n FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'producto_referencia_categorias'
                  AND COLUMN_NAME = 'principal_referencia_id'
            """)
            if cursor.fetchone()['n']:
                cursor.execute(
                    'ALTER TABLE producto_referencia_categorias '
                    'DROP INDEX uq_prc_principal'
                )
                cursor.execute(
                    'ALTER TABLE producto_referencia_categorias '
                    'DROP COLUMN principal_referencia_id'
                )

            cursor.execute("""
                SELECT CONSTRAINT_NAME FROM information_schema.REFERENTIAL_CONSTRAINTS
                WHERE CONSTRAINT_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'producto_referencia_categorias'
            """)
            constraints = {row['CONSTRAINT_NAME'] for row in cursor.fetchall()}
            if 'fk_prc_referencia' not in constraints:
                cursor.execute("""
                    ALTER TABLE producto_referencia_categorias
                    ADD CONSTRAINT fk_prc_referencia
                    FOREIGN KEY (producto_referencia_id)
                    REFERENCES producto_referencias(id) ON DELETE CASCADE
                """)
            if 'fk_prc_categoria' not in constraints:
                cursor.execute("""
                    ALTER TABLE producto_referencia_categorias
                    ADD CONSTRAINT fk_prc_categoria
                    FOREIGN KEY (categoria_id)
                    REFERENCES categorias(id) ON DELETE RESTRICT
                """)

            cursor.execute('SELECT COUNT(*) AS n FROM producto_imagenes')
            images = cursor.fetchone()['n']
            cursor.execute(
                'SELECT COUNT(*) AS n FROM producto_referencia_categorias'
            )
            categories = cursor.fetchone()['n']
        print(f'Respaldo creado: {backup}')
        print(
            f'Extensión de catálogo aplicada ({statements} sentencias): '
            f'{images} imágenes, {categories} relaciones de categoría.'
        )
        return 0
    except Exception as exc:
        print(f'ERROR en extensión de catálogo: {exc}', file=sys.stderr)
        return 1
    finally:
        connection.close()


if __name__ == '__main__':
    raise SystemExit(main())
