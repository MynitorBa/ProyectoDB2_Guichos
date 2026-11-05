from decimal import Decimal
import uuid
import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session
from app.core.db_mysql import engine
from app.core.db_mongo import get_mongo_db
from app.models.usuario import Usuario
from app.models.vendedor import Vendedor
from app.models.pedido import Pedido, PedidoLinea
from app.models.pedido_vendedor import PedidoVendedor
from app.models.direccion import Direccion
from app.models.oferta import Oferta, OfertaPrecioHistorial
from app.models.inventario import Inventario, MovimientoInventario
from app.models.pago import Pago, MetodoPago
from app.api.v1.vendor import change_own_offer, VendorOfferUpdate
from app.api.v1.catalog_requests import propose_variant, approve_request, VariantProposalCreate, ReviewPayload
from app.services.fulfillment_service import (
    admin_status, create_shipment, deliver_shipment, detail, prepare_part, progress_state,
)


@pytest.fixture
def db():
    with engine.connect() as connection:
        transaction = connection.begin()
        session = Session(bind=connection, join_transaction_mode='create_savepoint')
        try:
            yield session
        finally:
            session.close()
            transaction.rollback()


def example_order(db):
    admin = db.query(Usuario).filter_by(email='admin@tiendaya.gt').one()
    address = db.query(Direccion).first()
    offers = db.query(Oferta).filter_by(estado='activa').all()
    first = offers[0]
    second = next(o for o in offers if o.vendedor_id != first.vendedor_id)
    order = Pedido(usuario_id=address.usuario_id, direccion_id=address.id,
        estado='confirmado', subtotal=70, impuestos=0, total=70)
    db.add(order)
    db.flush()
    parts, lines = [], []
    for offer, quantity in ((first, 5), (second, 2)):
        part = PedidoVendedor(pedido_id=order.id, vendedor_id=offer.vendedor_id,
            estado='confirmado', subtotal=quantity*10, costo_envio=0)
        db.add(part)
        db.flush()
        line = PedidoLinea(pedido_id=order.id, pedido_vendedor_id=part.id, oferta_id=offer.id,
            producto_ref=offer.producto_ref, sku_snapshot=offer.sku, producto_nombre='Prueba parcial',
            vendedor_nombre_snapshot='Prueba', cantidad=quantity, precio_unitario=10, subtotal_linea=quantity*10)
        db.add(line)
        db.flush()
        # Como en el checkout real: la venta deja un movimiento de salida en la bodega de la
        # que sale el stock (al cancelar se repone en esa misma fila).
        inventory = db.query(Inventario).filter_by(oferta_id=offer.id, bodega='principal').one()
        db.add(MovimientoInventario(inventario_id=inventory.id, tipo='salida', cantidad=quantity,
            motivo='Venta de prueba', pedido_id=order.id, usuario_id=admin.id))
        db.flush()
        parts.append(part)
        lines.append(line)
    db.add(Pago(
        pedido_id=order.id,
        metodo_pago_id=db.query(MetodoPago).first().id,
        monto=70,
        estado='aprobado',
    ))
    db.commit()
    return order, parts, lines, admin


@pytest.mark.parametrize('sent,delivered,expected', [(0,0,'confirmado'),(3,0,'enviado_parcial'),
    (5,0,'enviado'),(5,3,'entregado_parcial'),(5,5,'entregado')])
def test_quantity_state(sent, delivered, expected):
    assert progress_state(5, sent, delivered) == expected


def test_partial_shipments_and_permissions(db):
    order, parts, lines, admin = example_order(db)
    for payload in ([{'pedido_linea_id': lines[0].id, 'cantidad': 6}],
                    [{'pedido_linea_id': lines[0].id, 'cantidad': 1.5}],
                    [{'pedido_linea_id': lines[0].id, 'cantidad': 1}]*2,
                    [{'pedido_linea_id': lines[1].id, 'cantidad': 1}]):
        with pytest.raises(HTTPException):
            create_shipment(db, order.id, parts[0].id, admin, payload)
    vendor = db.get(Vendedor, parts[0].vendedor_id)
    user = db.get(Usuario, vendor.usuario_id)
    if not any(r.nombre == 'administrador' for r in user.roles):
        assert len(detail(db, order.id, user)['subpedidos']) == 1
        with pytest.raises(HTTPException):
            create_shipment(db, order.id, parts[1].id, user, [{'pedido_linea_id': lines[1].id, 'cantidad': 1}])
    first = create_shipment(db, order.id, parts[0].id, admin, [{'pedido_linea_id': lines[0].id, 'cantidad': 3}])
    assert order.estado == 'enviado_parcial'
    assert detail(db, order.id, admin)['subpedidos'][0]['lineas'][0]['pendiente_envio'] == 2
    deliver_shipment(db, order.id, first, admin)
    assert order.estado == 'entregado_parcial'
    second = create_shipment(db, order.id, parts[0].id, admin, [{'pedido_linea_id': lines[0].id, 'cantidad': 2}])
    deliver_shipment(db, order.id, second, admin)
    assert parts[0].estado == 'entregado' and order.estado != 'entregado'
    third = create_shipment(db, order.id, parts[1].id, admin, [{'pedido_linea_id': lines[1].id, 'cantidad': 2}])
    deliver_shipment(db, order.id, third, admin)
    deliver_shipment(db, order.id, third, admin)
    assert order.estado == 'entregado'


