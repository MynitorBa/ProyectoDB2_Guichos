"""Instala de forma idempotente el soporte del checkout como saga (migración 20)."""

from pathlib import Path

from apply_unique_nombre_tiendaya import connect_mysql
from run_sql_migration import run_sql_file

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    connection = connect_mysql()
    try:
        run_sql_file(connection, ROOT / 'database/mysql/20_checkout_saga.sql')
        print('Checkout saga: idempotencia, estados de pago y bitácora listos.')
        return 0
    finally:
        connection.close()


if __name__ == '__main__':
    raise SystemExit(main())
