#!/usr/bin/env python3
"""Instala el expediente durable de alertas explicables."""

from pathlib import Path

from apply_unique_nombre_tiendaya import connect_mysql
from run_sql_migration import run_sql_file


ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    connection = connect_mysql()
    try:
        count = run_sql_file(connection, ROOT / 'database/mysql/22_fraud_alerts.sql')
        connection.commit()
        print(f'Alertas de fraude instaladas ({count} sentencias).')
        return 0
    finally:
        connection.close()


if __name__ == '__main__':
    raise SystemExit(main())
