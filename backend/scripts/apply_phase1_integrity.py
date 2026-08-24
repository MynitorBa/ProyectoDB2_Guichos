#!/usr/bin/env python3
"""Aplica de forma idempotente la Fase 1 a una base MySQL existente."""

import os
import sys

import pymysql
from dotenv import load_dotenv


load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

MYSQL_HOST = os.getenv('MYSQL_HOST', 'localhost')
MYSQL_PORT = int(os.getenv('MYSQL_PORT', 3306))
MYSQL_DB = os.getenv('MYSQL_DB', 'tiendaya')
MYSQL_USER = os.getenv('MYSQL_USER', 'tiendaya')
MYSQL_PASS = os.getenv('MYSQL_PASSWORD', 'tiendaya123')


ORPHAN_QUERIES = {
    'movimientos_inventario.pedido_id': """
        SELECT COUNT(*) AS n
        FROM movimientos_inventario mi
        LEFT JOIN pedidos p ON p.id = mi.pedido_id
        WHERE mi.pedido_id IS NOT NULL AND p.id IS NULL
    """,
    'movimientos_inventario.usuario_id': """
        SELECT COUNT(*) AS n
        FROM movimientos_inventario mi
        LEFT JOIN usuarios u ON u.id = mi.usuario_id
        WHERE mi.usuario_id IS NOT NULL AND u.id IS NULL
    """,
    'notificaciones.usuario_id': """
        SELECT COUNT(*) AS n
        FROM notificaciones n
        LEFT JOIN usuarios u ON u.id = n.usuario_id
        WHERE u.id IS NULL
    """,
    'notificaciones.pedido_id': """
        SELECT COUNT(*) AS n
        FROM notificaciones n
        LEFT JOIN pedidos p ON p.id = n.pedido_id
        WHERE n.pedido_id IS NOT NULL AND p.id IS NULL
    """,
}


FK_DEFINITIONS = {
    'fk_mi_pedido': """
        ALTER TABLE movimientos_inventario
        ADD CONSTRAINT fk_mi_pedido
        FOREIGN KEY (pedido_id) REFERENCES pedidos(id) ON DELETE SET NULL
    """,
    'fk_mi_usuario': """
        ALTER TABLE movimientos_inventario
        ADD CONSTRAINT fk_mi_usuario
        FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE SET NULL
    """,
    'fk_notif_usuario': """
        ALTER TABLE notificaciones
        ADD CONSTRAINT fk_notif_usuario
        FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
    """,
    'fk_notif_pedido': """
        ALTER TABLE notificaciones
        ADD CONSTRAINT fk_notif_pedido
        FOREIGN KEY (pedido_id) REFERENCES pedidos(id) ON DELETE SET NULL
    """,
}


def main() -> int:
    connection = pymysql.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        db=MYSQL_DB,
        user=MYSQL_USER,
        password=MYSQL_PASS,
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )

    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS notificaciones (
                  id             INT UNSIGNED NOT NULL AUTO_INCREMENT,
                  usuario_id     INT UNSIGNED NOT NULL,
                  tipo           VARCHAR(50)  NOT NULL,
                  titulo         VARCHAR(200) NOT NULL,
                  mensaje        TEXT         NOT NULL,
                  leida          TINYINT(1)   NOT NULL DEFAULT 0,
                  pedido_id      INT UNSIGNED NULL,
                  fecha_creacion DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  PRIMARY KEY (id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                  COLLATE=utf8mb4_unicode_ci
            """)

            print('Validando referencias antes de crear FKs...')
            for label, query in ORPHAN_QUERIES.items():
                cursor.execute(query)
                count = cursor.fetchone()['n']
                print(f'  {label}: {count} huérfanas')
                if count:
                    raise RuntimeError(
                        f'Migración abortada: {count} referencias huérfanas en {label}'
                    )

            cursor.execute("""
                ALTER TABLE notificaciones
                  MODIFY id INT UNSIGNED NOT NULL AUTO_INCREMENT,
                  MODIFY usuario_id INT UNSIGNED NOT NULL,
                  MODIFY pedido_id INT UNSIGNED NULL
            """)

            cursor.execute("""
                SELECT CONSTRAINT_NAME
                FROM information_schema.REFERENTIAL_CONSTRAINTS
                WHERE CONSTRAINT_SCHEMA = %s
            """, (MYSQL_DB,))
            installed = {row['CONSTRAINT_NAME'] for row in cursor.fetchall()}

            for name, ddl in FK_DEFINITIONS.items():
                if name in installed:
                    print(f'  {name}: ya instalada')
                    continue
                cursor.execute(ddl)
                print(f'  {name}: creada')

            cursor.execute("""
                SELECT COUNT(*) AS n
                FROM information_schema.STATISTICS
                WHERE TABLE_SCHEMA = %s
                  AND TABLE_NAME = 'notificaciones'
                  AND INDEX_NAME = 'idx_notif_usuario_leida_fecha'
            """, (MYSQL_DB,))
            if cursor.fetchone()['n'] == 0:
                cursor.execute("""
                    ALTER TABLE notificaciones
                    ADD INDEX idx_notif_usuario_leida_fecha
                      (usuario_id, leida, fecha_creacion)
                """)
                print('  idx_notif_usuario_leida_fecha: creado')
            else:
                print('  idx_notif_usuario_leida_fecha: ya existe')

        print('Fase 1 aplicada correctamente.')
        return 0
    except Exception as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 1
    finally:
        connection.close()


if __name__ == '__main__':
    raise SystemExit(main())
