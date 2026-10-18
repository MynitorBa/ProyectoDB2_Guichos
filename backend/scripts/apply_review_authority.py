#!/usr/bin/env python3
"""Instala y concilia MySQL como autoridad de reseñas sin perder el grafo actual."""

from __future__ import annotations

import json
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from apply_unique_nombre_tiendaya import connect_mysql
from run_sql_migration import run_sql_file

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / 'database/mysql/21_review_authority.sql'
BACKUP_DIR = ROOT / 'backups/reviews'
sys.path.insert(0, str(ROOT / 'backend'))


def _json(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(type(value).__name__)


def _neo4j_snapshot() -> list[dict]:
    from app.core.db_neo4j import get_driver

    with get_driver().session() as session:
        return session.run("""
            MATCH (u:Usuario)-[:ESCRIBIO]->(r:Reseña)-[:SOBRE]->(p:Producto)
            OPTIONAL MATCH (r)-[:CALIFICA_A|PARA_VENDEDOR]->(v:Vendedor)
            OPTIONAL MATCH (resp:Respuesta)-[:A_RESENA]->(r)
            OPTIONAL MATCH (autor:Usuario)-[:RESPONDIO]->(resp)
            RETURN r.id AS public_id, r.mysql_id AS mysql_id,
                   r.estado AS estado, r.verificada AS verificada,
                   r.fecha AS fecha,
                   coalesce(r.imagenes, []) AS imagenes,
                   u.id AS usuario_id, p.ref AS producto_ref,
                   v.id AS vendedor_id,
                   collect(CASE WHEN resp IS NULL THEN null ELSE {
                       public_id: resp.id, texto: resp.texto, fecha: resp.fecha,
                       autor_nombre: resp.autor_nombre, usuario_id: autor.id
                   } END) AS respuestas
            ORDER BY r.id
        """).data()


def _tables(cursor) -> set[str]:
    cursor.execute("""
        SELECT TABLE_NAME FROM information_schema.TABLES
        WHERE TABLE_SCHEMA = DATABASE()
    """)
    return {row['TABLE_NAME'] for row in cursor.fetchall()}


def _already_migrated(connection) -> bool:
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT COUNT(*) AS n FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='resenas'
              AND COLUMN_NAME='public_id'
        """)
        has_public_id = cursor.fetchone()['n'] == 1
        tables = _tables(cursor)
    return has_public_id and {'resena_imagenes', 'resena_respuestas'} <= tables


def _backup(connection, neo_rows: list[dict]) -> Path:
    with connection.cursor() as cursor:
        cursor.execute('SELECT * FROM resenas ORDER BY id')
        payload = {'resenas': cursor.fetchall(), 'neo4j': neo_rows}
        tables = _tables(cursor)
        for table in ('resena_imagenes', 'resena_respuestas'):
            if table in tables:
                cursor.execute(f'SELECT * FROM {table} ORDER BY id')
                payload[table] = cursor.fetchall()
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    path = BACKUP_DIR / f'reviews_{datetime.now():%Y%m%d_%H%M%S}.json'
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=_json), encoding='utf-8')
    return path


def _compatible_line(cursor, row: dict) -> int | None:
    vendedor_id = row.get('vendedor_id')
    if vendedor_id is None:
        return None
    cursor.execute("""
        SELECT pl.id
        FROM pedido_lineas pl
        JOIN pedidos p ON p.id = pl.pedido_id
        JOIN pedido_vendedores pv ON pv.id = pl.pedido_vendedor_id
        WHERE p.usuario_id = %s
          AND pl.producto_ref = %s
          AND pv.vendedor_id = %s
          AND (%s IS NULL OR p.fecha_creacion <= %s)
          AND p.estado NOT IN ('cancelado', 'reembolsado')
          AND EXISTS (
              SELECT 1 FROM pagos pa
              WHERE pa.pedido_id = p.id AND pa.estado = 'aprobado'
          )
        ORDER BY p.fecha_creacion DESC, pl.id DESC
        LIMIT 1
    """, (
        row['usuario_id'], row['producto_ref'], vendedor_id,
        row.get('fecha'), row.get('fecha'),
    ))
    found = cursor.fetchone()
    return found['id'] if found else None


def _reconcile(connection, neo_rows: list[dict]) -> tuple[int, int, int]:
    reviews = images = replies = 0
    with connection.cursor() as cursor:
        for row in neo_rows:
            mysql_id = row.get('mysql_id')
            if mysql_id is None and str(row.get('public_id', '')).startswith('mysql:'):
                mysql_id = int(str(row['public_id']).split(':', 1)[1])
            if mysql_id is None:
                continue
            cursor.execute('SELECT id FROM resenas WHERE id = %s', (mysql_id,))
            if not cursor.fetchone():
                continue
            line_id = _compatible_line(cursor, row)
            verified = bool(line_id)
            state = row.get('estado') if row.get('estado') in {'pendiente', 'aprobada', 'rechazada'} else 'pendiente'
            cursor.execute("""
                UPDATE resenas
                SET public_id=%s, vendedor_id=%s, pedido_linea_id=%s,
                    verificada_compra=%s, motivo_no_verificada=%s,
                    estado_moderacion=%s, aprobada=%s
                WHERE id=%s
            """, (
                row['public_id'], row.get('vendedor_id'),
                line_id, 1 if verified else 0,
                None if verified else 'sin_compra_pagada_atribuible',
                state if verified else 'pendiente',
                1 if verified and state == 'aprobada' else 0, mysql_id,
            ))
            reviews += 1
            for order, url in enumerate(row.get('imagenes') or []):
                cursor.execute("""
                    INSERT INTO resena_imagenes (resena_id, url, orden)
                    VALUES (%s, %s, %s)
                    ON DUPLICATE KEY UPDATE orden=VALUES(orden)
                """, (mysql_id, url, order))
                images += 1
            for reply in row.get('respuestas') or []:
                if not reply or row.get('vendedor_id') is None:
                    continue
                cursor.execute('SELECT usuario_id FROM vendedores WHERE id=%s', (row['vendedor_id'],))
                owner = cursor.fetchone()
                if not owner:
                    continue
                cursor.execute("""
                    INSERT INTO resena_respuestas
                      (public_id, resena_id, usuario_id, vendedor_id, texto, fecha_creacion)
                    VALUES (%s,%s,%s,%s,%s,%s)
                    ON DUPLICATE KEY UPDATE texto=VALUES(texto)
                """, (
                    reply['public_id'], mysql_id,
                    reply.get('usuario_id') or owner['usuario_id'], row['vendedor_id'],
                    reply.get('texto') or '', reply.get('fecha') or datetime.now(),
                ))
                replies += 1
    return reviews, images, replies


def main() -> int:
    connection = connect_mysql()
    try:
        already_migrated = _already_migrated(connection)
        try:
            neo_rows = _neo4j_snapshot()
        except Exception:
            if not already_migrated:
                # En el primer corte Neo4j puede contener UUID, imágenes y
                # respuestas que aún no existen en MySQL: continuar los
                # perdería, por lo que se falla de manera segura.
                raise
            # Después del corte MySQL ya es la autoridad y setup debe poder
            # repetirse aunque la proyección Neo4j esté temporalmente caída.
            neo_rows = []
            print('Aviso: Neo4j no disponible; se respalda y valida solo MySQL.')
        backup = _backup(connection, neo_rows)
        statements = run_sql_file(connection, MIGRATION)
        reviews, images, replies = (
            (0, 0, 0) if already_migrated else _reconcile(connection, neo_rows)
        )
        connection.commit()
        print(f'Respaldo de reseñas: {backup}')
        print(
            f'Migración 21 aplicada ({statements} sentencias): '
            f'{reviews} reseñas conciliadas, {images} imágenes, {replies} respuestas.'
        )
        if already_migrated:
            print('MySQL ya era autoridad; Neo4j no se usó para sobrescribir datos.')
        return 0
    except Exception as exc:
        print(f'ERROR en migración 21: {exc}', file=sys.stderr)
        return 1
    finally:
        connection.close()


if __name__ == '__main__':
    raise SystemExit(main())
