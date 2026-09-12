"""Instala de forma idempotente las tablas relacionales de ventas flash."""

from pathlib import Path

from apply_unique_nombre_tiendaya import connect_mysql
from run_sql_migration import run_sql_file

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    connection = connect_mysql()
    try:
        run_sql_file(connection, ROOT / 'database/mysql/18_flash_sales.sql')
        print('Ventas flash: tablas, restricciones e índices listos.')
        return 0
    finally:
        connection.close()


if __name__ == '__main__':
    raise SystemExit(main())
