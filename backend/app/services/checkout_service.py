"""Checkout como saga orquestada: MySQL + pasarela de pagos externa.

La pasarela es un sistema independiente: no comparte transacción con MySQL,
puede tardar, fallar a medias o cobrar sin poder avisar. Por eso el checkout
se divide en pasos, cada uno con su propia transacción y su acción
compensatoria:

1. ``reservar_pedido`` (T1, MySQL): valida precios, bloquea ofertas e
   inventario, crea el pedido ``pendiente`` y **reserva** el stock
   (``cantidad_reservada``) sin descontarlo. Commit: no se retienen bloqueos
   mientras se espera a la pasarela.
2. ``cobrar_pedido`` (fuera de transacción): solicita el cargo con la clave
   idempotente del pago; los reintentos nunca cobran dos veces.
3. ``aplicar_resultado_cobro`` (T2, MySQL), según la respuesta:
   - aprobado     → ``confirmar_pedido``: descuenta stock, aprueba el pago y
                    encola las proyecciones en el outbox.
   - rechazado    → ``compensar_pedido``: libera la reserva y cancela.
   - no enviado   → ``compensar_pedido``: la pasarela nunca recibió la
                    solicitud, así que no hubo cargo.
   - desconocido  → ``marcar_en_verificacion``: pudo haberse cobrado; el pedido
                    conserva la reserva y el reconciliador lo resuelve.
   - aprobado pero ya no se puede cumplir (p. ej. venció la reserva flash)
                  → ``reembolsar_y_cancelar``: compensación del cargo.

Todas las transiciones están protegidas por estado (``pendiente`` →
``confirmado`` | ``cancelado``) con el pedido bloqueado: ejecutarlas dos veces
no tiene efecto. Cada transición queda en ``checkout_saga_pasos``.
"""

import hashlib
import json
import logging
import uuid
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from bson import ObjectId
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.fault_injection import FallaSimulada, punto_de_falla
from app.core.time import utc_now
from app.models.checkout_saga import CheckoutSagaPaso
from app.models.direccion import Direccion
from app.models.inventario import Inventario, MovimientoInventario
from app.models.notificacion import Notificacion
from app.models.oferta import Oferta
from app.models.pago import MetodoPago, Pago
from app.models.pedido import Pedido, PedidoLinea
from app.models.pedido_vendedor import PedidoDireccion, PedidoVendedor
from app.models.promocion_flash import PromocionFlash, ReservaFlash
from app.models.usuario import Usuario
from app.models.vendedor import Vendedor
from app.schemas.checkout import CheckoutItem
from app.services import payment_gateway_client as pg
from app.services.offer_history_service import registrar_saldo_inventario
from app.services.offer_service import resolver_oferta_comprable
from app.services.outbox_service import enqueue_outbox

logger = logging.getLogger(__name__)
IVA = Decimal('0.12')

# Desenlaces de aplicar el resultado del cobro.
CONFIRMADO = 'confirmado'
RECHAZADO = 'rechazado'
NO_ENVIADO = 'no_enviado'
EN_VERIFICACION = 'en_verificacion'
REEMBOLSADO = 'reembolsado'
REEMBOLSO_PENDIENTE = 'reembolso_pendiente'


class CheckoutError(Exception):
    def __init__(self, message: str, code: str = 'CHECKOUT_ERROR', pedido_id: int | None = None):
        self.message = message
        self.code = code
        self.pedido_id = pedido_id
        super().__init__(message)


class PedidoNoCumplible(Exception):
    """El cobro se aprobó pero el pedido ya no puede confirmarse."""


# ── Utilidades ────────────────────────────────────────────────────────────────

def huella_solicitud(items: list[CheckoutItem], direccion_id: int, metodo_pago_id: int) -> str:
    """Identifica el contenido de una solicitud para detectar claves reutilizadas."""
    cantidades = defaultdict(int)
    for item in items:
        cantidades[item.oferta_id] += item.cantidad
    contenido = {
        'items': sorted(cantidades.items()),
        'direccion_id': direccion_id,
        'metodo_pago_id': metodo_pago_id,
    }
    return hashlib.sha256(json.dumps(contenido, sort_keys=True).encode()).hexdigest()


