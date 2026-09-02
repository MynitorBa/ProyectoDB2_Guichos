#!/usr/bin/env python3
"""Instala de forma idempotente unicidad de nombre en categorías y columna es_tiendaya."""

import os
import sys
from pathlib import Path

import pymysql
from dotenv import load_dotenv

from run_sql_migration import run_sql_file

BACKEND_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BACKEND_DIR.parent
MIGRATION = ROOT_DIR / 'database' / 'mysql' / '16_unique_nombre_tiendaya.sql'
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
        statements = run_sql_file(connection, MIGRATION)
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT COUNT(*) AS n FROM information_schema.STATISTICS
                WHERE table_schema = DATABASE()
                  AND table_name = 'categorias'
                  AND index_name = 'uq_categorias_nombre'
            """)
            idx_ok = cursor.fetchone()['n'] > 0
            cursor.execute("""
                SELECT COUNT(*) AS n FROM information_schema.COLUMNS
                WHERE table_schema = DATABASE()
                  AND table_name = 'vendedores'
                  AND column_name = 'es_tiendaya'
            """)
            col_ok = cursor.fetchone()['n'] > 0
            cursor.execute("""
                SELECT COUNT(*) AS n FROM vendedores WHERE es_tiendaya = 1
            """)
            flag_ok = cursor.fetchone()['n'] > 0
        print(
            f'Migración 16 aplicada ({statements} sentencias). '
            f'idx_nombre={"ok" if idx_ok else "falta"}, '
            f'col_es_tiendaya={"ok" if col_ok else "falta"}, '
            f'vendedor_tiendaya_marcado={"ok" if flag_ok else "ninguno (normal en setup sin seed TiendaYa)"}.'
        )
        return 0
    except Exception as exc:
        print(f'ERROR en migración 16: {exc}', file=sys.stderr)
        return 1
    finally:
        connection.close()


if __name__ == '__main__':
    raise SystemExit(main())
