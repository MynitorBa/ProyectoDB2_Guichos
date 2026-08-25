#!/usr/bin/env python3
"""Detecta si MySQL conserva el esquema heredado o ya completó el corte."""

import os
import sys
from pathlib import Path

import pymysql
from dotenv import load_dotenv


BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / '.env')


def main() -> int:
    connection = pymysql.connect(
        host=os.getenv('MYSQL_HOST', 'localhost'),
        port=int(os.getenv('MYSQL_PORT', 3306)),
        db=os.getenv('MYSQL_DB', 'tiendaya'),
        user=os.getenv('MYSQL_USER', 'tiendaya'),
        password=os.getenv('MYSQL_PASSWORD', 'tiendaya123'),
        charset='utf8mb4',
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT TABLE_NAME
                FROM information_schema.TABLES
                WHERE TABLE_SCHEMA = DATABASE()
            """)
            tables = {row[0] for row in cursor.fetchall()}
        if 'productos' in tables:
            print('legacy')
            return 0
        required = {
            'producto_referencias', 'ofertas', 'inventario',
            'pedido_vendedores', 'pedido_direcciones', 'outbox_eventos',
        }
        missing = sorted(required - tables)
        if not missing:
            print('final')
            return 0
        print(
            'Esquema incompleto; faltan tablas: ' + ', '.join(missing),
            file=sys.stderr,
        )
        return 1
    except Exception as exc:
        print(f'No se pudo detectar el estado del esquema: {exc}', file=sys.stderr)
        return 1
    finally:
        connection.close()


if __name__ == '__main__':
    raise SystemExit(main())
