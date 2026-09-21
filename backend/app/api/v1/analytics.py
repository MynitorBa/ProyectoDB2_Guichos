"""Consultas de tendencias servidas desde Cassandra."""

from datetime import date

from bson import ObjectId
from cassandra import DriverException
from fastapi import APIRouter, Depends, HTTPException, Query
from pymongo.database import Database
from sqlalchemy.orm import Session

from app.core.db_cassandra import cassandra_health
from app.core.db_mongo import get_mongo_db
from app.core.db_mysql import get_db
from app.core.deps import get_admin_user, require_role
from app.models.usuario import Usuario
from app.models.vendedor import Vendedor
from app.models.oferta import Oferta
from app.models.inventario import Inventario
from app.services.analytics_service import (
    current_week_start,
    product_trends,
    product_weekly_trend,
    vendor_offer_summary,
    vendor_product_weekly_trend,
)


router = APIRouter(prefix='/analytics', tags=['Analítica Cassandra'])
get_vendor_user = require_role('vendedor', 'administrador')


def _week(value: date | None) -> date:
    chosen = value or current_week_start()
    if chosen.weekday() != 0:
        raise HTTPException(422, 'semana_inicio debe ser un lunes.')
    return chosen


def _unavailable(exc: Exception) -> HTTPException:
    return HTTPException(
        503,
        'La analítica histórica no está disponible temporalmente; las compras continúan funcionando.',
    )


@router.get('/health')
def health(_: Usuario = Depends(get_admin_user)):
    try:
        return cassandra_health()
    except DriverException as exc:
        raise _unavailable(exc) from exc


@router.get('/admin/trends')
def admin_trends(
    semana_inicio: date | None = Query(None),
    semanas_comparacion: int = Query(1, ge=0, le=4),
    solo_sin_ventas: bool = Query(False),
    _: Usuario = Depends(get_admin_user),
    mongo: Database = Depends(get_mongo_db),
):
    selected = _week(semana_inicio)
    try:
        items = product_trends(selected, comparison_weeks=semanas_comparacion)
    except DriverException as exc:
        raise _unavailable(exc) from exc
    if solo_sin_ventas:
        sold_refs = {
            item['producto_ref'] for item in product_trends(selected, comparison_weeks=0)
            if item['unidades'] > 0
        }
        items = []
        for product in mongo.productos.find({}, {
            'nombre': 1, 'sku': 1, 'estado': 1, 'categorias': 1, 'imagenes': 1,
        }).sort('nombre', 1):
            ref = str(product['_id'])
            if ref in sold_refs:
                continue
            images = product.get('imagenes') or []
            first_image = images[0] if images else None
            items.append({
                'producto_ref': ref,
                'producto_nombre': product.get('nombre'),
                'sku': product.get('sku'),
                'estado': product.get('estado'),
                'categorias': product.get('categorias') or [],
                'imagen': first_image.get('url') if isinstance(first_image, dict) else first_image,
                'unidades': 0,
            })
    return {
        'semana_inicio': selected.isoformat(),
        'semanas_comparacion': semanas_comparacion,
        'solo_sin_ventas': solo_sin_ventas,
        'items': items,
    }


@router.get('/admin/product-trend')
def admin_product_trend(
    producto_ref: str,
    desde: date = Query(...),
    hasta: date = Query(...),
    _: Usuario = Depends(get_admin_user),
    mongo: Database = Depends(get_mongo_db),
):
    start = _week(desde)
    end = _week(hasta)
    if end < start:
        raise HTTPException(422, 'hasta no puede ser anterior a desde.')
    if (end - start).days > 7 * 104:
        raise HTTPException(422, 'El rango máximo de consulta es de 104 semanas.')
    try:
        object_id = ObjectId(producto_ref)
    except Exception as exc:
        raise HTTPException(422, 'producto_ref no es válido.') from exc
    product = mongo.productos.find_one({'_id': object_id}, {'nombre': 1})
    if not product:
        raise HTTPException(404, 'Producto no encontrado.')
    try:
        items = product_weekly_trend(producto_ref, start, end)
    except DriverException as exc:
        raise _unavailable(exc) from exc
    return {
        'producto_ref': producto_ref,
        'producto_nombre': product.get('nombre'),
        'desde': start.isoformat(),
        'hasta': end.isoformat(),
        'items': items,
    }


