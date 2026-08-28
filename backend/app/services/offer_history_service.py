"""Consultas y escrituras temporales para ofertas e inventario."""

from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from typing import Iterable

from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.models.inventario import Inventario, InventarioSaldoHistorial
from app.models.oferta import Oferta, OfertaEstadoHistorial, OfertaPrecioHistorial
from app.models.vendedor import Vendedor


GT_TZ = timezone(timedelta(hours=-6))


def _as_utc_aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _as_utc_naive(value: datetime) -> datetime:
    return _as_utc_aware(value).replace(tzinfo=None)


def _gt_date(value: datetime) -> date:
    return _as_utc_aware(value).astimezone(GT_TZ).date()


def _gt_day_end_utc(value: date) -> datetime:
    local = datetime.combine(value, time(23, 59, 59, 999999), tzinfo=GT_TZ)
    return local.astimezone(timezone.utc).replace(tzinfo=None)


def registrar_estado_oferta(
    db: Session,
    *,
    oferta: Oferta,
    usuario_id: int | None,
    motivo: str,
    instante: datetime | None = None,
    forzar: bool = False,
) -> bool:
    """Cierra el intervalo previo e inserta la configuración vigente."""
    ahora = _as_utc_naive(instante or utc_now())
    vigente = db.query(OfertaEstadoHistorial).filter_by(
        oferta_id=oferta.id, vigente_hasta=None
    ).first()
    valores = (oferta.vendedor_id, oferta.sku, oferta.estado)
    if vigente and not forzar and (
        vigente.vendedor_id, vigente.sku, vigente.estado
    ) == valores:
        return False
    if vigente:
        if ahora <= vigente.vigente_desde:
            ahora = vigente.vigente_desde + timedelta(microseconds=1)
        vigente.vigente_hasta = ahora
        db.flush()
    db.add(OfertaEstadoHistorial(
        oferta_id=oferta.id,
        vendedor_id=oferta.vendedor_id,
        sku=oferta.sku,
        estado=oferta.estado,
        vigente_desde=ahora,
        cambiado_por=usuario_id,
        motivo=motivo,
    ))
    return True


def registrar_saldo_inventario(
    db: Session,
    *,
    inventario: Inventario,
    usuario_id: int | None,
    motivo: str,
    instante: datetime | None = None,
    forzar: bool = False,
) -> bool:
    """Cierra el saldo previo e inserta el saldo vigente de inventario."""
    ahora = _as_utc_naive(instante or utc_now())
    vigente = db.query(InventarioSaldoHistorial).filter_by(
        inventario_id=inventario.id, vigente_hasta=None
    ).first()
    valores = (inventario.cantidad_disponible, inventario.cantidad_reservada)
    if vigente and not forzar and (
        vigente.cantidad_disponible, vigente.cantidad_reservada
    ) == valores:
        return False
    if vigente:
        if ahora <= vigente.vigente_desde:
            ahora = vigente.vigente_desde + timedelta(microseconds=1)
        vigente.vigente_hasta = ahora
        db.flush()
    db.add(InventarioSaldoHistorial(
        inventario_id=inventario.id,
        cantidad_disponible=inventario.cantidad_disponible,
        cantidad_reservada=inventario.cantidad_reservada,
        vigente_desde=ahora,
        cambiado_por=usuario_id,
        motivo=motivo,
    ))
    return True


def _vigente_en(rows: Iterable, instante: datetime):
    candidates = [
        row for row in rows
        if row.vigente_desde <= instante
        and (row.vigente_hasta is None or instante < row.vigente_hasta)
    ]
    return max(candidates, key=lambda row: row.vigente_desde, default=None)


