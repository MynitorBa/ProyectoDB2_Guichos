"""Envíos por cantidad. Toda escritura bloquea primero el pedido global.

El inventario ya se descuenta en checkout: despachar no lo vuelve a descontar.
"""
from datetime import timezone
from fastapi import HTTPException
from sqlalchemy.orm import Session
from app.core.time import utc_now
from app.models.pedido import Pedido, PedidoLinea
from app.models.pedido_vendedor import PedidoVendedor, PedidoDireccion
from app.models.pedido_envio import PedidoEnvio, PedidoEnvioLinea
from app.models.vendedor import Vendedor
from app.models.notificacion import Notificacion

TERMINAL = {'cancelado', 'reembolsado'}


def progress_state(total, sent, delivered, fallback='confirmado'):
    if total and delivered >= total:
        return 'entregado'
    if delivered:
        return 'entregado_parcial'
    if total and sent >= total:
        return 'enviado'
    if sent:
        return 'enviado_parcial'
    return fallback


def order_access(db, order_id, user, *, write=False):
    query = db.query(Pedido).filter_by(id=order_id)
    order = query.populate_existing().with_for_update().first() if write else query.first()
    if not order:
        raise HTTPException(404, 'Pedido no encontrado.')
    roles = {role.nombre for role in user.roles}
    if 'administrador' in roles or (not write and order.usuario_id == user.id):
        return order, None
    if 'vendedor' in roles:
        vendor = db.query(Vendedor).filter_by(usuario_id=user.id).first()
        if vendor and db.query(PedidoVendedor).filter_by(
            pedido_id=order.id, vendedor_id=vendor.id
        ).first():
            return order, vendor.id
    raise HTTPException(404, 'Pedido no encontrado o sin permiso.')


def quantities(db, part_id, *, lock=False):
    result = {}
    query = db.query(PedidoEnvioLinea, PedidoEnvio).join(
        PedidoEnvio, PedidoEnvio.id == PedidoEnvioLinea.envio_id
    ).filter(PedidoEnvio.pedido_vendedor_id == part_id)
    rows = query.populate_existing().with_for_update().all() if lock else query.all()
    for line, shipment in rows:
        counts = result.setdefault(line.pedido_linea_id, [0, 0])
        counts[0] += line.cantidad
        if shipment.estado == 'entregado':
            counts[1] += line.cantidad
    return result


def recalculate(db, order):
    db.flush()
    parts = db.query(PedidoVendedor).filter_by(pedido_id=order.id).populate_existing().with_for_update().all()
    total = sent = delivered = 0
    active = [p for p in parts if p.estado not in TERMINAL]
    for part in active:
        lines = db.query(PedidoLinea).filter_by(pedido_vendedor_id=part.id).all()
        counts = quantities(db, part.id, lock=True)
        n = sum(l.cantidad for l in lines)
        s = sum(counts.get(l.id, [0, 0])[0] for l in lines)
        d = sum(counts.get(l.id, [0, 0])[1] for l in lines)
        fallback = part.estado if part.estado in {'pendiente', 'confirmado', 'preparando'} else 'confirmado'
        part.estado = progress_state(n, s, d, fallback)
        total += n
        sent += s
        delivered += d
    if order.estado not in TERMINAL:
        fallback = ('preparando' if any(p.estado == 'preparando' for p in active)
                    else 'pendiente' if active and all(p.estado == 'pendiente' for p in active)
                    else 'confirmado')
        order.estado = progress_state(total, sent, delivered, fallback)
    db.flush()


def _part(db, order, part_id, vendor_id):
    part = db.query(PedidoVendedor).filter_by(id=part_id, pedido_id=order.id).populate_existing().with_for_update().first()
    if not part or (vendor_id is not None and part.vendedor_id != vendor_id):
        raise HTTPException(404, 'Subpedido no encontrado o sin permiso.')
    if order.estado in TERMINAL or part.estado in TERMINAL:
        raise HTTPException(409, 'No se puede operar un pedido cancelado o reembolsado.')
    return part