def registrar_paso(db: Session, pedido_id: int, paso: str, resultado: str, detalle: dict | None = None) -> None:
    """Agrega una transición a la bitácora de la saga (sin commit)."""
    db.add(CheckoutSagaPaso(pedido_id=pedido_id, paso=paso, resultado=resultado, detalle=detalle))


def es_contra_entrega(db: Session, metodo_pago_id: int) -> bool:
    metodo = db.get(MetodoPago, metodo_pago_id)
    return bool(metodo and 'contra entrega' in metodo.nombre.lower())


def _pago_de(db: Session, pedido_id: int) -> Pago:
    return db.execute(
        select(Pago).where(Pago.pedido_id == pedido_id).order_by(Pago.id).with_for_update()
    ).scalars().first()


def _bloquear_pedido(db: Session, pedido_id: int) -> Pedido:
    return db.execute(select(Pedido).where(Pedido.id == pedido_id).with_for_update()).scalar_one()


def _cantidades(pedido: Pedido) -> dict[int, int]:
    cantidades = defaultdict(int)
    for linea in pedido.lineas:
        cantidades[linea.oferta_id] += linea.cantidad
    return dict(cantidades)


def _bloquear_recursos(db: Session, pedido: Pedido, offer_ids: list[int]):
    """Bloquea en el mismo orden que la reserva (ofertas → flash → inventario).

    Mantener un único orden de bloqueo entre todos los pasos de la saga evita
    interbloqueos con checkouts concurrentes sobre las mismas ofertas.
    """
    offers = {
        o.id: o for o in db.execute(
            select(Oferta).where(Oferta.id.in_(offer_ids)).order_by(Oferta.id).with_for_update()
        ).scalars()
    }
    reservas = db.execute(
        select(ReservaFlash).where(ReservaFlash.pedido_id == pedido.id).with_for_update()
    ).scalars().all()
    flash: dict[int, tuple[PromocionFlash, ReservaFlash]] = {}
    for reserva in reservas:
        promocion = db.execute(
            select(PromocionFlash).where(PromocionFlash.id == reserva.promocion_id).with_for_update()
        ).scalar_one()
        flash[promocion.oferta_id] = (promocion, reserva)
    inventarios = {
        i.oferta_id: i for i in db.execute(
            select(Inventario)
            .where(Inventario.oferta_id.in_(offer_ids), Inventario.bodega == 'principal')
            .order_by(Inventario.oferta_id)
            .with_for_update()
        ).scalars()
    }
    return offers, flash, inventarios


def _encolar_inventario(db: Session, pedido_id: int, offer: Oferta) -> None:
    # MongoDB y el índice de búsqueda recalculan el stock total del producto
    # (todas sus ofertas) al procesar el evento; no se envía un delta parcial.
    enqueue_outbox(
        db,
        tipo_evento='inventario.actualizado',
        agregado_tipo='pedido',
        agregado_id=pedido_id,
        producto_ref=offer.producto_ref,
        payload={'oferta_id': offer.id, 'pedido_id': pedido_id},
    )


