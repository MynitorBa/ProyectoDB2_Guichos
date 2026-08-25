"""Lectura transaccional de ofertas, vendedores e inventario desde MySQL."""

from collections import defaultdict
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.inventario import Inventario
from app.models.oferta import Oferta, OfertaPrecioHistorial
from app.models.vendedor import Vendedor
from app.services.outbox_service import enqueue_outbox


def actualizar_precio_oferta(
    db: Session,
    *,
    oferta: Oferta,
    nuevo_precio: Decimal,
    usuario_id: int | None,
    motivo: str,
    enqueue_projection: bool = True,
) -> bool:
    """Actualiza precio, historial y outbox sin hacer commit."""
    nuevo_precio = Decimal(nuevo_precio).quantize(Decimal('0.01'))
    if oferta.precio_actual == nuevo_precio:
        return False

    precio_anterior = oferta.precio_actual
    ahora = datetime.now()
    vigente = db.query(OfertaPrecioHistorial).filter_by(
        oferta_id=oferta.id, vigente_hasta=None
    ).first()
    if vigente:
        vigente.vigente_hasta = ahora
        db.flush()

    oferta.precio_actual = nuevo_precio
    oferta.version += 1
    db.add(OfertaPrecioHistorial(
        oferta_id=oferta.id,
        precio=nuevo_precio,
        moneda=oferta.moneda,
        vigente_desde=ahora,
        cambiado_por=usuario_id,
        motivo=motivo,
    ))
    if enqueue_projection:
        enqueue_outbox(
            db,
            tipo_evento='oferta.precio_actualizado',
            agregado_tipo='oferta',
            agregado_id=oferta.id,
            producto_ref=oferta.producto_ref,
            payload={
                'projection': {
                    'precio': float(nuevo_precio),
                    'moneda': oferta.moneda,
                },
                'history': {
                    'tipo_evento': 'PRECIO_ACTUALIZADO',
                    'datos_anteriores': {'precio': float(precio_anterior)},
                    'datos_nuevos': {'precio': float(nuevo_precio)},
                    'usuario_id': str(usuario_id) if usuario_id is not None else None,
                },
            },
        )
    else:
        enqueue_outbox(
            db,
            tipo_evento='oferta.precio_actualizado',
            agregado_tipo='oferta',
            agregado_id=oferta.id,
            producto_ref=oferta.producto_ref,
            payload={
                'projection': {},
                'history': {
                    'tipo_evento': 'PRECIO_ACTUALIZADO',
                    'datos_anteriores': {'precio': float(precio_anterior)},
                    'datos_nuevos': {'precio': float(nuevo_precio)},
                    'usuario_id': str(usuario_id) if usuario_id is not None else None,
                },
            },
        )
    return True


def _stock_by_offer(db: Session, offer_ids: list[int]) -> dict[int, int]:
    if not offer_ids:
        return {}
    rows = (
        db.query(
            Inventario.oferta_id,
            func.sum(
                Inventario.cantidad_disponible - Inventario.cantidad_reservada
            ),
        )
        .filter(Inventario.oferta_id.in_(offer_ids))
        .group_by(Inventario.oferta_id)
        .all()
    )
    return {offer_id: max(0, int(stock or 0)) for offer_id, stock in rows}


def listar_ofertas_por_referencias(
    db: Session,
    producto_refs: list[str],
    *,
    solo_activas: bool = True,
) -> dict[str, list[dict]]:
    if not producto_refs:
        return {}

    query = (
        db.query(Oferta, Vendedor)
        .join(Vendedor, Vendedor.id == Oferta.vendedor_id)
        .filter(Oferta.producto_ref.in_(producto_refs))
    )
    if solo_activas:
        query = query.filter(Oferta.estado == 'activa')

    rows = query.all()
    offer_ids = [offer.id for offer, _ in rows]
    stock = _stock_by_offer(db, offer_ids)
    grouped = defaultdict(list)
    for offer, vendor in rows:
        available = stock.get(offer.id, 0)
        grouped[offer.producto_ref].append({
            'id': offer.id,
            'oferta_id': offer.id,
            'producto_ref': offer.producto_ref,
            'sku': offer.sku,
            'precio': float(offer.precio_actual),
            'moneda': offer.moneda,
            'estado': offer.estado,
            'version': offer.version,
            'vendedor_id': offer.vendedor_id,
            'vendedor_usuario_id': vendor.usuario_id,
            'vendedor_nombre': vendor.nombre_comercial,
            'stock': available,
            'disponible': offer.estado == 'activa' and available > 0,
        })

    for offers in grouped.values():
        offers.sort(key=lambda item: (
            not item['disponible'], item['precio'], item['oferta_id']
        ))
    return dict(grouped)


def oferta_principal(offers: list[dict]) -> dict | None:
    return offers[0] if offers else None


def enqueue_primary_offer_projection(
    db: Session, producto_ref: str, agregado_id: int
) -> None:
    """Proyecta en Mongo únicamente la oferta activa que gana la lectura."""
    offers = listar_ofertas_por_referencias(db, [producto_ref]).get(
        producto_ref, []
    )
    primary = oferta_principal(offers)
    projection = {
        'ofertas_count': len(offers),
        'disponible': bool(primary and primary['disponible']),
        'stock': primary['stock'] if primary else 0,
    }
    if primary:
        projection.update({
            'precio': primary['precio'],
            'moneda': primary['moneda'],
            'vendedor_id': primary['vendedor_id'],
            'vendedor_usuario_id': primary['vendedor_usuario_id'],
            'vendedor_nombre': primary['vendedor_nombre'],
        })
    enqueue_outbox(
        db,
        tipo_evento='producto.oferta_principal_actualizada',
        agregado_tipo='oferta',
        agregado_id=agregado_id,
        producto_ref=producto_ref,
        payload={'projection': projection},
    )


def resolver_oferta_comprable(
    db: Session,
    *,
    oferta_id: int,
) -> Oferta:
    offer = db.query(Oferta).filter_by(id=oferta_id, estado='activa').first()
    if not offer:
        raise LookupError('No existe una oferta activa para el producto solicitado.')
    return offer
