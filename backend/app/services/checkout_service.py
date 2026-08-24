"""Checkout transaccional cuya identidad comprable es la oferta MySQL."""

from collections import defaultdict
from decimal import Decimal

from bson import ObjectId
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.carrito import Carrito, CarritoItem
from app.models.direccion import Direccion
from app.models.inventario import Inventario, MovimientoInventario
from app.models.oferta import Oferta
from app.models.pago import Pago
from app.models.pedido import Pedido, PedidoLinea
from app.models.pedido_vendedor import PedidoDireccion, PedidoVendedor
from app.models.usuario import Usuario
from app.models.vendedor import Vendedor
from app.schemas.checkout import CheckoutItem
from app.services.offer_service import resolver_oferta_comprable
from app.services.outbox_service import enqueue_outbox

IVA = Decimal('0.12')


class CheckoutError(Exception):
    def __init__(self, message: str, code: str = 'CHECKOUT_ERROR'):
        self.message = message
        self.code = code
        super().__init__(message)


def procesar_checkout(
    db: Session,
    mongo_db=None,
    *,
    usuario_id: int,
    direccion_id: int,
    metodo_pago_id: int,
    items: list[CheckoutItem],
) -> Pedido:
    """Bloquea oferta e inventario y crea el pedido completo atómicamente."""
    if not items:
        raise CheckoutError('El carrito está vacío.', 'EMPTY_CART')

    usuario = db.get(Usuario, usuario_id)
    if not usuario or usuario.estado != 'activo':
        raise CheckoutError('Usuario no válido.', 'INVALID_USER')

    direccion = db.get(Direccion, direccion_id)
    if not direccion or direccion.usuario_id != usuario_id or not direccion.activa:
        raise CheckoutError('Dirección no válida para este usuario.', 'INVALID_ADDRESS')

    quantities = defaultdict(int)
    for item in items:
        if item.cantidad < 1:
            raise CheckoutError('La cantidad debe ser positiva.', 'INVALID_QUANTITY')
        try:
            offer = resolver_oferta_comprable(db, oferta_id=item.oferta_id)
        except LookupError as exc:
            raise CheckoutError(str(exc), 'OFFER_NOT_FOUND') from exc
        quantities[offer.id] += item.cantidad

    offer_ids = sorted(quantities)
    locked_offers = (
        db.execute(
            select(Oferta)
            .where(Oferta.id.in_(offer_ids))
            .where(Oferta.estado == 'activa')
            .order_by(Oferta.id)
            .with_for_update()
        )
        .scalars()
        .all()
    )
    offers = {offer.id: offer for offer in locked_offers}
    if len(offers) != len(offer_ids):
        raise CheckoutError('Una oferta dejó de estar disponible.', 'OFFER_NOT_FOUND')

    inventories = (
        db.execute(
            select(Inventario)
            .where(Inventario.oferta_id.in_(offer_ids))
            .where(Inventario.bodega == 'principal')
            .order_by(Inventario.oferta_id)
            .with_for_update()
        )
        .scalars()
        .all()
    )
    inventory_by_offer = {row.oferta_id: row for row in inventories}
    for offer_id, quantity in quantities.items():
        inventory = inventory_by_offer.get(offer_id)
        if inventory is None:
            raise CheckoutError(
                f'Oferta id={offer_id} no tiene inventario registrado.',
                'NO_INVENTORY',
            )
        available = inventory.cantidad_disponible - inventory.cantidad_reservada
        if available < quantity:
            raise CheckoutError(
                f'Stock insuficiente para oferta id={offer_id}. '
                f'Disponible: {available}, solicitado: {quantity}',
                'INSUFFICIENT_STOCK',
            )

    vendors = {
        vendor.id: vendor
        for vendor in db.query(Vendedor).filter(
            Vendedor.id.in_({offer.vendedor_id for offer in offers.values()})
        )
    }
    subtotal_by_vendor = defaultdict(lambda: Decimal('0'))
    subtotal = Decimal('0')
    for offer_id, quantity in quantities.items():
        offer = offers[offer_id]
        line_subtotal = offer.precio_actual * quantity
        subtotal += line_subtotal
        subtotal_by_vendor[offer.vendedor_id] += line_subtotal

    impuestos = (subtotal * IVA).quantize(Decimal('0.01'))
    total = subtotal + impuestos
    pedido = Pedido(
        usuario_id=usuario_id,
        direccion_id=direccion_id,
        estado='confirmado',
        subtotal=subtotal,
        impuestos=impuestos,
        total=total,
    )
    db.add(pedido)
    db.flush()

    vendor_orders = {}
    for vendor_id, vendor_subtotal in subtotal_by_vendor.items():
        part = PedidoVendedor(
            pedido_id=pedido.id,
            vendedor_id=vendor_id,
            estado='confirmado',
            subtotal=vendor_subtotal,
            costo_envio=Decimal('0'),
        )
        db.add(part)
        db.flush()
        vendor_orders[vendor_id] = part

    db.add(PedidoDireccion(
        pedido_id=pedido.id,
        receptor_nombre=f'{usuario.nombre} {usuario.apellido}'.strip(),
        receptor_telefono=usuario.telefono,
        pais=direccion.pais,
        departamento=direccion.departamento,
        municipio=direccion.municipio,
        linea1=direccion.linea1,
        linea2=direccion.linea2,
        codigo_postal=direccion.codigo_postal,
    ))

    for offer_id, quantity in quantities.items():
        offer = offers[offer_id]
        inventory = inventory_by_offer[offer_id]
        vendor = vendors[offer.vendedor_id]
        line_subtotal = offer.precio_actual * quantity
        product_name = offer.sku
        if mongo_db is not None and offer.producto_ref:
            try:
                mongo_product = mongo_db.productos.find_one(
                    {'_id': ObjectId(offer.producto_ref)}, {'nombre': 1}
                )
                if mongo_product and mongo_product.get('nombre'):
                    product_name = mongo_product['nombre']
            except Exception:
                pass

        db.add(PedidoLinea(
            pedido_id=pedido.id,
            pedido_vendedor_id=vendor_orders[offer.vendedor_id].id,
            oferta_id=offer.id,
            producto_ref=offer.producto_ref,
            sku_snapshot=offer.sku,
            producto_nombre=product_name,
            vendedor_nombre_snapshot=vendor.nombre_comercial,
            precio_unitario=offer.precio_actual,
            cantidad=quantity,
            subtotal_linea=line_subtotal,
        ))

        inventory.cantidad_disponible -= quantity
        projected_stock = max(0, inventory.cantidad_disponible)
        enqueue_outbox(
            db,
            tipo_evento='inventario.actualizado',
            agregado_tipo='pedido',
            agregado_id=pedido.id,
            producto_ref=offer.producto_ref,
            payload={
                'oferta_id': offer.id,
                'pedido_id': pedido.id,
                'projection': {
                    'stock': projected_stock,
                    'disponible': projected_stock > 0,
                },
                'history': {
                    'tipo_evento': 'DISPONIBILIDAD_CAMBIADA',
                    'datos_anteriores': {},
                    'datos_nuevos': {
                        'stock': projected_stock,
                        'disponible': projected_stock > 0,
                    },
                    'usuario_id': str(usuario_id),
                },
            },
        )
        db.add(MovimientoInventario(
            inventario_id=inventory.id,
            tipo='salida',
            cantidad=quantity,
            motivo='venta',
            pedido_id=pedido.id,
            usuario_id=usuario_id,
        ))

    db.add(Pago(
        pedido_id=pedido.id,
        metodo_pago_id=metodo_pago_id,
        monto=total,
        estado='aprobado',
        referencia_transaccion=f'TXN-{pedido.id:08d}-{int(total * 100)}',
    ))
    cart = db.query(Carrito).filter_by(usuario_id=usuario_id, estado='activo').first()
    if cart:
        db.query(CarritoItem).filter_by(carrito_id=cart.id).delete()

    db.commit()

    db.refresh(pedido)
    return pedido