def _notificar_vendedores(db: Session, pedido: Pedido) -> None:
    """Una notificación por vendedor con productos en el pedido (sin commit)."""
    comprador = db.get(Usuario, pedido.usuario_id)
    partes = {p.id: p for p in db.query(PedidoVendedor).filter_by(pedido_id=pedido.id)}
    por_usuario: dict[int, list[PedidoLinea]] = {}
    for linea in pedido.lineas:
        parte = partes.get(linea.pedido_vendedor_id)
        vendedor = db.get(Vendedor, parte.vendedor_id) if parte else None
        if not vendedor or vendedor.usuario_id == comprador.id:
            continue
        por_usuario.setdefault(vendedor.usuario_id, []).append(linea)
    for usuario_id, lineas in por_usuario.items():
        productos = ', '.join(l.producto_nombre for l in lineas[:3])
        if len(lineas) > 3:
            productos += f' y {len(lineas) - 3} más'
        subtotal = sum(float(l.subtotal_linea) for l in lineas)
        db.add(Notificacion(
            usuario_id=usuario_id,
            tipo='venta_realizada',
            titulo=f'¡Nueva venta! Pedido #{pedido.id}',
            mensaje=(
                f'Productos vendidos: {productos}. Subtotal: Q{subtotal:.2f}. '
                f'Comprador: {comprador.nombre} {comprador.apellido}.'
            ),
            pedido_id=pedido.id,
        ))


MENSAJES_CANCELACION = {
    'pago_rechazado': 'La pasarela rechazó el pago. No se realizó ningún cargo y tus productos siguen en el carrito.',
    'pasarela_no_disponible': 'No pudimos contactar a la pasarela de pagos. No se realizó ningún cargo.',
    'pago_no_recibido': 'No se recibió el pago a tiempo; liberamos la reserva. No se realizó ningún cargo.',
    'pedido_no_cumplible': 'El pago se aprobó pero el pedido ya no se podía cumplir; el cargo fue reembolsado.',
}


# ── Paso 1: reservar (T1) ─────────────────────────────────────────────────────

