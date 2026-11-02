#!/usr/bin/env python3
"""Instala las tablas derivadas del Plan B de Cassandra (migración 27)."""

from pathlib import Path

from apply_unique_nombre_tiendaya import connect_mysql
from run_sql_migration import run_sql_file


ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    connection = connect_mysql()
    try:
        count = run_sql_file(connection, ROOT / 'database/mysql/27_respaldo_analitica.sql')
        connection.commit()
        print(f'Respaldo analítico MySQL instalado ({count} sentencias).')
        return 0
    finally:
        connection.close()


if __name__ == '__main__':
    raise SystemExit(main())
