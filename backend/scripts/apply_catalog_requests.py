#!/usr/bin/env python3
"""Instala de forma idempotente el flujo de solicitudes del catálogo."""

import os
import sys
from pathlib import Path

import pymysql
from dotenv import load_dotenv

from run_sql_migration import run_sql_file


BACKEND_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BACKEND_DIR.parent
MIGRATION = ROOT_DIR / 'database' / 'mysql' / '13_catalog_requests.sql'
load_dotenv(BACKEND_DIR / '.env')


def connect_mysql():
    return pymysql.connect(
        host=os.getenv('MYSQL_HOST', 'localhost'),
        port=int(os.getenv('MYSQL_PORT', 3306)),
        db=os.getenv('MYSQL_DB', 'tiendaya'),
        user=os.getenv('MYSQL_USER', 'tiendaya'),
        password=os.getenv('MYSQL_PASSWORD', 'tiendaya123'),
        charset='utf8mb4', autocommit=True,
        cursorclass=pymysql.cursors.DictCursor,
    )


def main() -> int:
    connection = connect_mysql()
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT COUNT(*) AS n FROM information_schema.TABLES
                WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'producto_imagenes'
            """)
            if not cursor.fetchone()['n']:
                raise RuntimeError('Primero debe instalarse la extensión de imágenes.')
            cursor.execute("""
                SELECT COUNT(*) AS n FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'producto_imagenes'
                  AND COLUMN_NAME = 'subida_por'
            """)
            if not cursor.fetchone()['n']:
                cursor.execute(
                    'ALTER TABLE producto_imagenes '
                    'ADD COLUMN subida_por INT UNSIGNED NULL AFTER producto_referencia_id'
                )
            cursor.execute("""
                SELECT COUNT(*) AS n FROM information_schema.STATISTICS
                WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'producto_imagenes'
                  AND INDEX_NAME = 'idx_pi_subida_por'
            """)
            if not cursor.fetchone()['n']:
                cursor.execute(
                    'ALTER TABLE producto_imagenes ADD INDEX idx_pi_subida_por (subida_por)'
                )
            cursor.execute("""
                SELECT COUNT(*) AS n FROM information_schema.REFERENTIAL_CONSTRAINTS
                WHERE CONSTRAINT_SCHEMA = DATABASE()
                  AND CONSTRAINT_NAME = 'fk_pi_subida_por'
            """)
            if not cursor.fetchone()['n']:
                cursor.execute(
                    'ALTER TABLE producto_imagenes ADD CONSTRAINT fk_pi_subida_por '
                    'FOREIGN KEY (subida_por) REFERENCES usuarios(id) ON DELETE SET NULL'
                )
        statements = run_sql_file(connection, MIGRATION)
        with connection.cursor() as cursor:
            cursor.execute('SELECT COUNT(*) AS n FROM solicitudes_catalogo')
            count = cursor.fetchone()['n']
        print(
            f'Solicitudes de catálogo instaladas ({statements} sentencias, '
            f'{count} solicitudes existentes).'
        )
        return 0
    except Exception as exc:
        print(f'ERROR instalando solicitudes de catálogo: {exc}', file=sys.stderr)
        return 1
    finally:
        connection.close()


if __name__ == '__main__':
    raise SystemExit(main())
