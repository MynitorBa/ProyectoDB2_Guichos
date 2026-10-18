r"""Reconstruye en Neo4j compras pagadas y reseñas históricas reales.

Neo4j es una proyección reconstruible: MySQL conserva los pedidos y las
reseñas heredadas. El script nunca inventa compras ni vendedores. Una reseña
sin compra pagada compatible se migra como no verificada y pendiente.

Uso desde ``backend/``::

    .\venv\Scripts\python.exe scripts\backfill_neo4j_reviews.py --dry-run
    .\venv\Scripts\python.exe scripts\backfill_neo4j_reviews.py --apply
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from bson import ObjectId
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))

from app.core.db_mongo import get_mongo_db  # noqa: E402
from app.core.db_mysql import engine  # noqa: E402
from app.core.db_neo4j import close_driver, get_driver  # noqa: E402


PURCHASES_SQL = text("""
    SELECT pl.id AS linea_id, p.id AS pedido_id, p.usuario_id,
           u.nombre, u.apellido, u.email,
           pl.producto_ref, pl.producto_nombre, pl.oferta_id,
           pv.vendedor_id, v.nombre_comercial AS vendedor_nombre,
           pl.cantidad, pl.precio_unitario, pl.sku_snapshot,
           p.fecha_creacion,
           (SELECT rf.promocion_id FROM reservas_flash rf
            JOIN promociones_flash pf ON pf.id=rf.promocion_id
            WHERE rf.pedido_id=p.id AND rf.estado='convertida'
              AND pf.oferta_id=pl.oferta_id
            ORDER BY rf.fecha_creacion DESC LIMIT 1) AS promocion_flash_id
    FROM pedido_lineas pl
    JOIN pedidos p ON p.id = pl.pedido_id
    JOIN usuarios u ON u.id = p.usuario_id
    JOIN pedido_vendedores pv ON pv.id = pl.pedido_vendedor_id
    JOIN vendedores v ON v.id = pv.vendedor_id
    WHERE p.estado NOT IN ('cancelado', 'reembolsado')
      AND EXISTS (
          SELECT 1 FROM pagos pa
          WHERE pa.pedido_id = p.id AND pa.estado = 'aprobado'
      )
    ORDER BY p.fecha_creacion, pl.id
""")

OFFERS_SQL = text("""
    SELECT o.id AS oferta_id, o.producto_ref, o.producto_variante_id,
           pvr.variante_ref, o.sku, o.estado,
           v.id AS vendedor_id, v.nombre_comercial AS vendedor_nombre,
           v.usuario_id AS vendedor_usuario_id
    FROM ofertas o
    JOIN vendedores v ON v.id=o.vendedor_id
    JOIN producto_variante_referencias pvr ON pvr.id=o.producto_variante_id
    ORDER BY o.id
""")

def _iso(value: datetime) -> str:
    return value.replace(tzinfo=timezone.utc).isoformat()


def _product_names(refs: set[str], purchases: list[dict]) -> dict[str, str]:
    names = {
        row['producto_ref']: row['producto_nombre']
        for row in purchases if row.get('producto_nombre')
    }
    object_ids = [ObjectId(ref) for ref in refs if ObjectId.is_valid(ref)]
    for doc in get_mongo_db().productos.find(
        {'_id': {'$in': object_ids}}, {'nombre': 1},
    ):
        names[str(doc['_id'])] = doc.get('nombre') or names.get(str(doc['_id']), str(doc['_id']))
    return {ref: names.get(ref, ref) for ref in refs}


def _project_purchase(session, row: dict) -> None:
    from app.services.review_service import (
        ensure_producto, ensure_usuario, ensure_vendedor, registrar_compra,
    )
    ensure_usuario(
        session, row['usuario_id'],
        f"{row['nombre']} {row['apellido']}".strip(), row['email'],
    )
    ensure_producto(session, row['producto_ref'], row['producto_nombre'])
    ensure_vendedor(session, row['vendedor_id'], row['vendedor_nombre'])
    registrar_compra(
        session, row['usuario_id'], row['producto_ref'], row['pedido_id'],
        row['oferta_id'], _iso(row['fecha_creacion']),
        linea_id=row['linea_id'], vendedor_id=row['vendedor_id'],
        cantidad=row['cantidad'], precio_unitario=float(row['precio_unitario']),
        sku=row['sku_snapshot'], promocion_flash_id=row['promocion_flash_id'],
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--dry-run', action='store_true')
    mode.add_argument('--apply', action='store_true')
    args = parser.parse_args()

    with engine.connect() as connection:
        purchases = [dict(row) for row in connection.execute(PURCHASES_SQL).mappings()]
        offers = [dict(row) for row in connection.execute(OFFERS_SQL).mappings()]
        review_ids = [row[0] for row in connection.execute(text(
            'SELECT id FROM resenas ORDER BY id'
        ))]

    print(f'Compras pagadas a proyectar: {len(purchases)}')
    print(f'Ofertas a proyectar como relaciones: {len(offers)}')
    print(f'Reseñas MySQL a proyectar: {len(review_ids)}')
    if args.dry_run:
        print('[DRY-RUN] Neo4j no fue modificado.')
        return 0

    refs = {row['producto_ref'] for row in purchases} | {
        row['producto_ref'] for row in offers
    }
    names = _product_names(refs, purchases)
    for purchase in purchases:
        purchase['producto_nombre'] = names[purchase['producto_ref']]

    driver = get_driver()
    try:
        with driver.session() as session:
            from app.services.review_service import proyectar_oferta
            for offer in offers:
                proyectar_oferta(session, **offer)
            for purchase in purchases:
                _project_purchase(session, purchase)
            from app.core.db_mysql import SessionLocal
            from app.services.review_service import proyectar_resena_mysql
            with SessionLocal() as db:
                for review_id in review_ids:
                    proyectar_resena_mysql(session, db, review_id)
            counts = session.run("""
                MATCH (p:Producto)
                OPTIONAL MATCH (c:Compra)-[:DE_PRODUCTO]->(p)
                WITH count(DISTINCT p) AS productos, count(DISTINCT c) AS compras
                OPTIONAL MATCH (r:Reseña)
                RETURN productos, compras, count(r) AS resenas,
                       count(CASE WHEN r.verificada THEN 1 END) AS verificadas
            """).single()
        print(
            'Neo4j reconstruido: '
            f"{counts['productos']} productos, {counts['compras']} compras, "
            f"{counts['resenas']} reseñas ({counts['verificadas']} verificadas)."
        )
        return 0
    finally:
        close_driver()


if __name__ == '__main__':
    raise SystemExit(main())
