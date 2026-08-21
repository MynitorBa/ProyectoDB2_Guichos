"""
Servicio de checkout que ejecuta el flujo de compra como transacción atómica.
Implementa lo mismo que sp_crear_pedido pero desde Python/SQLAlchemy,
para poder hacer pruebas unitarias y de concurrencia directamente.
"""
from decimal import Decimal

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models.inventario import Inventario, MovimientoInventario
from app.models.pedido import Pedido, PedidoLinea
from app.models.pago import Pago
from app.models.producto import Producto
from app.models.direccion import Direccion
from app.models.usuario import Usuario
from app.schemas.checkout import CheckoutItem


IVA = Decimal('0.12')


class CheckoutError(Exception):
    def __init__(self, message: str, code: str = 'CHECKOUT_ERROR'):
        self.message = message
        self.code = code
        super().__init__(message)


def procesar_checkout(
    db: Session,
    usuario_id: int,
    direccion_id: int,
    metodo_pago_id: int,
    items: list[CheckoutItem],
) -> Pedido:
    """
    Ejecuta el checkout dentro de una transacción explícita con bloqueos pesimistas.
    Lanza CheckoutError si hay stock insuficiente o datos inválidos.
    """
    if not items:
        raise CheckoutError('El carrito está vacío.', 'EMPTY_CART')

    # Validar usuario activo
    usuario = db.get(Usuario, usuario_id)
    if not usuario or usuario.estado != 'activo':
        raise CheckoutError('Usuario no válido.', 'INVALID_USER')

    # Validar dirección pertenece al usuario
    direccion = db.get(Direccion, direccion_id)
    if not direccion or direccion.usuario_id != usuario_id or not direccion.activa:
        raise CheckoutError('Dirección no válida para este usuario.', 'INVALID_ADDRESS')

    producto_ids = [item.producto_id for item in items]
    cantidad_por_producto = {item.producto_id: item.cantidad for item in items}

    # SELECT FOR UPDATE: bloquea las filas de inventario para evitar sobreventa
    # en compras concurrentes sobre el mismo stock.
    inventarios = (
        db.execute(
            select(Inventario)
            .where(Inventario.producto_id.in_(producto_ids))
            .where(Inventario.bodega == 'principal')
            .with_for_update()
        )
        .scalars()
        .all()
    )

    inventario_map: dict[int, Inventario] = {inv.producto_id: inv for inv in inventarios}

    # Verificar stock para cada producto
    for producto_id, cantidad in cantidad_por_producto.items():
        inv = inventario_map.get(producto_id)
        if inv is None:
            raise CheckoutError(
                f'Producto id={producto_id} no tiene inventario registrado.',
                'NO_INVENTORY'
            )
        if inv.cantidad_disponible < cantidad:
            raise CheckoutError(
                f'Stock insuficiente para producto id={producto_id}. '
                f'Disponible: {inv.cantidad_disponible}, solicitado: {cantidad}',
                'INSUFFICIENT_STOCK'
            )

    # Cargar datos de productos para congelar precio y nombre
    productos: dict[int, Producto] = {}
    for prod_id in producto_ids:
        prod = db.get(Producto, prod_id)
        if not prod:
            raise CheckoutError(f'Producto id={prod_id} no encontrado.', 'PRODUCT_NOT_FOUND')
        productos[prod_id] = prod

    # Calcular subtotal
    subtotal = Decimal('0')
    for item in items:
        prod = productos[item.producto_id]
        subtotal += prod.precio * item.cantidad

    impuestos = (subtotal * IVA).quantize(Decimal('0.01'))
    total = subtotal + impuestos

    # Crear pedido
    pedido = Pedido(
        usuario_id=usuario_id,
        direccion_id=direccion_id,
        estado='confirmado',
        subtotal=subtotal,
        impuestos=impuestos,
        total=total,
    )
    db.add(pedido)
    db.flush()  # Obtener el id del pedido antes de commit

    # Crear líneas, descontar inventario, registrar movimientos
    for item in items:
        prod = productos[item.producto_id]
        subtotal_linea = prod.precio * item.cantidad

        linea = PedidoLinea(
            pedido_id=pedido.id,
            producto_id=item.producto_id,
            producto_ref=prod.producto_ref,
            producto_nombre=prod.nombre,
            precio_unitario=prod.precio,
            cantidad=item.cantidad,
            subtotal_linea=subtotal_linea,
        )
        db.add(linea)

        # Descontar inventario
        inv = inventario_map[item.producto_id]
        inv.cantidad_disponible -= item.cantidad

        # Movimiento de salida
        mov = MovimientoInventario(
            producto_id=item.producto_id,
            tipo='salida',
            cantidad=item.cantidad,
            motivo='venta',
            pedido_id=pedido.id,
            usuario_id=usuario_id,
        )
        db.add(mov)

    # Registrar pago
    referencia = f"TXN-{pedido.id:08d}-{int(total * 100)}"
    pago = Pago(
        pedido_id=pedido.id,
        metodo_pago_id=metodo_pago_id,
        monto=total,
        estado='aprobado',
        referencia_transaccion=referencia,
    )
    db.add(pago)

    db.commit()
    db.refresh(pedido)
    return pedido
