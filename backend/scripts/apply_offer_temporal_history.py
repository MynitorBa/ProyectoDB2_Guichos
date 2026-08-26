#!/usr/bin/env python3
"""Instala de forma idempotente el historial temporal de ofertas."""

import os
import sys
from pathlib import Path

import pymysql
from dotenv import load_dotenv

from run_sql_migration import run_sql_file


BACKEND_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BACKEND_DIR.parent
MIGRATION = ROOT_DIR / 'database' / 'mysql' / '14_offer_temporal_history.sql'
load_dotenv(BACKEND_DIR / '.env')


def main() -> int:
    connection = pymysql.connect(
        host=os.getenv('MYSQL_HOST', 'localhost'),
        port=int(os.getenv('MYSQL_PORT', 3306)),
        db=os.getenv('MYSQL_DB', 'tiendaya'),
        user=os.getenv('MYSQL_USER', 'tiendaya'),
        password=os.getenv('MYSQL_PASSWORD', 'tiendaya123'),
        charset='utf8mb4',
        autocommit=True,
        cursorclass=pymysql.cursors.DictCursor,
    )
    try:
        statements = run_sql_file(connection, MIGRATION)
        with connection.cursor() as cursor:
            cursor.execute('SELECT COUNT(*) n FROM oferta_estados_historial')
            states = cursor.fetchone()['n']
            cursor.execute('SELECT COUNT(*) n FROM inventario_saldos_historial')
            balances = cursor.fetchone()['n']
        print(
            f'Historial temporal instalado ({statements} sentencias): '
            f'{states} estados de oferta y {balances} saldos de inventario.'
        )
        return 0
    except Exception as exc:
        print(f'ERROR en historial temporal de ofertas: {exc}', file=sys.stderr)
        return 1
    finally:
        connection.close()


if __name__ == '__main__':
    raise SystemExit(main())
