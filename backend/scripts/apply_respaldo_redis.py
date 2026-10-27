#!/usr/bin/env python3
"""Instala las tablas de respaldo del carrito y de las ventas flash (plan B de Redis)."""

from pathlib import Path

from apply_unique_nombre_tiendaya import connect_mysql
from run_sql_migration import run_sql_file


ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    connection = connect_mysql()
    try:
        count = run_sql_file(
            connection, ROOT / 'database/mysql/24_respaldo_redis.sql'
        )
        connection.commit()
        print(f'Respaldo de Redis en MySQL instalado ({count} sentencias).')
        return 0
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


if __name__ == '__main__':
    raise SystemExit(main())
