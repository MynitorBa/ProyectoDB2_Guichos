from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from decimal import Decimal
from typing import Literal
from bson import ObjectId
from pymongo.database import Database
from app.core.db_mongo import get_mongo_db
from app.models.oferta import Oferta
from app.models.inventario import Inventario
from app.services.offer_service import editar_oferta
from app.services.variant_service import list_variants
from app.services.fulfillment_service import prepare_part
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.db_mysql import get_db
from app.core.deps import require_role
from app.models.pedido import Pedido, PedidoLinea
from app.models.pedido_vendedor import PedidoVendedor
from app.models.usuario import Usuario
from app.models.vendedor import Vendedor

GT_TZ = timezone(timedelta(hours=-6))
router = APIRouter(prefix='/vendor', tags=['Vendedor'])

get_vendor_user = require_role('vendedor', 'administrador')

# pendiente lo asigna el sistema; cancelado y reembolsado son exclusivos del admin
_ESTADOS_ADMIN_ONLY = {'pendiente', 'cancelado', 'reembolsado'}

def _estados_vendedor() -> list[str]:
    """Devuelve los estados válidos del subpedido que controla el vendedor."""
    all_estados: list[str] = list(
        PedidoVendedor.__table__.c['estado'].type.enums
    )
    return ['preparando']  # Enviado/entregado se calculan desde envíos por cantidad.


class StatusUpdate(BaseModel):
    estado: str


@router.get('/estados')
def vendor_estados():
    return _estados_vendedor()


def _get_vendedor(db: Session, user: Usuario) -> Vendedor:
    v = db.query(Vendedor).filter_by(usuario_id=user.id).first()
    if not v:
        raise HTTPException(403, 'No tienes perfil de vendedor configurado. Pide al admin que configure tu perfil.')
    return v


# Resumen financiero del vendedor: ingresos totales, pedidos totales y pendientes de despacho
@router.get('/stats')
def vendor_stats(
    current_user: Usuario = Depends(get_vendor_user),
    db: Session = Depends(get_db),
):
    v = _get_vendedor(db, current_user)

    total_pedidos = (
        db.query(func.count(PedidoVendedor.id))
        .filter(PedidoVendedor.vendedor_id == v.id)
        .scalar() or 0
    )

    ingresos = (
        db.query(func.sum(PedidoVendedor.subtotal))
        .join(Pedido, Pedido.id == PedidoVendedor.pedido_id)
        .filter(
            PedidoVendedor.vendedor_id == v.id,
            Pedido.estado.notin_(['cancelado', 'reembolsado']),
            PedidoVendedor.estado.notin_(['cancelado', 'reembolsado']),
        )
        .scalar() or 0
    )

    pendientes = (
        db.query(func.count(PedidoVendedor.id))
        .filter(
            PedidoVendedor.vendedor_id == v.id,
            PedidoVendedor.estado.in_(['confirmado', 'preparando', 'enviado_parcial', 'entregado_parcial']),
        )
        .scalar() or 0
    )

    return {
        'nombre_comercial': v.nombre_comercial,
        'total_pedidos': total_pedidos,
        'ingresos_totales': float(ingresos),
        'pendientes': pendientes,
    }


