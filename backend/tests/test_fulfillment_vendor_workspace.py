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
from app.api.v1.vendor import change_own_offer, VendorOfferUpdate
from app.api.v1.catalog_requests import propose_variant, approve_request, VariantProposalCreate, ReviewPayload
from app.services.fulfillment_service import create_shipment, deliver_shipment, detail, progress_state, admin_status


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
        parts.append(part)
        lines.append(line)
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
    from app.models.pago import Pago, MetodoPago
    order, parts, lines, admin = example_order(db)
    payment = Pago(pedido_id=order.id, metodo_pago_id=db.query(MetodoPago).first().id,
                   monto=70, estado='aprobado')
    db.add(payment)
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