def reservar_pedido(
    db: Session,
    mongo_db=None,
    *,
    usuario_id: int,
    direccion_id: int,
    metodo_pago_id: int,
    items: list[CheckoutItem],
    precios_esperados: dict[int, Decimal] | None = None,
    confirmar_cambios_precio: bool = False,
    precios_confirmados: dict[int, Decimal] | None = None,
    promociones_flash: dict[int, dict] | None = None,
    clave_idempotencia: str | None = None,
    huella: str | None = None,
) -> Pedido:
    """Valida, bloquea y crea el pedido ``pendiente`` reservando el inventario."""
    # Las ofertas e inventarios se bloquean con SELECT ... FOR UPDATE ordenados por id para evitar deadlocks
    if not items:
        raise CheckoutError('El carrito está vacío.', 'EMPTY_CART')

    usuario = db.get(Usuario, usuario_id)
    if not usuario or usuario.estado != 'activo':
        raise CheckoutError('Usuario no válido.', 'INVALID_USER')

    direccion = db.get(Direccion, direccion_id)
    if not direccion or direccion.usuario_id != usuario_id or not direccion.activa:
        raise CheckoutError('Dirección no válida para este usuario.', 'INVALID_ADDRESS')

    if not db.get(MetodoPago, metodo_pago_id):
        raise CheckoutError('Método de pago no válido.', 'INVALID_PAYMENT_METHOD')

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

    promociones_flash = promociones_flash or {}
    flash_context: dict[int, tuple[PromocionFlash, ReservaFlash]] = {}
    applied_prices = {offer_id: offer.precio_actual for offer_id, offer in offers.items()}
    now = utc_now()
    for offer_id, context in promociones_flash.items():
        if offer_id not in offers:
            raise CheckoutError('La oferta flash dejó de estar disponible.', 'OFFER_NOT_FOUND')
        promotion = db.execute(
            select(PromocionFlash).where(
                PromocionFlash.id == context['promocion_id']
            ).with_for_update()
        ).scalar_one_or_none()
        reservation = db.execute(
            select(ReservaFlash).where(
                ReservaFlash.token == context['token']
            ).with_for_update()
        ).scalar_one_or_none()
        if (
            not promotion or not reservation
            or promotion.oferta_id != offer_id
            or promotion.estado not in {'programada', 'activa'}
            or not (promotion.inicia_en <= now < promotion.finaliza_en)
            or reservation.promocion_id != promotion.id
            or reservation.usuario_id != usuario_id
            or reservation.estado != 'reservada'
            or reservation.expira_en <= now
            or reservation.cantidad != quantities[offer_id]
        ):
            raise CheckoutError('La reserva flash venció o no es válida.', 'FLASH_RESERVATION_INVALID')
        flash_context[offer_id] = (promotion, reservation)
        applied_prices[offer_id] = reservation.precio_unitario

    # El precio de Redis solo representa lo visto al agregar. MySQL sigue
    # siendo la autoridad y se compara después de bloquear las ofertas para
    # que el valor no cambie entre la validación y la creación del pedido.
    if precios_esperados is not None:
        cambios = [
            offer_id
            for offer_id, offer in offers.items()
            if precios_esperados.get(offer_id) != applied_prices[offer_id]
        ]
        precios_visibles_desactualizados = (
            precios_confirmados is not None
            and bool(precios_confirmados)
            and any(
                precios_confirmados.get(offer_id) != applied_prices[offer_id]
                for offer_id in offers
            )
        )
        if precios_visibles_desactualizados:
            raise CheckoutError(
                'Uno o más precios cambiaron. Revisa el total y confirma nuevamente.',
                'PRICE_CHANGED',
            )
        if cambios:
            confirmados_coinciden = (
                confirmar_cambios_precio
                and precios_confirmados is not None
                and all(offer_id in precios_confirmados for offer_id in offer_ids)
                and all(
                    precios_confirmados.get(offer_id) == applied_prices[offer_id]
                    for offer_id in offer_ids
                )
            )
            if not confirmados_coinciden:
                raise CheckoutError(
                    'Uno o más precios cambiaron. Revisa el total y confirma nuevamente.',
                    'PRICE_CHANGED',
                )

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
        if offer_id in flash_context:
            promotion, _ = flash_context[offer_id]
            available = min(
                inventory.cantidad_reservada,
                promotion.unidades_totales - promotion.unidades_vendidas,
            )
        else:
            available = inventory.cantidad_disponible - inventory.cantidad_reservada
        if available < quantity:
            raise CheckoutError(
                f'Stock insuficiente para oferta id={offer_id}. '
                f'Disponible: {available}, solicitado: {quantity}',
                'INSUFFICIENT_STOCK',
            )

    # Se agrupa el subtotal por vendedor para crear un PedidoVendedor independiente por cada uno
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
        line_subtotal = applied_prices[offer_id] * quantity
        subtotal += line_subtotal
        subtotal_by_vendor[offer.vendedor_id] += line_subtotal

    # Los precios ya incluyen IVA; se extrae la base imponible para el desglose contable
    total = subtotal
    base = (total / (Decimal('1') + IVA)).quantize(Decimal('0.01'))
    impuestos = total - base
    clave = clave_idempotencia or str(uuid.uuid4())
    pedido = Pedido(
        usuario_id=usuario_id,
        direccion_id=direccion_id,
        estado='pendiente',
        subtotal=base,
        impuestos=impuestos,
        total=total,
        clave_idempotencia=clave,
        huella_solicitud=huella,
        reserva_expira_en=now + timedelta(minutes=settings.CHECKOUT_RESERVA_MINUTOS),
    )
    db.add(pedido)
    # Una clave repetida falla aquí (UNIQUE) antes de tocar inventario.
    db.flush()

    vendor_orders = {}
    for vendor_id, vendor_subtotal in subtotal_by_vendor.items():
        part = PedidoVendedor(
            pedido_id=pedido.id,
            vendedor_id=vendor_id,
            estado='pendiente',
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
        line_subtotal = applied_prices[offer_id] * quantity
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
            precio_unitario=applied_prices[offer_id],
            cantidad=quantity,
            subtotal_linea=line_subtotal,
        ))

        if offer_id in flash_context:
            # Las unidades flash ya están apartadas en el cupo de la promoción;
            # se vincula la reserva al pedido sin consumirla todavía.
            _, reservation = flash_context[offer_id]
            reservation.pedido_id = pedido.id
        else:
            inventory.cantidad_reservada += quantity
            db.add(MovimientoInventario(
                inventario_id=inventory.id,
                tipo='reserva',
                cantidad=quantity,
                motivo=f'Reserva del pedido #{pedido.id}',
                pedido_id=pedido.id,
                usuario_id=usuario_id,
            ))
            registrar_saldo_inventario(
                db, inventario=inventory, usuario_id=usuario_id,
                motivo=f'Reserva del pedido #{pedido.id}',
            )
            # La reserva reduce el stock visible en el catálogo y el buscador.
            _encolar_inventario(db, pedido.id, offer)

    db.add(Pago(
        pedido_id=pedido.id,
        metodo_pago_id=metodo_pago_id,
        monto=total,
        estado='pendiente',
        clave_idempotencia=clave,
    ))
    registrar_paso(db, pedido.id, 'reserva', 'ok', {
        'ofertas': {str(k): v for k, v in quantities.items()},
        'total': str(total),
        'flash': sorted(flash_context),
    })
    db.commit()
    return pedido