def create_shipment(db, order_id, part_id, user, lines, reference=None):
    order, vendor_id = order_access(db, order_id, user, write=True)
    part = _part(db, order, part_id, vendor_id)
    if part.estado == 'pendiente':
        raise HTTPException(409, 'El subpedido todavía no está confirmado.')
    ids = [line['pedido_linea_id'] for line in lines]
    if not lines or len(set(ids)) != len(ids):
        raise HTTPException(422, 'Selecciona líneas únicas y cantidades positivas.')
    ordered = {line.id: line for line in db.query(PedidoLinea).filter_by(
        pedido_vendedor_id=part.id
    ).all()}
    counts = quantities(db, part.id, lock=True)
    for line in lines:
        original = ordered.get(line['pedido_linea_id'])
        amount = line['cantidad']
        if not original or not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0:
            raise HTTPException(422, 'Línea o cantidad inválida para este vendedor.')
        if amount > original.cantidad - counts.get(original.id, [0, 0])[0]:
            raise HTTPException(409, 'La cantidad supera las unidades pendientes de envío.')
    shipment = PedidoEnvio(
        pedido_vendedor_id=part.id, estado='enviado', referencia=reference,
        creado_por=user.id, fecha_envio=utc_now(),
    )
    db.add(shipment)
    db.flush()
    for line in lines:
        db.add(PedidoEnvioLinea(envio_id=shipment.id, **line))
    recalculate(db, order)
    db.add(Notificacion(usuario_id=order.usuario_id, tipo='pedido',
        titulo=f'Nuevo envío del pedido #{order.id}',
        mensaje=f'Se despachó el envío #{shipment.id}. Consulta las cantidades en tu pedido.'))
    db.commit()
    return shipment.id


def deliver_shipment(db, order_id, shipment_id, user):
    order, vendor_id = order_access(db, order_id, user, write=True)
    shipment = db.query(PedidoEnvio).filter_by(id=shipment_id).populate_existing().with_for_update().first()
    if not shipment:
        raise HTTPException(404, 'Envío no encontrado.')
    _part(db, order, shipment.pedido_vendedor_id, vendor_id)
    if shipment.estado == 'entregado':
        return  # Repetir la confirmación no duplica cantidades ni notificaciones.
    shipment.estado = 'entregado'
    shipment.fecha_entrega = utc_now()
    shipment.entregado_por = user.id
    recalculate(db, order)
    db.add(Notificacion(usuario_id=order.usuario_id, tipo='pedido',
        titulo=f'Entrega del pedido #{order.id}',
        mensaje=f'El envío #{shipment.id} fue marcado como entregado. Estado del pedido: {order.estado}.'))
    db.commit()


def prepare_part(db, order_id, part_id, user):
    order, vendor_id = order_access(db, order_id, user, write=True)
    part = _part(db, order, part_id, vendor_id)
    if part.estado not in {'confirmado', 'preparando'}:
        raise HTTPException(409, 'Solo un subpedido confirmado puede pasar a preparación.')
    part.estado = 'preparando'
    recalculate(db, order)
    db.commit()


def admin_status(db, order_id, user, target):
    """Cancelación previa al envío y devolución del pago SIMULADO del proyecto."""
    if 'administrador' not in {r.nombre for r in user.roles}:
        raise HTTPException(403, 'Solo el administrador puede cancelar o reembolsar.')
    order, _ = order_access(db, order_id, user, write=True)
    parts = db.query(PedidoVendedor).filter_by(pedido_id=order.id).with_for_update().all()
    if target == order.estado and target in TERMINAL:
        return  # No duplica reposiciones ni reembolsos.
    if target == 'confirmado':
        if order.estado != 'pendiente':
            raise HTTPException(409, 'Solo se puede confirmar un pedido pendiente.')
    elif target == 'cancelado':
        if order.estado not in {'confirmado', 'preparando'} or db.query(PedidoEnvio).filter(
            PedidoEnvio.pedido_vendedor_id.in_([p.id for p in parts])).first():
            raise HTTPException(409, 'Solo se puede cancelar antes del primer envío; las devoluciones requieren otro flujo.')
        from app.models.oferta import Oferta
        from app.models.inventario import Inventario, MovimientoInventario
        from app.services.offer_history_service import registrar_saldo_inventario
        from app.services.offer_service import enqueue_primary_offer_projection
        lines = db.query(PedidoLinea).filter_by(pedido_id=order.id).order_by(PedidoLinea.oferta_id).all()
        for line in lines:
            offer = db.query(Oferta).filter_by(id=line.oferta_id).populate_existing().with_for_update().one()
            inventory = db.query(Inventario).filter_by(oferta_id=offer.id, bodega='principal').populate_existing().with_for_update().one()
            inventory.cantidad_disponible += line.cantidad
            offer.version += 1
            db.add(MovimientoInventario(inventario_id=inventory.id, tipo='entrada',
                cantidad=line.cantidad, motivo='Cancelación previa al envío', pedido_id=order.id, usuario_id=user.id))
            registrar_saldo_inventario(db, inventario=inventory, usuario_id=user.id, motivo=f'Cancelación del pedido #{order.id}')
            db.flush()
            enqueue_primary_offer_projection(db, offer.producto_ref, offer.id)
    elif target == 'reembolsado':
        if order.estado != 'cancelado':
            raise HTTPException(409, 'Primero cancela el pedido sin envíos. No se gestionan devoluciones posteriores a la entrega aquí.')
        if not any(p.estado == 'aprobado' for p in order.pagos):
            raise HTTPException(409, 'No hay un pago aprobado que se pueda reembolsar.')
        for payment in order.pagos:
            if payment.estado == 'aprobado':
                payment.estado = 'reembolsado'
    else:
        raise HTTPException(409, 'Utiliza los botones de preparación y envío del subpedido; el estado global es calculado.')
    order.estado = target
    for part in parts:
        part.estado = target
    db.add(Notificacion(usuario_id=order.usuario_id, tipo='pedido', titulo=f'Pedido #{order.id} {target}',
        mensaje='Actualización administrativa del pedido. Los pagos de esta aplicación son simulados.'))
    db.commit()