def test_vendor_offer_audit_version_and_ownership(db):
    vendor = db.query(Vendedor).filter_by(estado_verificacion='verificado').first()
    user = db.get(Usuario, vendor.usuario_id)
    offer = db.query(Oferta).filter_by(vendedor_id=vendor.id, estado='activa').first()
    inv = db.query(Inventario).filter_by(oferta_id=offer.id, bodega='principal').one()
    version = offer.version
    moves, prices = db.query(MovimientoInventario).count(), db.query(OfertaPrecioHistorial).count()
    change_own_offer(offer.id, VendorOfferUpdate(version=version,
        stock=inv.cantidad_disponible+3, precio=offer.precio_actual+Decimal('1.00')), user, db)
    assert db.query(MovimientoInventario).count() == moves+1
    assert db.query(OfertaPrecioHistorial).count() == prices+1
    with pytest.raises(HTTPException) as exc:
        change_own_offer(offer.id, VendorOfferUpdate(version=version, stock=1), user, db)
    assert exc.value.status_code == 409
    other = db.query(Oferta).filter(Oferta.vendedor_id != vendor.id).first()
    with pytest.raises(HTTPException) as exc:
        change_own_offer(other.id, VendorOfferUpdate(version=other.version, precio=1), user, db)
    assert exc.value.status_code == 404


def test_cancellation_restock_once_and_simulated_refund(db):
    order, parts, lines, admin = example_order(db)
    payment = db.query(Pago).filter_by(pedido_id=order.id).one()
    inventories = [db.query(Inventario).filter_by(oferta_id=l.oferta_id, bodega='principal').one() for l in lines]
    initial = [i.cantidad_disponible for i in inventories]
    db.commit()
    admin_status(db, order.id, admin, 'cancelado')
    admin_status(db, order.id, admin, 'cancelado')
    assert [i.cantidad_disponible for i in inventories] == [initial[0]+5, initial[1]+2]
    assert all(p.estado == 'cancelado' for p in parts)
    admin_status(db, order.id, admin, 'reembolsado')
    admin_status(db, order.id, admin, 'reembolsado')
    assert payment.estado == 'reembolsado'
    assert [i.cantidad_disponible for i in inventories] == [initial[0]+5, initial[1]+2]
    with pytest.raises(HTTPException):
        create_shipment(db, order.id, parts[0].id, admin, [{'pedido_linea_id': lines[0].id, 'cantidad': 1}])


def test_pending_card_payment_cannot_be_confirmed_or_dispatched(db):
    order, parts, lines, admin = example_order(db)
    payment = db.query(Pago).filter_by(pedido_id=order.id).one()
    order.estado = 'pendiente'
    payment.estado = 'en_verificacion'
    for part in parts:
        part.estado = 'pendiente'
    db.commit()

    with pytest.raises(HTTPException, match='pago todavía no está aprobado'):
        admin_status(db, order.id, admin, 'confirmado')

    # Defensa adicional si un subpedido hubiera sido alterado por datos
    # históricos o una herramienta anterior.
    parts[0].estado = 'confirmado'
    db.commit()
    with pytest.raises(HTTPException, match='pago todavía no está aprobado'):
        create_shipment(
            db, order.id, parts[0].id, admin,
            [{'pedido_linea_id': lines[0].id, 'cantidad': 1}],
        )