# Lista solo los subpedidos (PedidoVendedor) que corresponden a este vendedor con sus líneas de producto
@router.get('/orders')
def vendor_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: Usuario = Depends(get_vendor_user),
    db: Session = Depends(get_db),
):
    v = _get_vendedor(db, current_user)

    total = db.query(func.count(PedidoVendedor.id)).filter(
        PedidoVendedor.vendedor_id == v.id
    ).scalar() or 0

    rows = (
        db.query(PedidoVendedor, Pedido)
        .join(Pedido, Pedido.id == PedidoVendedor.pedido_id)
        .filter(PedidoVendedor.vendedor_id == v.id)
        .order_by(Pedido.fecha_creacion.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    items = []
    for part, p in rows:
        u = p.usuario
        mis_lineas = (
            db.query(PedidoLinea)
            .filter(PedidoLinea.pedido_vendedor_id == part.id)
            .all()
        )
        items.append({
            'id': p.id,
            'pedido_vendedor_id': part.id,
            'fecha': p.fecha_creacion.replace(tzinfo=timezone.utc).astimezone(GT_TZ).isoformat(),
            'estado': part.estado,
            'estado_pedido': p.estado,
            'total': float(part.subtotal + part.costo_envio),
            'comprador': {
                'nombre': f'{u.nombre} {u.apellido}' if u else '—',
                'email': u.email if u else '—',
            },
            'mis_lineas': [
                {
                    'producto_nombre': l.producto_nombre,
                    'precio_unitario': float(l.precio_unitario),
                    'cantidad': l.cantidad,
                    'subtotal_linea': float(l.subtotal_linea),
                }
                for l in mis_lineas
            ],
            'subtotal_mis_productos': float(sum(l.subtotal_linea for l in mis_lineas)),
        })

    return {
        'items': items,
        'total': total,
        'page': page,
        'page_size': page_size,
        'total_pages': max(1, -(-total // page_size)),
    }


# El vendedor solo puede cambiar su subpedido a los estados que no son exclusivos del admin
@router.patch('/orders/{pedido_id}/status')
def update_vendor_order_status(
    pedido_id: int,
    payload: StatusUpdate,
    current_user: Usuario = Depends(get_vendor_user),
    db: Session = Depends(get_db),
):
    estados_validos = _estados_vendedor()
    if payload.estado not in estados_validos:
        raise HTTPException(400, f'Solo puedes establecer: {", ".join(sorted(estados_validos))}.')

    v = _get_vendedor(db, current_user)

    part = (
        db.query(PedidoVendedor)
        .filter(
            PedidoVendedor.pedido_id == pedido_id,
            PedidoVendedor.vendedor_id == v.id,
        )
        .first()
    )
    if not part:
        raise HTTPException(403, 'No tienes permiso para modificar este pedido.')

    pedido = db.get(Pedido, pedido_id)
    if not pedido:
        raise HTTPException(404, 'Pedido no encontrado.')

    prepare_part(db, pedido_id, part.id, current_user)
    return {
        'id': pedido_id,
        'pedido_vendedor_id': part.id,
        'estado': payload.estado,
    }


class VendorOfferUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    version: int = Field(ge=1)
    precio: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    stock: int | None = Field(default=None, ge=0, le=2147483647, strict=True)
    estado: Literal['activa', 'pausada'] | None = None


@router.get('/offers')
def own_offers(q: str = '', estado: str | None = None, oferta_id: int | None = None, page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100), user: Usuario = Depends(get_vendor_user),
    db: Session = Depends(get_db), mongo: Database = Depends(get_mongo_db)):
    vendor = _get_vendedor(db, user)
    query = db.query(Oferta).filter_by(vendedor_id=vendor.id)
    if oferta_id is not None:
        query = query.filter_by(id=oferta_id)
    if estado:
        query = query.filter_by(estado=estado)
    if q.strip():
        import re
        refs = [str(d['_id']) for d in mongo.productos.find(
            {'nombre': {'$regex': re.escape(q.strip()), '$options': 'i'}}, {'_id': 1})]
        query = query.filter((Oferta.producto_ref.in_(refs)) | (Oferta.sku.contains(q.strip())))
    total = query.count()
    rows = query.order_by(Oferta.id.desc()).offset((page-1)*page_size).limit(page_size).all()
    result = []
    for offer in rows:
        product = mongo.productos.find_one({'_id': ObjectId(offer.producto_ref)}) or {}
        variant = next((v for v in list_variants(mongo, db, offer.producto_ref)
            if v['variante_id'] == offer.producto_variante_id), {})
        inventory = db.query(Inventario).filter_by(oferta_id=offer.id, bodega='principal').first()
        physical = inventory.cantidad_disponible if inventory else 0
        reserved = inventory.cantidad_reservada if inventory else 0
        images = product.get('imagenes', [])
        images = [image.get('url') if isinstance(image, dict) else image for image in images if image]
        images = [image for image in images if image]
        result.append({'id': offer.id, 'producto_ref': offer.producto_ref,
            'producto_nombre': product.get('nombre', offer.sku), 'imagen': images[0] if images else None,
            'producto_estado': product.get('estado'), 'atributos': variant.get('atributos', {}),
            'sku': offer.sku, 'precio': float(offer.precio_actual), 'estado': offer.estado,
            'stock': max(0, physical-reserved), 'existencias': physical, 'reservado': reserved,
            'version': offer.version})
    return {'items': result, 'total': total, 'page': page, 'total_pages': max(1, -(-total//page_size))}


@router.patch('/offers/{offer_id}')
def change_own_offer(offer_id: int, payload: VendorOfferUpdate,
    user: Usuario = Depends(get_vendor_user), db: Session = Depends(get_db)):
    vendor = _get_vendedor(db, user)
    if vendor.estado_verificacion != 'verificado':
        raise HTTPException(403, 'El vendedor no está verificado.')
    offer = db.query(Oferta).filter_by(id=offer_id, vendedor_id=vendor.id).with_for_update().first()
    if not offer:
        raise HTTPException(404, 'Oferta no encontrada.')
    if offer.estado not in {'activa', 'pausada'}:
        raise HTTPException(409, 'Solo puedes editar ofertas aprobadas activas o pausadas.')
    editar_oferta(db, oferta=offer, usuario_id=user.id, **payload.model_dump(), motivo='Edición del vendedor')
    db.commit()
    return {'id': offer.id, 'version': offer.version}