# ── Paso 2: cobrar (fuera de transacción) ─────────────────────────────────────

def cobrar_pedido(db: Session, pedido_id: int, pasarela: 'pg.PasarelaPagos') -> 'pg.ResultadoPasarela':
    pago = db.execute(select(Pago).where(Pago.pedido_id == pedido_id).order_by(Pago.id)).scalars().first()
    monto, clave = pago.monto, pago.clave_idempotencia
    db.commit()  # no retener ningún bloqueo durante la llamada externa

    resultado = pasarela.cobrar(clave, monto, referencia=f'PED-{pedido_id:08d}')

    pago = _pago_de(db, pedido_id)
    pago.intentos += resultado.intentos
    pago.ultimo_error = '; '.join(resultado.detalle)[:4000] or None
    if resultado.referencia:
        pago.referencia_pasarela = resultado.referencia
    registrar_paso(db, pedido_id, 'cobro', resultado.estado, {
        'intentos': resultado.intentos,
        'referencia': resultado.referencia,
        'motivo': resultado.motivo,
        'detalle': resultado.detalle,
    })
    db.commit()
    return resultado


# ── Paso 3: confirmar, compensar o verificar (T2) ─────────────────────────────

def confirmar_pedido(db: Session, pedido_id: int, *, referencia: str | None = None, origen: str = 'checkout') -> Pedido:
    """Convierte la reserva en venta. Sin efecto si el pedido ya no está pendiente."""
    pedido = _bloquear_pedido(db, pedido_id)
    if pedido.estado != 'pendiente':
        db.commit()
        return pedido

    cantidades = _cantidades(pedido)
    offer_ids = sorted(cantidades)
    offers, flash, inventarios = _bloquear_recursos(db, pedido, offer_ids)

    for offer_id in offer_ids:
        cantidad = cantidades[offer_id]
        inventario = inventarios[offer_id]
        if offer_id in flash:
            promocion, reserva = flash[offer_id]
            if reserva.estado != 'reservada':
                db.rollback()
                raise PedidoNoCumplible(f'La reserva flash {reserva.token} está {reserva.estado}.')
            promocion.unidades_vendidas += cantidad
            reserva.estado = 'convertida'
            if promocion.unidades_vendidas >= promocion.unidades_totales:
                promocion.estado = 'finalizada'
            promocion.version += 1
        elif inventario.cantidad_reservada < cantidad or inventario.cantidad_disponible < cantidad:
            db.rollback()
            raise PedidoNoCumplible(f'La reserva de la oferta {offer_id} ya no existe.')
        inventario.cantidad_disponible -= cantidad
        inventario.cantidad_reservada -= cantidad
        offers[offer_id].version += 1  # Invalida ediciones de stock abiertas antes de la venta.
        db.add(MovimientoInventario(
            inventario_id=inventario.id,
            tipo='salida',
            cantidad=cantidad,
            motivo='venta_flash' if offer_id in flash else 'venta',
            pedido_id=pedido.id,
            usuario_id=pedido.usuario_id,
        ))
        registrar_saldo_inventario(
            db, inventario=inventario, usuario_id=pedido.usuario_id,
            motivo=f'Venta del pedido #{pedido.id}',
        )
        _encolar_inventario(db, pedido.id, offers[offer_id])

    pago = _pago_de(db, pedido.id)
    contra_entrega = es_contra_entrega(db, pago.metodo_pago_id)
    # Contra entrega: el pedido se confirma y el pago queda pendiente de cobro al entregar.
    pago.estado = 'pendiente' if contra_entrega else 'aprobado'
    if referencia:
        pago.referencia_pasarela = referencia
    pago.referencia_transaccion = referencia or f'TXN-{pedido.id:08d}-{int(pedido.total * 100)}'
    pedido.estado = 'confirmado'
    pedido.reserva_expira_en = None
    db.query(PedidoVendedor).filter_by(pedido_id=pedido.id).update({'estado': 'confirmado'})
    _notificar_vendedores(db, pedido)

    # Todo lo que ocurre fuera de MySQL se encola en esta misma transacción y
    # el worker del outbox lo aplica con reintentos idempotentes:
    # - Cassandra: proyección analítica de la venta (y el índice de búsqueda,
    #   que refleja las ventas en su ranking).
    # - Neo4j: nodos Compra pagados que habilitan reseñas verificadas.
    # - Redis: retirar del carrito lo comprado y cerrar reservas flash, como
    #   respaldo de la limpieza inmediata que intenta el endpoint.
    enqueue_outbox(db, tipo_evento='analytics.pedido_actualizado', agregado_tipo='pedido',
                   agregado_id=pedido.id, producto_ref=None, payload={'motivo': 'pago_aprobado'})
    enqueue_outbox(db, tipo_evento='grafo.compra_registrada', agregado_tipo='pedido',
                   agregado_id=pedido.id, producto_ref=None, payload={'usuario_id': pedido.usuario_id})
    enqueue_outbox(db, tipo_evento='carrito.limpiar', agregado_tipo='pedido', agregado_id=pedido.id,
                   producto_ref=None, payload={'usuario_id': pedido.usuario_id, 'oferta_ids': offer_ids})
    for promocion, reserva in flash.values():
        enqueue_outbox(db, tipo_evento='flash.consumir', agregado_tipo='pedido', agregado_id=pedido.id,
                       producto_ref=None, payload={
                           'promocion_id': promocion.id,
                           'usuario_id': pedido.usuario_id,
                           'token': reserva.token,
                       })
    registrar_paso(db, pedido.id, 'confirmacion', 'ok', {
        'origen': origen, 'referencia': referencia, 'contra_entrega': contra_entrega,
    })
    try:
        # La transacción de confirmación falla antes del commit: nada de lo
        # anterior queda escrito y el pedido sigue pendiente con su reserva.
        punto_de_falla('checkout.confirmacion')
    except FallaSimulada:
        db.rollback()
        raise
    db.commit()
    return pedido