@router.get('/vendor/trends')
def vendor_trends(
    semana_inicio: date | None = Query(None),
    semanas_comparacion: int = Query(1, ge=0, le=4),
    solo_sin_ventas: bool = Query(False),
    user: Usuario = Depends(get_vendor_user),
    db: Session = Depends(get_db),
    mongo: Database = Depends(get_mongo_db),
):
    vendor = db.query(Vendedor).filter_by(usuario_id=user.id).first()
    if not vendor:
        raise HTTPException(403, 'No tienes perfil de vendedor configurado.')
    selected = _week(semana_inicio)
    try:
        items = vendor_offer_summary(
            vendor.id, selected, comparison_weeks=semanas_comparacion
        )
    except DriverException as exc:
        raise _unavailable(exc) from exc
    if solo_sin_ventas:
        sold_offer_ids = {
            item['oferta_id'] for item in vendor_offer_summary(
                vendor.id, selected, comparison_weeks=0
            )
            if item['unidades'] > 0
        }
        offers = db.query(Oferta).filter_by(vendedor_id=vendor.id).order_by(Oferta.id).all()
        refs = []
        for offer in offers:
            if offer.producto_ref not in refs:
                refs.append(offer.producto_ref)
        valid_ids = [ObjectId(ref) for ref in refs if ObjectId.is_valid(ref)]
        products = {
            str(product['_id']): product
            for product in mongo.productos.find({'_id': {'$in': valid_ids}}, {'nombre': 1})
        }
        inventories = {
            row.oferta_id: row
            for row in db.query(Inventario).filter(
                Inventario.oferta_id.in_([offer.id for offer in offers]),
                Inventario.bodega == 'principal',
            ).all()
        } if offers else {}
        items = [{
            'oferta_id': offer.id,
            'producto_ref': offer.producto_ref,
            'producto_nombre': products.get(offer.producto_ref, {}).get('nombre', offer.sku),
            'sku': offer.sku,
            'estado': offer.estado,
            'precio': float(offer.precio_actual),
            'stock': max(0, (
                inventories[offer.id].cantidad_disponible - inventories[offer.id].cantidad_reservada
            )) if offer.id in inventories else 0,
            'unidades': 0,
        } for offer in offers if offer.id not in sold_offer_ids]
    return {
        'semana_inicio': selected.isoformat(),
        'vendedor_id': vendor.id,
        'semanas_comparacion': semanas_comparacion,
        'solo_sin_ventas': solo_sin_ventas,
        'items': items,
    }


@router.get('/vendor/products')
def vendor_analytics_products(
    q: str = '',
    page: int = Query(1, ge=1),
    page_size: int = Query(12, ge=1, le=100),
    user: Usuario = Depends(get_vendor_user),
    db: Session = Depends(get_db),
    mongo: Database = Depends(get_mongo_db),
):
    import re

    vendor = db.query(Vendedor).filter_by(usuario_id=user.id).first()
    if not vendor:
        raise HTTPException(403, 'No tienes perfil de vendedor configurado.')
    refs = [row[0] for row in db.query(Oferta.producto_ref).filter_by(
        vendedor_id=vendor.id
    ).distinct().all()]
    valid_ids = [ObjectId(ref) for ref in refs if ObjectId.is_valid(ref)]
    mongo_filter = {'_id': {'$in': valid_ids}}
    if q.strip():
        mongo_filter['nombre'] = {'$regex': re.escape(q.strip()), '$options': 'i'}
    total = mongo.productos.count_documents(mongo_filter)
    docs = list(mongo.productos.find(mongo_filter).sort('nombre', 1).skip(
        (page - 1) * page_size
    ).limit(page_size))
    items = []
    for product in docs:
        images = product.get('imagenes') or []
        items.append({
            '_id': str(product['_id']),
            'nombre': product.get('nombre'),
            'sku': product.get('sku'),
            'imagenes': [
                image.get('url') if isinstance(image, dict) else image
                for image in images if image
            ],
        })
    return {
        'items': items,
        'total': total,
        'page': page,
        'total_pages': max(1, -(-total // page_size)),
    }


@router.get('/vendor/product-trend')
def vendor_product_trend(
    producto_ref: str,
    desde: date = Query(...),
    hasta: date = Query(...),
    user: Usuario = Depends(get_vendor_user),
    db: Session = Depends(get_db),
    mongo: Database = Depends(get_mongo_db),
):
    vendor = db.query(Vendedor).filter_by(usuario_id=user.id).first()
    if not vendor:
        raise HTTPException(403, 'No tienes perfil de vendedor configurado.')
    if not db.query(Oferta.id).filter_by(
        vendedor_id=vendor.id, producto_ref=producto_ref
    ).first():
        raise HTTPException(404, 'El producto no pertenece a tus ofertas.')
    start = _week(desde)
    end = _week(hasta)
    if end < start:
        raise HTTPException(422, 'hasta no puede ser anterior a desde.')
    if (end - start).days > 7 * 104:
        raise HTTPException(422, 'El rango máximo de consulta es de 104 semanas.')
    product = mongo.productos.find_one(
        {'_id': ObjectId(producto_ref)}, {'nombre': 1}
    ) if ObjectId.is_valid(producto_ref) else None
    if not product:
        raise HTTPException(404, 'Producto no encontrado.')
    try:
        items = vendor_product_weekly_trend(vendor.id, producto_ref, start, end)
    except DriverException as exc:
        raise _unavailable(exc) from exc
    return {
        'producto_ref': producto_ref,
        'producto_nombre': product.get('nombre'),
        'desde': start.isoformat(),
        'hasta': end.isoformat(),
        'items': items,
    }
