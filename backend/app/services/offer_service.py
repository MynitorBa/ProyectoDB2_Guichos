"""Lectura transaccional de ofertas, vendedores e inventario desde MySQL."""

from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.inventario import Inventario
from app.models.oferta import Oferta, OfertaPrecioHistorial
from app.models.producto_variante_referencia import ProductoVarianteReferencia
from app.models.vendedor import Vendedor
from app.core.time import utc_now
from app.services.outbox_service import enqueue_outbox
from app.models.inventario import MovimientoInventario
from app.services.offer_history_service import registrar_estado_oferta, registrar_saldo_inventario
from fastapi import HTTPException


BODEGAS_COMPRABLES = ('principal', 'demo-principal')


def stock_comprable(inventarios) -> int:
    """Mayor cantidad que una sola bodega puede entregar, sin sumar saldos."""
    return max((max(0, row.cantidad_disponible - row.cantidad_reservada)
                for row in inventarios if row.bodega in BODEGAS_COMPRABLES), default=0)


def seleccionar_inventario(inventarios, cantidad: int):
    """Prioriza principal si cubre toda la línea; de lo contrario usa DEMO."""
    for bodega in BODEGAS_COMPRABLES:
        for row in inventarios:
            if (row.bodega == bodega
                    and row.cantidad_disponible - row.cantidad_reservada >= cantidad):
                return row
    return None


def inventario_operativo(inventarios):
    """Fila que se edita o presenta cuando no se solicitó cantidad concreta."""
    candidates = [row for row in inventarios if row.bodega in BODEGAS_COMPRABLES]
    return max(
        candidates,
        key=lambda row: (row.cantidad_disponible - row.cantidad_reservada,
                         row.bodega == 'principal'),
        default=None,
    )


def inventario_id_promocion(db: Session, promocion_id: int) -> int:
    """Identidad durable del cupo flash, registrada al crear la promoción."""
    rows = db.query(MovimientoInventario.inventario_id).filter(
        MovimientoInventario.tipo == 'reserva',
        MovimientoInventario.pedido_id.is_(None),
        MovimientoInventario.motivo == f'Promoción flash #{promocion_id}',
    ).all()
    if len(rows) != 1:
        raise LookupError(f'No se identificó el inventario de la promoción flash {promocion_id}.')
    return rows[0][0]


def inventario_promocion(db: Session, promocion, *, bloquear: bool = False):
    inventory_id = inventario_id_promocion(db, promocion.id)
    query = db.query(Inventario).filter_by(id=inventory_id, oferta_id=promocion.oferta_id)
    if bloquear:
        query = query.with_for_update()
    row = query.one_or_none()
    if row is None:
        raise LookupError(f'No existe el inventario reservado de la promoción flash {promocion.id}.')
    return row


def editar_oferta(db, *, oferta, usuario_id, precio=None, stock=None, estado=None,
                  version=None, motivo='Edición de oferta'):
    """El llamador bloquea Oferta antes de invocar. No hace commit."""
    if version is not None and oferta.version != version:
        raise HTTPException(409, 'La oferta cambió. Recarga antes de guardar.')
    if estado is not None and estado not in {'activa', 'pausada', 'descontinuada', 'borrador'}:
        raise HTTPException(422, 'Estado de oferta inválido.')
    inventories = db.query(Inventario).filter(
        Inventario.oferta_id == oferta.id,
        Inventario.bodega.in_(BODEGAS_COMPRABLES),
    ).order_by(Inventario.id).with_for_update().all()
    # Para una oferta histórica con solo demo-principal, editar esa misma fila.
    # Si hay dos bodegas, editar la que sustenta el stock anunciado; en empate
    # se conserva la prioridad de principal.
    inventory = inventario_operativo(inventories)
    if stock is not None:
        # Una edición del stock de la oferta no debe ocultar reservas que
        # sigan vivas en la bodega alternativa.
        reserved = max((row.cantidad_reservada for row in inventories), default=0)
        if stock < reserved:
            raise HTTPException(409, 'Las existencias no pueden ser menores que las unidades reservadas.')
    initial_version = oferta.version
    if precio is not None:
        actualizar_precio_oferta(db, oferta=oferta, nuevo_precio=precio,
            usuario_id=usuario_id, motivo=motivo, enqueue_projection=False)
    if stock is not None:
        old = inventory.cantidad_disponible if inventory else 0
        if not inventory:
            inventory = Inventario(oferta_id=oferta.id, bodega='principal', cantidad_disponible=0, cantidad_reservada=0)
            db.add(inventory)
        inventory.cantidad_disponible = stock
        db.flush()
        if stock != old:
            db.add(MovimientoInventario(inventario_id=inventory.id, tipo='ajuste',
                cantidad=stock-old, motivo=motivo[:100], usuario_id=usuario_id))
        registrar_saldo_inventario(db, inventario=inventory, usuario_id=usuario_id, motivo=motivo)
    if estado is not None:
        oferta.estado = estado
        registrar_estado_oferta(db, oferta=oferta, usuario_id=usuario_id, motivo=motivo)
    oferta.version = initial_version + 1
    db.flush()
    enqueue_primary_offer_projection(db, oferta.producto_ref, oferta.id)


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
    ).with_for_update().first()
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
    """Stock comprable por una sola bodega para cada oferta."""
    if not offer_ids:
        return {}
    rows = db.query(Inventario).filter(
        Inventario.oferta_id.in_(offer_ids),
        Inventario.bodega.in_(BODEGAS_COMPRABLES),
    ).all()
    by_offer = defaultdict(list)
    for row in rows:
        by_offer[row.oferta_id].append(row)
    return {offer_id: stock_comprable(inventories)
            for offer_id, inventories in by_offer.items()}


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


def proyeccion_oferta_principal(db: Session, producto_ref: str) -> dict:
    """Campos comerciales que MongoDB replica desde MySQL para un producto.

    Se calcula siempre desde el estado actual (oferta líder y stock total de
    todas las ofertas activas), por eso aplicarla es idempotente y no depende
    del orden en que lleguen los eventos.
    """
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
            'es_tiendaya': primary['es_tiendaya'],
        })
    return projection


def enqueue_primary_offer_projection(
    db: Session, producto_ref: str, agregado_id: int
) -> None:
    """Encola la proyección de la oferta líder hacia MongoDB y el índice de búsqueda."""
    enqueue_outbox(
        db,
        tipo_evento='producto.oferta_principal_actualizada',
        agregado_tipo='oferta',
        agregado_id=agregado_id,
        producto_ref=producto_ref,
        payload={'projection': proyeccion_oferta_principal(db, producto_ref)},
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