def compensar_pedido(
    db: Session,
    pedido_id: int,
    motivo: str,
    *,
    estado_pago: str = 'rechazado',
    origen: str = 'checkout',
) -> Pedido:
    """Libera la reserva y cancela. Sin efecto si el pedido ya no está pendiente."""
    pedido = _bloquear_pedido(db, pedido_id)
    if pedido.estado != 'pendiente':
        db.commit()
        return pedido

    cantidades = _cantidades(pedido)
    offer_ids = sorted(cantidades)
    offers, flash, inventarios = _bloquear_recursos(db, pedido, offer_ids)
    for offer_id in offer_ids:
        if offer_id in flash:
            # La reserva flash sigue siendo del cliente mientras no venza:
            # puede reintentar el pago sin perder el precio promocional.
            _, reserva = flash[offer_id]
            reserva.pedido_id = None
            continue
        inventario = inventarios[offer_id]
        liberar = min(cantidades[offer_id], inventario.cantidad_reservada)
        inventario.cantidad_reservada -= liberar
        db.add(MovimientoInventario(
            inventario_id=inventario.id,
            tipo='liberacion',
            cantidad=liberar,
            motivo=f'Compensación del pedido #{pedido.id}: {motivo}'[:100],
            pedido_id=pedido.id,
            usuario_id=pedido.usuario_id,
        ))
        registrar_saldo_inventario(
            db, inventario=inventario, usuario_id=pedido.usuario_id,
            motivo=f'Reserva liberada del pedido #{pedido.id}',
        )
        _encolar_inventario(db, pedido.id, offers[offer_id])

    pago = _pago_de(db, pedido.id)
    pago.estado = estado_pago
    pedido.estado = 'cancelado'
    pedido.motivo_cancelacion = motivo
    pedido.reserva_expira_en = None
    db.query(PedidoVendedor).filter_by(pedido_id=pedido.id).update({'estado': 'cancelado'})
    db.add(Notificacion(
        usuario_id=pedido.usuario_id,
        tipo='pedido',
        titulo=f'Pedido #{pedido.id} cancelado',
        mensaje=MENSAJES_CANCELACION.get(motivo, 'El pedido fue cancelado.'),
        pedido_id=pedido.id,
    ))
    registrar_paso(db, pedido.id, 'compensacion', 'ok', {
        'motivo': motivo, 'estado_pago': estado_pago, 'origen': origen,
    })
    db.commit()
    return pedido