# Time-travel: reconstruye el estado de precio, estado e inventario de cada oferta en el instante dado
def reconstruir_ofertas_en_fecha(
    db: Session, *, producto_ref: str, instante_utc: datetime
) -> list[dict]:
    """Reconstruye todas las ofertas que ya existían en el instante indicado."""
    instante = _as_utc_naive(instante_utc)
    offers = db.query(Oferta).filter(
        Oferta.producto_ref == producto_ref,
        Oferta.fecha_creacion <= instante,
    ).order_by(Oferta.id).all()
    if not offers:
        return []

    offer_ids = [offer.id for offer in offers]
    prices = db.query(OfertaPrecioHistorial).filter(
        OfertaPrecioHistorial.oferta_id.in_(offer_ids),
        OfertaPrecioHistorial.vigente_desde <= instante,
    ).all()
    states = db.query(OfertaEstadoHistorial).filter(
        OfertaEstadoHistorial.oferta_id.in_(offer_ids),
        OfertaEstadoHistorial.vigente_desde <= instante,
    ).all()
    inventories = db.query(Inventario).filter(
        Inventario.oferta_id.in_(offer_ids), Inventario.bodega == 'principal'
    ).all()
    inventory_by_offer = {row.oferta_id: row for row in inventories}
    inventory_ids = [row.id for row in inventories]
    balances = (
        db.query(InventarioSaldoHistorial).filter(
            InventarioSaldoHistorial.inventario_id.in_(inventory_ids),
            InventarioSaldoHistorial.vigente_desde <= instante,
        ).all()
        if inventory_ids else []
    )

    prices_by_offer = defaultdict(list)
    states_by_offer = defaultdict(list)
    balances_by_inventory = defaultdict(list)
    for row in prices:
        prices_by_offer[row.oferta_id].append(row)
    for row in states:
        states_by_offer[row.oferta_id].append(row)
    for row in balances:
        balances_by_inventory[row.inventario_id].append(row)

    vendor_ids = {
        state.vendedor_id
        for rows in states_by_offer.values()
        for state in rows
    } | {offer.vendedor_id for offer in offers}
    vendors = {
        vendor.id: vendor.nombre_comercial
        for vendor in db.query(Vendedor).filter(Vendedor.id.in_(vendor_ids)).all()
    }

    result = []
    for offer in offers:
        price = _vigente_en(prices_by_offer[offer.id], instante)
        state = _vigente_en(states_by_offer[offer.id], instante)
        inventory = inventory_by_offer.get(offer.id)
        balance = (
            _vigente_en(balances_by_inventory[inventory.id], instante)
            if inventory else None
        )
        vendor_id = state.vendedor_id if state else offer.vendedor_id
        estado = state.estado if state else offer.estado
        disponible = balance.cantidad_disponible if balance else 0
        reservado = balance.cantidad_reservada if balance else 0
        result.append({
            'oferta_id': offer.id,
            'sku': state.sku if state else offer.sku,
            'vendedor_id': vendor_id,
            'vendedor_nombre': vendors.get(vendor_id, f'Vendedor {vendor_id}'),
            'precio': float(price.precio) if price else None,
            'moneda': price.moneda if price else offer.moneda,
            'estado': estado,
            'stock_disponible': disponible,
            'stock_reservado': reservado,
            'stock': max(0, disponible - reservado),
            'disponible': estado == 'activa' and disponible - reservado > 0,
        })
    return result


def historial_precios_diario(
    db: Session,
    *,
    producto_ref: str,
    desde: date | None = None,
    hasta: date | None = None,
) -> dict:
    """Devuelve el último precio vigente de cada oferta al cierre de cada día GT."""
    offers = db.query(Oferta).filter_by(producto_ref=producto_ref).order_by(Oferta.id).all()
    if not offers:
        return {'producto_id': producto_ref, 'desde': None, 'hasta': None, 'ofertas': []}

    offer_ids = [offer.id for offer in offers]
    histories = db.query(OfertaPrecioHistorial).filter(
        OfertaPrecioHistorial.oferta_id.in_(offer_ids)
    ).order_by(OfertaPrecioHistorial.vigente_desde).all()
    if not histories:
        return {'producto_id': producto_ref, 'desde': None, 'hasta': None, 'ofertas': []}

    first_day = min(_gt_date(row.vigente_desde) for row in histories)
    today_gt = datetime.now(timezone.utc).astimezone(GT_TZ).date()
    start = desde or first_day
    end = hasta or today_gt
    if start > end:
        raise ValueError('La fecha inicial no puede ser posterior a la fecha final.')

    rows_by_offer = defaultdict(list)
    for row in histories:
        rows_by_offer[row.oferta_id].append(row)
    vendors = {
        vendor.id: vendor.nombre_comercial
        for vendor in db.query(Vendedor).filter(
            Vendedor.id.in_({offer.vendedor_id for offer in offers})
        ).all()
    }

    result = []
    for offer in offers:
        points = []
        day = start
        while day <= end:
            sample = _gt_day_end_utc(day)
            price = _vigente_en(rows_by_offer[offer.id], sample)
            if price:
                points.append({
                    'fecha': day.isoformat(),
                    'precio': float(price.precio),
                    'moneda': price.moneda,
                })
            day += timedelta(days=1)
        if points:
            result.append({
                'oferta_id': offer.id,
                'sku': offer.sku,
                'vendedor_id': offer.vendedor_id,
                'vendedor_nombre': vendors.get(
                    offer.vendedor_id, f'Vendedor {offer.vendedor_id}'
                ),
                'estado_actual': offer.estado,
                'puntos': points,
            })
    return {
        'producto_id': producto_ref,
        'desde': start.isoformat(),
        'hasta': end.isoformat(),
        'criterio_diario': 'último precio vigente a las 23:59:59 de Guatemala',
        'ofertas': result,
    }