def test_pending_card_payment_cannot_be_prepared_or_delivered(db):
    order, parts, lines, admin = example_order(db)
    payment = db.query(Pago).filter_by(pedido_id=order.id).one()

    # Preparación: incluso un subpedido confirmado queda bloqueado mientras el
    # cobro de tarjeta sea incierto.
    payment.estado = 'en_verificacion'
    db.commit()
    with pytest.raises(HTTPException, match='pago todavía no está aprobado'):
        prepare_part(db, order.id, parts[0].id, admin)

    # Entrega: el envío pudo haberse creado cuando el pago era válido, pero si
    # luego se marca en verificación tampoco se permite completar la entrega.
    payment.estado = 'aprobado'
    db.commit()
    shipment_id = create_shipment(
        db, order.id, parts[0].id, admin,
        [{'pedido_linea_id': lines[0].id, 'cantidad': 1}],
    )
    payment.estado = 'en_verificacion'
    db.commit()
    with pytest.raises(HTTPException, match='pago todavía no está aprobado'):
        deliver_shipment(db, order.id, shipment_id, admin)


def test_fulfillment_selects_payment_matching_order_idempotency_key(db):
    order, parts, _lines, admin = example_order(db)
    authoritative = db.query(Pago).filter_by(pedido_id=order.id).one()
    order.clave_idempotencia = str(uuid.uuid4())
    authoritative.clave_idempotencia = order.clave_idempotencia
    authoritative.estado = 'en_verificacion'
    # Simula un registro histórico incorrecto posterior. El código no debe
    # elegirlo solo por tener el id más alto ni porque figure aprobado.
    db.add(Pago(
        pedido_id=order.id,
        metodo_pago_id=authoritative.metodo_pago_id,
        monto=authoritative.monto,
        estado='aprobado',
        clave_idempotencia=str(uuid.uuid4()),
    ))
    db.commit()

    with pytest.raises(HTTPException, match='pago todavía no está aprobado'):
        prepare_part(db, order.id, parts[0].id, admin)

    authoritative.estado = 'aprobado'
    db.commit()
    prepare_part(db, order.id, parts[0].id, admin)
    assert parts[0].estado == 'preparando'


def test_cash_on_delivery_pending_can_be_dispatched(db):
    order, parts, lines, admin = example_order(db)
    payment = db.query(Pago).filter_by(pedido_id=order.id).one()
    payment.metodo_pago_id = db.query(MetodoPago).filter(
        MetodoPago.nombre.ilike('%contra entrega%'),
    ).one().id
    payment.estado = 'pendiente'
    db.commit()

    shipment_id = create_shipment(
        db, order.id, parts[0].id, admin,
        [{'pedido_linea_id': lines[0].id, 'cantidad': 1}],
    )
    assert shipment_id is not None


def test_admin_confirmation_uses_saga_once(db):
    from app.models.outbox import OutboxEvento

    order, parts, lines, admin = example_order(db)
    payment = db.query(Pago).filter_by(pedido_id=order.id).one()
    order.estado = 'pendiente'
    for part in parts:
        part.estado = 'pendiente'

    # El helper creó movimientos representativos para las pruebas de
    # cancelación. Este caso reconstruye el estado real anterior a confirmar:
    # reserva existente y todavía ninguna salida.
    db.query(MovimientoInventario).filter_by(pedido_id=order.id).delete()
    inventories = []
    for line in lines:
        inventory = db.query(Inventario).filter_by(
            oferta_id=line.oferta_id, bodega='principal',
        ).one()
        inventory.cantidad_reservada += line.cantidad
        db.add(MovimientoInventario(
            inventario_id=inventory.id, tipo='reserva', cantidad=line.cantidad,
            motivo='Reserva de prueba para confirmación administrativa',
            pedido_id=order.id, usuario_id=admin.id,
        ))
        inventories.append((inventory, line.cantidad, inventory.cantidad_disponible))
    db.commit()

    admin_status(db, order.id, admin, 'confirmado')
    movement_count = db.query(MovimientoInventario).filter_by(
        pedido_id=order.id, tipo='salida',
    ).count()
    outbox_count = db.query(OutboxEvento).filter_by(agregado_id=str(order.id)).count()
    assert payment.estado == 'aprobado' and order.estado == 'confirmado'
    assert movement_count == len(lines)
    assert outbox_count > 0
    for inventory, quantity, available_before in inventories:
        assert inventory.cantidad_reservada == 0
        assert inventory.cantidad_disponible == available_before - quantity

    with pytest.raises(HTTPException):
        admin_status(db, order.id, admin, 'confirmado')
    assert db.query(MovimientoInventario).filter_by(
        pedido_id=order.id, tipo='salida',
    ).count() == movement_count
    assert db.query(OutboxEvento).filter_by(agregado_id=str(order.id)).count() == outbox_count