def marcar_en_verificacion(db: Session, pedido_id: int, detalle: dict | None = None) -> None:
    """El cobro pudo haberse hecho: se conserva la reserva hasta saberlo."""
    pago = _pago_de(db, pedido_id)
    if pago.estado in ('pendiente', 'en_verificacion'):
        pago.estado = 'en_verificacion'
        registrar_paso(db, pedido_id, 'verificacion', 'pendiente', detalle)
    db.commit()


def reembolsar_y_cancelar(db: Session, pedido_id: int, pasarela: 'pg.PasarelaPagos', razon: str) -> str:
    """Compensación del cargo: el cobro se aprobó pero el pedido no puede cumplirse."""
    clave = db.execute(select(Pago.clave_idempotencia).where(Pago.pedido_id == pedido_id)).scalar_one()
    db.commit()
    resultado = pasarela.reembolsar(clave)
    if resultado.estado == pg.REEMBOLSADO:
        compensar_pedido(db, pedido_id, 'pedido_no_cumplible', estado_pago='reembolsado')
        return REEMBOLSADO
    # Sin confirmación del reembolso: el pedido sigue en verificación y el
    # reconciliador lo reintentará (el reembolso también es idempotente).
    marcar_en_verificacion(db, pedido_id, {'reembolso': resultado.estado, 'razon': razon,
                                           'detalle': resultado.detalle})
    registrar_paso(db, pedido_id, 'reembolso', 'pendiente', {'razon': razon})
    db.commit()
    return REEMBOLSO_PENDIENTE


