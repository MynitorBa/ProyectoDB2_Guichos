#!/usr/bin/env python3
"""Aplica la columna y el backfill de carrito necesarios para Fase 4."""

import os
import sys
from pathlib import Path

import pymysql
from dotenv import load_dotenv

from run_sql_migration import run_sql_file


BACKEND_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BACKEND_DIR.parent
MIGRATION = ROOT_DIR / 'database' / 'mysql' / '08_phase4_dual_read.sql'
load_dotenv(BACKEND_DIR / '.env')


def main():
    connection = pymysql.connect(
        host=os.getenv('MYSQL_HOST', 'localhost'),
        port=int(os.getenv('MYSQL_PORT', 3306)),
        db=os.getenv('MYSQL_DB', 'tiendaya'),
        user=os.getenv('MYSQL_USER', 'tiendaya'),
        password=os.getenv('MYSQL_PASSWORD', 'tiendaya123'),
        charset='utf8mb4',
        autocommit=True,
    )
    try:
        total = run_sql_file(connection, MIGRATION)
        print(f'Fase 4 aplicada correctamente ({total} sentencias).')
        return 0
    except Exception as exc:
        print(f'ERROR al aplicar Fase 4: {exc}', file=sys.stderr)
        return 1
    finally:
        connection.close()


if __name__ == '__main__':
    raise SystemExit(main())