# Convierte los registros temporales de precio, estado e inventario en eventos auditables con formato homogéneo
def historial_operativo_unificado(
    db: Session,
    *,
    producto_ref: str,
    desde_utc: datetime | None = None,
    hasta_utc: datetime | None = None,
) -> list[dict]:
    """Normaliza precio, estado e inventario MySQL como eventos auditables."""
    offers = db.query(Oferta).filter_by(producto_ref=producto_ref).order_by(Oferta.id).all()
    if not offers:
        return []
    offer_ids = [offer.id for offer in offers]
    vendor_ids = {offer.vendedor_id for offer in offers}
    vendors = {
        vendor.id: vendor.nombre_comercial
        for vendor in db.query(Vendedor).filter(Vendedor.id.in_(vendor_ids)).all()
    }
    offer_by_id = {offer.id: offer for offer in offers}
    inventories = db.query(Inventario).filter(
        Inventario.oferta_id.in_(offer_ids), Inventario.bodega == 'principal'
    ).all()
    inventory_by_id = {inventory.id: inventory for inventory in inventories}

    def in_range(value: datetime) -> bool:
        return (
            (desde_utc is None or value >= desde_utc)
            and (hasta_utc is None or value <= hasta_utc)
        )

    def timestamp_gt(value: datetime) -> str:
        return _as_utc_aware(value).astimezone(GT_TZ).isoformat()

    events = []
    price_rows = db.query(OfertaPrecioHistorial).filter(
        OfertaPrecioHistorial.oferta_id.in_(offer_ids)
    ).order_by(OfertaPrecioHistorial.oferta_id, OfertaPrecioHistorial.vigente_desde).all()
    previous_price = {}
    for row in price_rows:
        offer = offer_by_id[row.oferta_id]
        before = previous_price.get(row.oferta_id)
        previous_price[row.oferta_id] = row
        if not in_range(row.vigente_desde):
            continue
        events.append({
            '_id': f'mysql-precio-{row.id}',
            'fuente': 'mysql',
            'entidad': 'oferta',
            'tipo_evento': 'OFERTA_PRECIO_INICIAL' if before is None else 'OFERTA_PRECIO_ACTUALIZADO',
            'timestamp': timestamp_gt(row.vigente_desde),
            'usuario_id': str(row.cambiado_por) if row.cambiado_por else None,
            'datos_anteriores': ({'precio': float(before.precio)} if before else {}),
            'datos_nuevos': {
                'oferta_id': row.oferta_id,
                'vendedor': vendors.get(offer.vendedor_id),
                'sku': offer.sku,
                'precio': float(row.precio),
                'moneda': row.moneda,
                'motivo': row.motivo,
            },
        })

    state_rows = db.query(OfertaEstadoHistorial).filter(
        OfertaEstadoHistorial.oferta_id.in_(offer_ids)
    ).order_by(OfertaEstadoHistorial.oferta_id, OfertaEstadoHistorial.vigente_desde).all()
    previous_state = {}
    for row in state_rows:
        before = previous_state.get(row.oferta_id)
        previous_state[row.oferta_id] = row
        if not in_range(row.vigente_desde):
            continue
        events.append({
            '_id': f'mysql-estado-{row.id}',
            'fuente': 'mysql',
            'entidad': 'oferta',
            'tipo_evento': 'OFERTA_ESTADO_INICIAL' if before is None else 'OFERTA_ESTADO_CAMBIADO',
            'timestamp': timestamp_gt(row.vigente_desde),
            'usuario_id': str(row.cambiado_por) if row.cambiado_por else None,
            'datos_anteriores': ({'estado': before.estado} if before else {}),
            'datos_nuevos': {
                'oferta_id': row.oferta_id,
                'vendedor': vendors.get(row.vendedor_id),
                'sku': row.sku,
                'estado': row.estado,
                'motivo': row.motivo,
            },
        })

    inventory_ids = list(inventory_by_id)
    balance_rows = (
        db.query(InventarioSaldoHistorial).filter(
            InventarioSaldoHistorial.inventario_id.in_(inventory_ids)
        ).order_by(
            InventarioSaldoHistorial.inventario_id,
            InventarioSaldoHistorial.vigente_desde,
        ).all()
        if inventory_ids else []
    )
    previous_balance = {}
    for row in balance_rows:
        before = previous_balance.get(row.inventario_id)
        previous_balance[row.inventario_id] = row
        if not in_range(row.vigente_desde):
            continue
        inventory = inventory_by_id[row.inventario_id]
        offer = offer_by_id[inventory.oferta_id]
        events.append({
            '_id': f'mysql-inventario-{row.id}',
            'fuente': 'mysql',
            'entidad': 'inventario',
            'tipo_evento': 'INVENTARIO_SALDO_INICIAL' if before is None else 'INVENTARIO_SALDO_CAMBIADO',
            'timestamp': timestamp_gt(row.vigente_desde),
            'usuario_id': str(row.cambiado_por) if row.cambiado_por else None,
            'datos_anteriores': ({
                'stock_disponible': before.cantidad_disponible,
                'stock_reservado': before.cantidad_reservada,
            } if before else {}),
            'datos_nuevos': {
                'oferta_id': offer.id,
                'vendedor': vendors.get(offer.vendedor_id),
                'stock_disponible': row.cantidad_disponible,
                'stock_reservado': row.cantidad_reservada,
                'motivo': row.motivo,
            },
        })
    return events
