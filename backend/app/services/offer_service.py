"""Lectura transaccional de ofertas, vendedores e inventario desde MySQL."""

from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.inventario import Inventario
from app.models.oferta import Oferta, OfertaPrecioHistorial
from app.models.producto_variante_referencia import ProductoVarianteReferencia
from app.models.vendedor import Vendedor
from app.core.time import utc_now
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

    ahora = utc_now()
    vigente = db.query(OfertaPrecioHistorial).filter_by(
        oferta_id=oferta.id, vigente_hasta=None
    ).first()
    if vigente:
        if ahora <= vigente.vigente_desde:
            ahora = vigente.vigente_desde + timedelta(microseconds=1)
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
    enqueue_outbox(
        db,
        tipo_evento='oferta.precio_actualizado',
        agregado_tipo='oferta',
        agregado_id=oferta.id,
        producto_ref=oferta.producto_ref,
        payload={'projection': ({
            'precio': float(nuevo_precio),
            'moneda': oferta.moneda,
        } if enqueue_projection else {})},
    )
    return True


def stock_by_offer(db: Session, offer_ids: list[int]) -> dict[int, int]:
    """Stock neto (disponible - reservado) por oferta_id."""
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


# Carga en una sola query todas las ofertas de una lista de producto_refs y calcula el stock neto
def listar_ofertas_por_referencias(
    db: Session,
    producto_refs: list[str],
    *,
    solo_activas: bool = True,
) -> dict[str, list[dict]]:
    if not producto_refs:
        return {}

    query = (
        db.query(Oferta, Vendedor, ProductoVarianteReferencia)
        .join(Vendedor, Vendedor.id == Oferta.vendedor_id)
        .join(
            ProductoVarianteReferencia,
            ProductoVarianteReferencia.id == Oferta.producto_variante_id,
        )
        .filter(Oferta.producto_ref.in_(producto_refs))
    )
    if solo_activas:
        query = query.filter(Oferta.estado == 'activa')

    rows = query.all()
    offer_ids = [offer.id for offer, _, _ in rows]
    stocks = stock_by_offer(db, offer_ids)
    grouped = defaultdict(list)
    for offer, vendor, variant in rows:
        available = stocks.get(offer.id, 0)
        grouped[offer.producto_ref].append({
            'id': offer.id,
            'oferta_id': offer.id,
            'producto_ref': offer.producto_ref,
            'producto_variante_id': offer.producto_variante_id,
            'variante_ref': variant.variante_ref,
            'sku': offer.sku,
            'precio': float(offer.precio_actual),
            'moneda': offer.moneda,
            'estado': offer.estado,
            'version': offer.version,
            'vendedor_id': offer.vendedor_id,
            'vendedor_usuario_id': vendor.usuario_id,
            'vendedor_nombre': vendor.nombre_comercial,
            'es_tiendaya': vendor.es_tiendaya,
            'stock': available,
            'disponible': offer.estado == 'activa' and available > 0,
        })

    for offers in grouped.values():
        # TiendaYa disponible primero → demás disponibles por precio → no disponibles
        offers.sort(key=lambda o: (
            not (o['es_tiendaya'] and o['disponible']),
            not o['disponible'],
            o['precio'],
            o['oferta_id'],
        ))
    return dict(grouped)


# La oferta principal sigue siendo el primer elemento de la lista (ya ordenada con TiendaYa primero)
def oferta_principal(offers: list[dict]) -> dict | None:
    return offers[0] if offers else None


def enqueue_primary_offer_projection(
    db: Session, producto_ref: str, agregado_id: int
) -> None:
    """Proyecta en Mongo la oferta líder (TiendaYa o más barata) y el stock total."""
    offers = listar_ofertas_por_referencias(db, [producto_ref]).get(
        producto_ref, []
    )
    primary = oferta_principal(offers)
    # Stock total = suma de todas las ofertas activas, no solo la principal
    stock_total = sum(o['stock'] for o in offers)
    projection = {
        'ofertas_count': len(offers),
        'oferta_id': primary['oferta_id'] if primary else None,
        'disponible': bool(primary and primary['disponible']),
        'stock': stock_total,
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


# Verifica que la oferta exista y esté en estado 'activa'; usada por carrito y checkout
def resolver_oferta_comprable(
    db: Session,
    *,
    oferta_id: int,
) -> Oferta:
    offer = db.query(Oferta).filter_by(id=oferta_id, estado='activa').first()
    if not offer:
        raise LookupError('No existe una oferta activa para el producto solicitado.')
    return offer