def test_admin_confirmation_failure_before_commit_rolls_back(db, monkeypatch):
    from app.core.fault_injection import FallaSimulada
    from app.models.outbox import OutboxEvento
    from app.services import checkout_service

    order, parts, lines, admin = example_order(db)
    order.estado = 'pendiente'
    for part in parts:
        part.estado = 'pendiente'
    db.query(MovimientoInventario).filter_by(pedido_id=order.id).delete()
    expected = []
    for line in lines:
        inventory = db.query(Inventario).filter_by(
            oferta_id=line.oferta_id, bodega='principal',
        ).one()
        inventory.cantidad_reservada += line.cantidad
        db.add(MovimientoInventario(
            inventario_id=inventory.id, tipo='reserva', cantidad=line.cantidad,
            motivo='Reserva para probar rollback de confirmación',
            pedido_id=order.id, usuario_id=admin.id,
        ))
        expected.append((inventory.id, inventory.cantidad_disponible, inventory.cantidad_reservada))
    db.commit()
    outbox_before = db.query(OutboxEvento).filter_by(agregado_id=str(order.id)).count()

    def fail_before_commit(point):
        if point == 'checkout.confirmacion':
            raise FallaSimulada('fallo antes del commit')

    monkeypatch.setattr(checkout_service, 'punto_de_falla', fail_before_commit)
    with pytest.raises(FallaSimulada, match='fallo antes del commit'):
        admin_status(db, order.id, admin, 'confirmado')

    db.expire_all()
    persisted_order = db.get(Pedido, order.id)
    assert persisted_order.estado == 'pendiente'
    assert db.query(MovimientoInventario).filter_by(
        pedido_id=order.id, tipo='salida',
    ).count() == 0
    assert db.query(OutboxEvento).filter_by(agregado_id=str(order.id)).count() == outbox_before
    for inventory_id, available, reserved in expected:
        inventory = db.get(Inventario, inventory_id)
        assert (inventory.cantidad_disponible, inventory.cantidad_reservada) == (available, reserved)


def test_cannot_cancel_after_dispatch_or_force_global_status(db):
    order, parts, lines, admin = example_order(db)
    create_shipment(db, order.id, parts[0].id, admin, [{'pedido_linea_id': lines[0].id, 'cantidad': 1}])
    for target in ['cancelado', 'entregado', 'reembolsado']:
        with pytest.raises(HTTPException) as exc:
            admin_status(db, order.id, admin, target)
        assert exc.value.status_code == 409


def test_confirm_pending_and_no_refund_without_payment(db):
    order, parts, lines, admin = example_order(db)
    order.estado = 'pendiente'
    for part in parts:
        part.estado = 'pendiente'
    db.commit()
    with pytest.raises(HTTPException):
        create_shipment(db, order.id, parts[0].id, admin, [{'pedido_linea_id': lines[0].id, 'cantidad': 1}])
    admin_status(db, order.id, admin, 'confirmado')
    assert order.estado == 'confirmado' and all(p.estado == 'confirmado' for p in parts)
    admin_status(db, order.id, admin, 'cancelado')
    with pytest.raises(HTTPException) as exc:
        admin_status(db, order.id, admin, 'reembolsado')
    assert exc.value.status_code == 409


def test_variant_request_includes_offer(db):
    mongo = get_mongo_db()
    admin = db.query(Usuario).filter_by(email='admin@tiendaya.gt').one()
    vendor = db.query(Vendedor).filter_by(estado_verificacion='verificado').first()
    user = db.get(Usuario, vendor.usuario_id)
    product = mongo.productos.find_one({'estado': 'activo'})
    attrs = {'prueba_solicitud': uuid.uuid4().hex}
    request = propose_variant(VariantProposalCreate(producto_ref=str(product['_id']),
        atributos=attrs, precio=25, stock=3), user, db, mongo)
    try:
        assert not mongo.producto_variantes.find_one({'atributos': attrs})
        result = approve_request(request['id'], ReviewPayload(), admin, db, mongo)
        offer = db.get(Oferta, result['oferta_id_resultado'])
        assert offer.vendedor_id == vendor.id and result['estado'] == 'aprobada'
        assert db.query(Inventario).filter_by(oferta_id=offer.id).one().cantidad_disponible == 3
        assert mongo.producto_variantes.find_one({'atributos': attrs})
        with pytest.raises(HTTPException):
            approve_request(request['id'], ReviewPayload(), admin, db, mongo)
    finally:
        mongo.producto_variantes.delete_one({'producto_ref': str(product['_id']), 'atributos': attrs})
