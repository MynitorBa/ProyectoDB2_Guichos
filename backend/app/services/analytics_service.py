"""Proyección analítica MySQL -> Cassandra orientada a semanas de Guatemala."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

from bson import ObjectId
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.db_cassandra import get_cassandra_session
from app.core.db_mongo import get_mongo_db
from app.core.db_mysql import SessionLocal


GT_TZ = timezone(timedelta(hours=-6))
ZERO = Decimal('0.00')


def current_week_start(now: datetime | None = None) -> date:
    value = now or datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    local_date = value.astimezone(GT_TZ).date()
    return local_date - timedelta(days=local_date.weekday())


def previous_week_start(week_start: date) -> date:
    if not isinstance(week_start, date) and hasattr(week_start, 'date'):
        week_start = week_start.date()
    return week_start - timedelta(days=7)


def _utc_bounds(week_start: date) -> tuple[datetime, datetime]:
    local_start = datetime.combine(week_start, time.min, tzinfo=GT_TZ)
    local_end = local_start + timedelta(days=7)
    return (
        local_start.astimezone(timezone.utc).replace(tzinfo=None),
        local_end.astimezone(timezone.utc).replace(tzinfo=None),
    )


def _paid_lines(db: Session, week_start: date | None = None) -> list[dict]:
    where = """
      EXISTS (
        SELECT 1 FROM pagos pg
        WHERE pg.pedido_id = p.id AND pg.estado IN ('aprobado', 'reembolsado')
      )
      AND (
        p.estado <> 'cancelado'
        OR EXISTS (
          SELECT 1 FROM pagos prc
          WHERE prc.pedido_id = p.id AND prc.estado = 'reembolsado'
        )
      )
    """
    params = {}
    if week_start is not None:
        start, end = _utc_bounds(week_start)
        where += ' AND p.fecha_creacion >= :start AND p.fecha_creacion < :end'
        params = {'start': start, 'end': end}
    query = text(f"""
      SELECT
        pl.id AS pedido_linea_id,
        pl.pedido_id,
        pl.oferta_id,
        pl.producto_ref,
        pl.sku_snapshot,
        pl.producto_nombre AS producto_nombre_snapshot,
        pl.vendedor_nombre_snapshot,
        pl.precio_unitario,
        pl.cantidad,
        pl.subtotal_linea AS subtotal,
        p.fecha_creacion AS fecha_hora,
        p.estado AS estado_pedido,
        pv.vendedor_id,
        o.producto_variante_id AS variante_id,
        CASE
          WHEN p.estado = 'reembolsado' OR EXISTS (
            SELECT 1 FROM pagos pr
            WHERE pr.pedido_id = p.id AND pr.estado = 'reembolsado'
          ) THEN 'reembolsado'
          ELSE 'aprobado'
        END AS estado_pago,
        (
          SELECT pf.id
          FROM reservas_flash rf
          JOIN promociones_flash pf ON pf.id = rf.promocion_id
          WHERE rf.pedido_id = p.id
            AND rf.estado = 'convertida'
            AND pf.oferta_id = pl.oferta_id
          ORDER BY rf.fecha_actualizacion DESC
          LIMIT 1
        ) AS promocion_flash_id
      FROM pedido_lineas pl
      JOIN pedidos p ON p.id = pl.pedido_id
      JOIN pedido_vendedores pv ON pv.id = pl.pedido_vendedor_id
      JOIN ofertas o ON o.id = pl.oferta_id
      WHERE {where}
      ORDER BY p.fecha_creacion, pl.id
    """)
    return [dict(row) for row in db.execute(query, params).mappings().all()]


def _product_images(mongo, refs: set[str]) -> dict[str, str | None]:
    valid_ids = []
    for ref in refs:
        try:
            valid_ids.append(ObjectId(ref))
        except Exception:
            continue
    result: dict[str, str | None] = {}
    for product in mongo.productos.find({'_id': {'$in': valid_ids}}, {'imagenes': 1}):
        images = product.get('imagenes') or []
        first = images[0] if images else None
        result[str(product['_id'])] = first.get('url') if isinstance(first, dict) else first
    return result


def _week_for_row(row: dict) -> date:
    moment = row['fecha_hora']
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    local_date = moment.astimezone(GT_TZ).date()
    return local_date - timedelta(days=local_date.weekday())


def _write_rows(cassandra, rows: list[dict], mongo) -> dict:
    detail = cassandra.prepare("""
      INSERT INTO ventas_producto_semana (
        producto_ref, semana_inicio, fecha_hora, pedido_linea_id, pedido_id,
        oferta_id, vendedor_id, variante_id, sku_snapshot,
        producto_nombre_snapshot, vendedor_nombre_snapshot, cantidad,
        precio_unitario, subtotal, tipo_venta, promocion_flash_id, estado_pago
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """)
    product_summary = cassandra.prepare("""
      INSERT INTO resumen_productos_semana (
        semana_inicio, producto_ref, producto_nombre_snapshot, imagen_snapshot,
        unidades_vendidas, ingresos_brutos, ingresos_reembolsados,
        ingresos_netos, pedidos_distintos, vendedores_distintos,
        ofertas_distintas, unidades_flash, actualizado_en
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """)
    vendor_summary = cassandra.prepare("""
      INSERT INTO resumen_ofertas_vendedor_semana (
        vendedor_id, semana_inicio, oferta_id, producto_ref,
        producto_nombre_snapshot, sku_snapshot, unidades_vendidas,
        ingresos_brutos, ingresos_reembolsados, ingresos_netos,
        pedidos_distintos, unidades_flash, actualizado_en
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """)

    product_groups = defaultdict(list)
    vendor_groups = defaultdict(list)
    images = _product_images(mongo, {row['producto_ref'] for row in rows})
    for row in rows:
        week = _week_for_row(row)
        refunded = row['estado_pago'] == 'reembolsado'
        flash_id = row['promocion_flash_id']
        cassandra.execute(detail, (
            row['producto_ref'], week, row['fecha_hora'], row['pedido_linea_id'],
            row['pedido_id'], row['oferta_id'], row['vendedor_id'], row['variante_id'],
            row['sku_snapshot'], row['producto_nombre_snapshot'],
            row['vendedor_nombre_snapshot'], row['cantidad'], row['precio_unitario'],
            row['subtotal'], 'flash' if flash_id else 'normal', flash_id,
            row['estado_pago'],
        ))
        product_groups[(week, row['producto_ref'])].append(row)
        vendor_groups[(row['vendedor_id'], week, row['oferta_id'])].append(row)

    updated = datetime.now(timezone.utc)
    for (week, product_ref), group in product_groups.items():
        refunded_rows = [row for row in group if row['estado_pago'] == 'reembolsado']
        gross = sum((row['subtotal'] for row in group), ZERO)
        refunded = sum((row['subtotal'] for row in refunded_rows), ZERO)
        cassandra.execute(product_summary, (
            week, product_ref, group[-1]['producto_nombre_snapshot'], images.get(product_ref),
            sum(row['cantidad'] for row in group if row['estado_pago'] != 'reembolsado'),
            gross, refunded, gross - refunded,
            len({row['pedido_id'] for row in group if row['estado_pago'] != 'reembolsado'}),
            len({row['vendedor_id'] for row in group if row['estado_pago'] != 'reembolsado'}),
            len({row['oferta_id'] for row in group if row['estado_pago'] != 'reembolsado'}),
            sum(row['cantidad'] for row in group if row['promocion_flash_id'] and row['estado_pago'] != 'reembolsado'),
            updated,
        ))

    for (vendor_id, week, offer_id), group in vendor_groups.items():
        refunded_rows = [row for row in group if row['estado_pago'] == 'reembolsado']
        gross = sum((row['subtotal'] for row in group), ZERO)
        refunded = sum((row['subtotal'] for row in refunded_rows), ZERO)
        cassandra.execute(vendor_summary, (
            vendor_id, week, offer_id, group[-1]['producto_ref'],
            group[-1]['producto_nombre_snapshot'], group[-1]['sku_snapshot'],
            sum(row['cantidad'] for row in group if row['estado_pago'] != 'reembolsado'),
            gross, refunded, gross - refunded,
            len({row['pedido_id'] for row in group if row['estado_pago'] != 'reembolsado'}),
            sum(row['cantidad'] for row in group if row['promocion_flash_id'] and row['estado_pago'] != 'reembolsado'),
            updated,
        ))
    return {
        'lineas': len(rows),
        'productos_semana': len(product_groups),
        'ofertas_vendedor_semana': len(vendor_groups),
    }


def rebuild_all(db: Session, cassandra=None, mongo=None) -> dict:
    target = cassandra or get_cassandra_session()
    source_mongo = mongo or get_mongo_db()
    rows = _paid_lines(db)
    target.execute('TRUNCATE ventas_producto_semana')
    target.execute('TRUNCATE resumen_productos_semana')
    target.execute('TRUNCATE resumen_ofertas_vendedor_semana')
    return _write_rows(target, rows, source_mongo)


def rebuild_week(week_start: date, db: Session, cassandra=None, mongo=None) -> dict:
    target = cassandra or get_cassandra_session()
    source_mongo = mongo or get_mongo_db()
    rows = _paid_lines(db, week_start)
    previous_refs = {
        row.producto_ref
        for row in target.execute(
            'SELECT producto_ref FROM resumen_productos_semana WHERE semana_inicio=%s',
            (week_start,),
        )
    }
    refs = previous_refs | {row['producto_ref'] for row in rows}
    start, end = _utc_bounds(week_start)
    # Incluye vendedores cuyas únicas ventas de la semana fueron canceladas;
    # así también se elimina cualquier resumen anterior que ya no sea válido.
    vendors = set(db.execute(text("""
      SELECT DISTINCT pv.vendedor_id
      FROM pedido_lineas pl
      JOIN pedidos p ON p.id = pl.pedido_id
      JOIN pedido_vendedores pv ON pv.id = pl.pedido_vendedor_id
      WHERE p.fecha_creacion >= :start AND p.fecha_creacion < :end
    """), {'start': start, 'end': end}).scalars().all())
    target.execute('DELETE FROM resumen_productos_semana WHERE semana_inicio=%s', (week_start,))
    for ref in refs:
        target.execute(
            'DELETE FROM ventas_producto_semana WHERE producto_ref=%s AND semana_inicio=%s',
            (ref, week_start),
        )
    for vendor_id in vendors:
        target.execute(
            'DELETE FROM resumen_ofertas_vendedor_semana WHERE vendedor_id=%s AND semana_inicio=%s',
            (vendor_id, week_start),
        )
    return _write_rows(target, rows, source_mongo)


def project_order(order_id: int) -> dict:
    with SessionLocal() as db:
        moments = db.execute(
            text('SELECT fecha_creacion FROM pedidos WHERE id=:id'), {'id': order_id}
        ).scalars().all()
        if not moments:
            return {'lineas': 0, 'productos_semana': 0, 'ofertas_vendedor_semana': 0}
        week = _week_for_row({'fecha_hora': moments[0]})
        return rebuild_week(week, db)


def _serialize_summary(row) -> dict:
    return {
        'producto_ref': row.producto_ref,
        'producto_nombre': row.producto_nombre_snapshot,
        'imagen': row.imagen_snapshot,
        'unidades': int(row.unidades_vendidas),
        'ingresos_brutos': float(row.ingresos_brutos),
        'ingresos_reembolsados': float(row.ingresos_reembolsados),
        'ingresos_netos': float(row.ingresos_netos),
        'pedidos': int(row.pedidos_distintos),
        'vendedores': int(row.vendedores_distintos),
        'ofertas': int(row.ofertas_distintas),
        'unidades_flash': int(row.unidades_flash),
    }


def product_trends(week_start: date, cassandra=None) -> list[dict]:
    target = cassandra or get_cassandra_session()
    current = {
        row.producto_ref: _serialize_summary(row)
        for row in target.execute(
            'SELECT * FROM resumen_productos_semana WHERE semana_inicio=%s',
            (week_start,),
        )
    }
    previous = {
        row.producto_ref: row
        for row in target.execute(
            'SELECT producto_ref, unidades_vendidas FROM resumen_productos_semana WHERE semana_inicio=%s',
            (previous_week_start(week_start),),
        )
    }
    result = []
    for ref, item in current.items():
        old_units = int(previous[ref].unidades_vendidas) if ref in previous else 0
        item['unidades_semana_anterior'] = old_units
        item['variacion_unidades'] = item['unidades'] - old_units
        item['variacion_porcentaje'] = (
            round((item['unidades'] - old_units) * 100 / old_units, 2)
            if old_units else (100.0 if item['unidades'] else 0.0)
        )
        result.append(item)
    return sorted(result, key=lambda item: (item['variacion_unidades'], item['unidades']), reverse=True)


def vendor_offer_summary(vendor_id: int, week_start: date, cassandra=None) -> list[dict]:
    target = cassandra or get_cassandra_session()
    rows = target.execute(
        'SELECT * FROM resumen_ofertas_vendedor_semana WHERE vendedor_id=%s AND semana_inicio=%s',
        (vendor_id, week_start),
    )
    return sorted([{
        'oferta_id': int(row.oferta_id),
        'producto_ref': row.producto_ref,
        'producto_nombre': row.producto_nombre_snapshot,
        'sku': row.sku_snapshot,
        'unidades': int(row.unidades_vendidas),
        'ingresos_brutos': float(row.ingresos_brutos),
        'ingresos_reembolsados': float(row.ingresos_reembolsados),
        'ingresos_netos': float(row.ingresos_netos),
        'pedidos': int(row.pedidos_distintos),
        'unidades_flash': int(row.unidades_flash),
    } for row in rows], key=lambda item: item['unidades'], reverse=True)