def _iso(date):
    return date.replace(tzinfo=timezone.utc).isoformat() if date else None


def detail(db, order_id, user):
    order, vendor_id = order_access(db, order_id, user)
    query = db.query(PedidoVendedor).filter_by(pedido_id=order.id)
    if vendor_id is not None:
        query = query.filter_by(vendedor_id=vendor_id)
    parts = []
    for part in query.order_by(PedidoVendedor.id).all():
        counts = quantities(db, part.id)
        lines = db.query(PedidoLinea).filter_by(pedido_vendedor_id=part.id).all()
        vendor = db.get(Vendedor, part.vendedor_id)
        shipments = db.query(PedidoEnvio).filter_by(pedido_vendedor_id=part.id).order_by(PedidoEnvio.id).all()
        parts.append({
            'id': part.id, 'vendedor_id': part.vendedor_id,
            'vendedor_nombre': vendor.nombre_comercial if vendor else 'Vendedor',
            'estado': part.estado, 'subtotal': float(part.subtotal),
            'lineas': [{
                'id': l.id, 'producto_nombre': l.producto_nombre,
                'producto_ref': l.producto_ref, 'sku': l.sku_snapshot,
                'cantidad': l.cantidad, 'precio': float(l.precio_unitario),
                'subtotal': float(l.subtotal_linea),
                'enviado': counts.get(l.id, [0, 0])[0],
                'entregado': counts.get(l.id, [0, 0])[1],
                'pendiente_envio': l.cantidad - counts.get(l.id, [0, 0])[0],
            } for l in lines],
            'envios': [{
                'id': s.id, 'estado': s.estado, 'referencia': s.referencia,
                'fecha_envio': _iso(s.fecha_envio), 'fecha_entrega': _iso(s.fecha_entrega),
                'legado': s.legado,
                'lineas': [{'pedido_linea_id': l.pedido_linea_id, 'cantidad': l.cantidad}
                    for l in db.query(PedidoEnvioLinea).filter_by(envio_id=s.id).all()],
            } for s in shipments],
        })
    address = db.get(PedidoDireccion, order.id)
    return {
        'id': order.id, 'estado': order.estado, 'fecha': _iso(order.fecha_creacion),
        'comprador': {'nombre': f'{order.usuario.nombre} {order.usuario.apellido}'},
        'total': float(order.total) if vendor_id is None else sum(p['subtotal'] for p in parts),
        'vista_vendedor': vendor_id is not None,
        'puede_confirmar': 'administrador' in {r.nombre for r in user.roles} and order.estado == 'pendiente',
        'puede_cancelar': 'administrador' in {r.nombre for r in user.roles}
            and order.estado in {'confirmado', 'preparando'} and all(not p['envios'] for p in parts),
        'puede_reembolsar': 'administrador' in {r.nombre for r in user.roles}
            and order.estado == 'cancelado' and any(p.estado == 'aprobado' for p in order.pagos),
        'subtotal': float(order.subtotal) if vendor_id is None else None,
        'impuestos': float(order.impuestos) if vendor_id is None else None,
        'pagos': [{'estado': p.estado, 'monto': float(p.monto), 'referencia': p.referencia_transaccion}
            for p in order.pagos] if vendor_id is None else [],
        'puede_gestionar': any(r.nombre in {'administrador', 'vendedor'} for r in user.roles)
            and ('administrador' in {r.nombre for r in user.roles} or vendor_id is not None),
        'direccion': {key: getattr(address, key) for key in (
            'receptor_nombre', 'receptor_telefono', 'pais', 'departamento', 'municipio', 'linea1', 'linea2'
        )} if address else None,
        'subpedidos': parts,
    }