def aplicar_resultado_cobro(
    db: Session,
    pedido_id: int,
    resultado: 'pg.ResultadoPasarela',
    pasarela: 'pg.PasarelaPagos',
    origen: str = 'checkout',
) -> str:
    """Lleva el pedido al estado que corresponde a la respuesta de la pasarela."""
    if resultado.estado == pg.APROBADO:
        try:
            confirmar_pedido(db, pedido_id, referencia=resultado.referencia, origen=origen)
            return CONFIRMADO
        except PedidoNoCumplible as exc:
            logger.warning('Pedido #%d cobrado pero no cumplible: %s', pedido_id, exc)
            return reembolsar_y_cancelar(db, pedido_id, pasarela, str(exc))
    if resultado.estado == pg.RECHAZADO:
        compensar_pedido(db, pedido_id, 'pago_rechazado', origen=origen)
        return RECHAZADO
    if resultado.estado == pg.REEMBOLSADO:
        # Un reembolso previo ya se completó en la pasarela; falta cerrar el pedido.
        compensar_pedido(db, pedido_id, 'pedido_no_cumplible', estado_pago='reembolsado', origen=origen)
        return REEMBOLSADO
    if resultado.estado in (pg.NO_ENVIADO, pg.NO_ENCONTRADO):
        compensar_pedido(db, pedido_id, 'pasarela_no_disponible', origen=origen)
        return NO_ENVIADO
    marcar_en_verificacion(db, pedido_id, {'detalle': resultado.detalle, 'origen': origen})
    return EN_VERIFICACION


# ── Orquestación ──────────────────────────────────────────────────────────────

def procesar_checkout(
    db: Session,
    mongo_db=None,
    *,
    usuario_id: int,
    direccion_id: int,
    metodo_pago_id: int,
    items: list[CheckoutItem],
    precios_esperados: dict[int, Decimal] | None = None,
    confirmar_cambios_precio: bool = False,
    precios_confirmados: dict[int, Decimal] | None = None,
    promociones_flash: dict[int, dict] | None = None,
    clave_idempotencia: str | None = None,
    huella: str | None = None,
    pasarela: 'pg.PasarelaPagos | None' = None,
) -> Pedido:
    """Ejecuta la saga completa. Devuelve el pedido confirmado o lanza CheckoutError."""
    pedido = reservar_pedido(
        db, mongo_db,
        usuario_id=usuario_id,
        direccion_id=direccion_id,
        metodo_pago_id=metodo_pago_id,
        items=items,
        precios_esperados=precios_esperados,
        confirmar_cambios_precio=confirmar_cambios_precio,
        precios_confirmados=precios_confirmados,
        promociones_flash=promociones_flash,
        clave_idempotencia=clave_idempotencia,
        huella=huella,
    )
    pedido_id = pedido.id
    # Caída entre la reserva y el cobro: el recolector libera la reserva al vencer.
    punto_de_falla('checkout.despues_reserva')

    if es_contra_entrega(db, metodo_pago_id):
        pedido = confirmar_pedido(db, pedido_id, origen='contra_entrega')
        db.refresh(pedido)
        return pedido

    pasarela = pasarela or pg.get_pasarela()
    resultado = cobrar_pedido(db, pedido_id, pasarela)
    # Caída con el cargo hecho y sin confirmar: el recolector consulta la
    # pasarela con la misma clave y confirma sin volver a cobrar.
    punto_de_falla('checkout.despues_cobro')
    desenlace = aplicar_resultado_cobro(db, pedido_id, resultado, pasarela)
    if desenlace == CONFIRMADO:
        pedido = db.get(Pedido, pedido_id)
        db.refresh(pedido)
        return pedido
    if desenlace == RECHAZADO:
        raise CheckoutError(
            'Tu pago fue rechazado. No se realizó ningún cargo; tu carrito se conserva.',
            'PAYMENT_DECLINED', pedido_id,
        )
    if desenlace == NO_ENVIADO:
        raise CheckoutError(
            'La pasarela de pagos no está disponible. No se realizó ningún cargo; intenta de nuevo.',
            'PAYMENT_UNAVAILABLE', pedido_id,
        )
    if desenlace in (REEMBOLSADO, REEMBOLSO_PENDIENTE):
        raise CheckoutError(
            'El pago se aprobó, pero el pedido ya no se podía cumplir y el cargo se reembolsó.',
            'ORDER_NOT_FULFILLABLE', pedido_id,
        )
    raise CheckoutError(
        'Estamos verificando tu pago con la pasarela. Te avisaremos en cuanto se confirme.',
        'PAYMENT_PENDING', pedido_id,
    )
