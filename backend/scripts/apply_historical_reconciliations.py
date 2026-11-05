#!/usr/bin/env python3
"""Instala la bitácora de conciliaciones históricas (migración 28)."""

from pathlib import Path

from apply_unique_nombre_tiendaya import connect_mysql
from run_sql_migration import run_sql_file


ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    connection = connect_mysql()
    try:
        count = run_sql_file(
            connection, ROOT / 'database/mysql/28_historical_reconciliations.sql'
        )
        connection.commit()
        with connection.cursor() as cursor:
            cursor.execute('SELECT DATABASE() AS db')
            database = cursor.fetchone()['db']
        print(f'Bitácora de conciliaciones instalada en {database} ({count} sentencia).')
        return 0
    finally:
        connection.close()


if __name__ == '__main__':
    raise SystemExit(main())
