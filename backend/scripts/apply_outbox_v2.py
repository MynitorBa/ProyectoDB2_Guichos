"""Instala de forma idempotente el outbox por destino (migración 19)."""

from pathlib import Path

from apply_unique_nombre_tiendaya import connect_mysql
from run_sql_migration import run_sql_file

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    connection = connect_mysql()
    try:
        run_sql_file(connection, ROOT / 'database/mysql/19_outbox_v2.sql')
        connection.commit()
        print('Outbox v2: destinos, secuencia y reintentos escalonados listos.')
        return 0
    finally:
        connection.close()


if __name__ == '__main__':
    raise SystemExit(main())
