from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from pymongo.database import Database
from bson import ObjectId
from app.core.db_mysql import get_db
from app.core.db_mongo import get_mongo_db
from app.core.deps import get_admin_user
from app.models.usuario import Usuario
from app.models.vendedor import Vendedor
from app.models.oferta import Oferta
from app.models.pedido import Pedido
from app.models.pedido_vendedor import PedidoVendedor
from app.services.offer_service import stock_by_offer

router = APIRouter(prefix='/admin', tags=['Fichas administrativas'])


@router.get('/users/{user_id}')
def user_detail(user_id: int, _: Usuario = Depends(get_admin_user), db: Session = Depends(get_db)):
    user = db.get(Usuario, user_id)
    if not user:
        raise HTTPException(404, 'Usuario no encontrado.')
    vendor = db.query(Vendedor).filter_by(usuario_id=user.id).first()
    return {'id': user.id, 'nombre': user.nombre, 'apellido': user.apellido,
        'email': user.email, 'estado': user.estado, 'roles': [r.nombre for r in user.roles],
        'vendedor_id': vendor.id if vendor else None}


@router.get('/vendors/{vendor_id}')
def vendor_detail(vendor_id: int, orders_page: int = Query(1, ge=1), offers_page: int = Query(1, ge=1),
    estado: str | None = None, _: Usuario = Depends(get_admin_user),
    db: Session = Depends(get_db), mongo: Database = Depends(get_mongo_db)):
    vendor = db.get(Vendedor, vendor_id)
    if not vendor:
        raise HTTPException(404, 'Vendedor no encontrado.')
    user = db.get(Usuario, vendor.usuario_id)
    offer_query = db.query(Oferta).filter_by(vendedor_id=vendor.id)
    order_query = db.query(PedidoVendedor).filter_by(vendedor_id=vendor.id)
    states = dict(db.query(PedidoVendedor.estado, func.count(PedidoVendedor.id)).filter_by(vendedor_id=vendor.id).group_by(PedidoVendedor.estado).all())
    if estado:
        order_query = order_query.filter_by(estado=estado)
    offers = offer_query.order_by(Oferta.id.desc()).offset((offers_page-1)*20).limit(20).all()
    stocks = stock_by_offer(db, [o.id for o in offers])
    products = {str(p['_id']):p for p in mongo.productos.find({'_id':{'$in':[ObjectId(o.producto_ref) for o in offers]}},{'nombre':1})}
    orders = []
    for part in order_query.order_by(PedidoVendedor.id.desc()).offset((orders_page-1)*20).limit(20).all():
        order = db.get(Pedido, part.pedido_id)
        orders.append({'id':order.id,'subpedido_id':part.id,'estado':part.estado,
            'fecha':order.fecha_creacion.isoformat()+'Z','subtotal':float(part.subtotal)})
    return {'id':vendor.id,'usuario_id':vendor.usuario_id,'nombre_comercial':vendor.nombre_comercial,
        'nit':vendor.nit,'estado_verificacion':vendor.estado_verificacion,'es_tiendaya':vendor.es_tiendaya,
        'email':user.email,'pedidos_por_estado':states,'pedidos':orders,
        'pedidos_pages':max(1,-(-order_query.count()//20)),
        'ofertas_pages':max(1,-(-offer_query.count()//20)),
        'ofertas':[{'id':o.id,'producto_ref':o.producto_ref,'producto_nombre':products.get(o.producto_ref,{}).get('nombre',o.sku),
            'sku':o.sku,'precio':float(o.precio_actual),'stock':stocks.get(o.id,0),'estado':o.estado} for o in offers]}
