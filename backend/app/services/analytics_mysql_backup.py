"""Proyección analítica semanal en MySQL para consultas cuando falla Cassandra.

Las filas se recalculan a partir de pedidos y pagos autoritativos. Repetir un
evento reemplaza la semana completa en una transacción, sin sumar deltas dos veces.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal
import logging

from pymongo.errors import PyMongoError

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.analytics_service import ZERO, _paid_lines, _product_images, _week_for_row


logger = logging.getLogger(__name__)


PRODUCTS = 'analitica_productos_semana'
VENDOR_PRODUCTS = 'analitica_productos_vendedor_semana'
VENDOR_OFFERS = 'analitica_ofertas_vendedor_semana'
TABLES = (PRODUCTS, VENDOR_PRODUCTS, VENDOR_OFFERS)


def _aggregate(group: list[dict], *, vendors: bool = False, offers: bool = False) -> dict:
    valid = [row for row in group if row['estado_pago'] != 'reembolsado']
    gross = sum((row['subtotal'] for row in group), ZERO)
    refunded = sum((row['subtotal'] for row in group if row['estado_pago'] == 'reembolsado'), ZERO)
    result = {
        'unidades_vendidas': sum(row['cantidad'] for row in valid),
        'ingresos_brutos': gross,
        'ingresos_reembolsados': refunded,
        'ingresos_netos': gross - refunded,
        'pedidos_distintos': len({row['pedido_id'] for row in valid}),
        'unidades_flash': sum(row['cantidad'] for row in valid if row['promocion_flash_id']),
    }
    if vendors:
        result['vendedores_distintos'] = len({row['vendedor_id'] for row in valid})
    if offers:
        result['ofertas_distintas'] = len({row['oferta_id'] for row in valid})
    return result


def summarize_week(rows: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    """Mismas reglas de pago, reembolso y semana que la proyección Cassandra."""
    products, vendor_products, vendor_offers = defaultdict(list), defaultdict(list), defaultdict(list)
    for row in rows:
        week = _week_for_row(row)
        products[(week, row['producto_ref'])].append(row)
        vendor_products[(row['vendedor_id'], row['producto_ref'], week)].append(row)
        vendor_offers[(row['vendedor_id'], week, row['oferta_id'])].append(row)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    product_rows = [{
        'semana_inicio': week, 'producto_ref': ref,
        'producto_nombre_snapshot': group[-1]['producto_nombre_snapshot'],
        'imagen_snapshot': None,
        **_aggregate(group, vendors=True, offers=True), 'actualizado_en': now,
    } for (week, ref), group in products.items()]
    vendor_product_rows = [{
        'vendedor_id': vendor_id, 'producto_ref': ref, 'semana_inicio': week,
        'producto_nombre_snapshot': group[-1]['producto_nombre_snapshot'],
        **_aggregate(group, offers=True), 'actualizado_en': now,
    } for (vendor_id, ref, week), group in vendor_products.items()]
    vendor_offer_rows = [{
        'vendedor_id': vendor_id, 'semana_inicio': week, 'oferta_id': offer_id,
        'producto_ref': group[-1]['producto_ref'],
        'producto_nombre_snapshot': group[-1]['producto_nombre_snapshot'],
        'sku_snapshot': group[-1]['sku_snapshot'],
        **_aggregate(group), 'actualizado_en': now,
    } for (vendor_id, week, offer_id), group in vendor_offers.items()]
    return product_rows, vendor_product_rows, vendor_offer_rows


def rebuild_week_mysql(week: date, db: Session) -> dict:
    rows = _paid_lines(db, week)
    product_rows, vendor_product_rows, vendor_offer_rows = summarize_week(rows)
    # La imagen no participa en los importes; conservar la ya copiada si existe.
    images = dict(db.execute(text(
        f'SELECT producto_ref, imagen_snapshot FROM {PRODUCTS} WHERE semana_inicio=:week'
    ), {'week': week}).all())
    missing = {item['producto_ref'] for item in product_rows if not images.get(item['producto_ref'])}
    if missing:
        try:
            from app.core.db_mongo import get_mongo_db
            images.update(_product_images(get_mongo_db(), missing))
        except PyMongoError as exc:
            logger.warning('MongoDB no disponible para imágenes analíticas; se conservan las copiadas: %s', exc)
    for item in product_rows:
        item['imagen_snapshot'] = images.get(item['producto_ref'])
    try:
        for table in TABLES:
            db.execute(text(f'DELETE FROM {table} WHERE semana_inicio=:week'), {'week': week})
        for table, items in zip(TABLES, (product_rows, vendor_product_rows, vendor_offer_rows)):
            if not items:
                continue
            fields = tuple(items[0])
            columns = ', '.join(fields)
            binds = ', '.join(f':{field}' for field in fields)
            db.execute(text(f'INSERT INTO {table} ({columns}) VALUES ({binds})'), items)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {'semana_inicio': week.isoformat(), 'lineas': len(rows),
            'productos': len(product_rows), 'productos_vendedor': len(vendor_product_rows),
            'ofertas': len(vendor_offer_rows)}


def project_order_mysql(order_id: int, db: Session) -> dict:
    moment = db.execute(text('SELECT fecha_creacion FROM pedidos WHERE id=:id'), {'id': order_id}).scalar()
    if moment is None:
        return {'lineas': 0}
    return rebuild_week_mysql(_week_for_row({'fecha_hora': moment}), db)


class MySQLAnalyticsAdapter:
    """Expone las cuatro lecturas Cassandra existentes sobre índices MySQL.

    El SQL aceptado es fijo y generado únicamente por analytics_service; jamás
    recibe nombres de tabla o columnas del cliente HTTP.
    """

    def __init__(self, db: Session):
        self.db = db

    def ready(self) -> bool:
        return bool(self.db.execute(text(
            'SELECT backfill_completo FROM analitica_respaldo_control WHERE id=1'
        )).scalar())

    def execute(self, query: str, params: tuple):
        normalized = ' '.join(query.lower().split())
        if 'from resumen_productos_semana' in normalized:
            return self.db.execute(text(f'SELECT * FROM {PRODUCTS} WHERE semana_inicio=:week'),
                                   {'week': params[0]})
        if 'from tendencia_producto_semana' in normalized:
            return self.db.execute(text(f'''SELECT * FROM {PRODUCTS}
                WHERE producto_ref=:ref AND semana_inicio BETWEEN :start AND :end'''),
                {'ref': params[0], 'start': params[1], 'end': params[2]})
        if 'from tendencia_producto_vendedor_semana' in normalized:
            return self.db.execute(text(f'''SELECT * FROM {VENDOR_PRODUCTS}
                WHERE vendedor_id=:vendor AND producto_ref=:ref
                  AND semana_inicio BETWEEN :start AND :end'''),
                {'vendor': params[0], 'ref': params[1], 'start': params[2], 'end': params[3]})
        if 'from resumen_ofertas_vendedor_semana' in normalized:
            return self.db.execute(text(f'''SELECT * FROM {VENDOR_OFFERS}
                WHERE vendedor_id=:vendor AND semana_inicio=:week'''),
                {'vendor': params[0], 'week': params[1]})
        raise ValueError('Consulta analítica no soportada por el respaldo MySQL')
