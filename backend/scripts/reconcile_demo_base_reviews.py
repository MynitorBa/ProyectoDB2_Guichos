#!/usr/bin/env python3
"""Reconcilia exclusivamente las reseñas académicas del seed base DEMO.

El modo predeterminado es una auditoría de solo lectura. ``--apply`` requiere
además ``--confirm-demo`` y solo puede conectarse a destinos validados por
``load_demo_env``. Cada reseña se decide por evidencia concreta de una línea
de pedido pagada; los conteos finales son únicamente una guarda de seguridad.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

import pymysql

from seed_demo_large import BACKEND_DIR, load_demo_env


EXPECTED_VERIFIED = 17
EXPECTED_HISTORICAL = 25


def eligible_lines(cursor, review: dict) -> list[dict]:
    cursor.execute(
        """
        SELECT pl.id AS pedido_linea_id, pl.pedido_id, pv.vendedor_id,
               p.estado AS pedido_estado, pa.estado AS pago_estado,
               p.fecha_creacion AS pedido_fecha
        FROM pedido_lineas pl
        JOIN pedidos p ON p.id = pl.pedido_id
        JOIN pedido_vendedores pv ON pv.id = pl.pedido_vendedor_id
        JOIN pagos pa ON pa.pedido_id = p.id AND pa.estado = 'aprobado'
        WHERE p.usuario_id = %s
          AND pl.producto_ref = %s
          AND p.fecha_creacion <= %s
          AND p.estado NOT IN ('cancelado', 'reembolsado')
        ORDER BY p.fecha_creacion DESC, pl.id DESC
        """,
        (review['usuario_id'], review['producto_ref'], review['fecha']),
    )
    return list(cursor.fetchall())


def audit(connection) -> tuple[list[tuple[dict, dict]], list[dict]]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT r.id, r.public_id, r.usuario_id, r.fecha,
                   r.estado_moderacion, r.verificada_compra,
                   pr.producto_ref
            FROM resenas r
            JOIN producto_referencias pr ON pr.id = r.producto_referencia_id
            WHERE r.public_id NOT LIKE 'demo:%%'
            ORDER BY r.id
            """
        )
        reviews = list(cursor.fetchall())

        verified: list[tuple[dict, dict]] = []
        historical: list[dict] = []
        for review in reviews:
            candidates = eligible_lines(cursor, review)
            if candidates:
                evidence = candidates[0]
                verified.append((review, evidence))
                print(
                    f"[ELEGIBLE] {review['public_id']} usuario={review['usuario_id']} "
                    f"producto={review['producto_ref']} vendedor={evidence['vendedor_id']} "
                    f"linea={evidence['pedido_linea_id']} pedido={evidence['pedido_id']} "
                    f"estado={evidence['pedido_estado']} pago={evidence['pago_estado']} "
                    f"coincidencias={len(candidates)}"
                )
            else:
                historical.append(review)
                print(
                    f"[HISTORICA] {review['public_id']} usuario={review['usuario_id']} "
                    f"producto={review['producto_ref']} sin compra pagada atribuible"
                )
    return verified, historical


def apply(connection, verified: list[tuple[dict, dict]], historical: list[dict]) -> None:
    if len(verified) != EXPECTED_VERIFIED or len(historical) != EXPECTED_HISTORICAL:
        raise SystemExit(
            'Se abortó la aplicación: la auditoría individual no produjo '
            f'{EXPECTED_VERIFIED} elegibles y {EXPECTED_HISTORICAL} históricas.'
        )
    with connection.cursor() as cursor:
        for review, evidence in verified:
            cursor.execute(
                """
                UPDATE resenas
                SET vendedor_id=%s, pedido_linea_id=%s,
                    verificada_compra=1, motivo_no_verificada=NULL,
                    estado_moderacion='aprobada', aprobada=1
                WHERE id=%s AND public_id=%s
                """,
                (
                    evidence['vendedor_id'], evidence['pedido_linea_id'],
                    review['id'], review['public_id'],
                ),
            )
            if cursor.rowcount not in (0, 1):
                raise RuntimeError(f"Actualización inesperada para {review['public_id']}")
        historical_ids = [row['id'] for row in historical]
        placeholders = ','.join(['%s'] * len(historical_ids))
        cursor.execute(
            f"""
            SELECT COUNT(*) AS n FROM resenas
            WHERE id IN ({placeholders}) AND verificada_compra = 0
            """,
            tuple(historical_ids),
        )
        if int(cursor.fetchone()['n']) != EXPECTED_HISTORICAL:
            raise RuntimeError('Una reseña histórica perdió su estado no verificado.')
    connection.commit()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--env-file', type=Path, required=True)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--confirm-demo', action='store_true')
    args = parser.parse_args()
    if args.apply and not args.confirm_demo:
        raise SystemExit('Falta --confirm-demo; no se modificó ninguna reseña.')

    cfg = load_demo_env(args.env_file.resolve())
    os.environ.update(cfg)
    connection = pymysql.connect(
        host=cfg['MYSQL_HOST'], port=int(cfg['MYSQL_PORT']),
        user=cfg['MYSQL_USER'], password=cfg['MYSQL_PASSWORD'],
        database=cfg['MYSQL_DB'], charset='utf8mb4', autocommit=False,
        cursorclass=pymysql.cursors.DictCursor,
    )
    try:
        verified, historical = audit(connection)
        print(
            f'Resultado: {len(verified)} elegibles y '
            f'{len(historical)} históricas no verificadas.'
        )
        if not args.apply:
            print('[DRY-RUN] No se modificó MySQL ni Neo4j.')
            return 0
        apply(connection, verified, historical)
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

    subprocess.run(
        [sys.executable, 'scripts/backfill_neo4j_reviews.py', '--apply'],
        cwd=BACKEND_DIR, env={**os.environ, **cfg}, check=True,
    )
    print('Reconciliación DEMO aplicada y reproyectada a Neo4j.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
