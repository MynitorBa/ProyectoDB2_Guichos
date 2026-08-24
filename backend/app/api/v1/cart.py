from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from decimal import Decimal
from bson import ObjectId
from pymongo.database import Database

from app.core.db_mongo import get_mongo_db
from app.core.db_mysql import get_db
from app.core.deps import get_current_user
from app.models.usuario import Usuario
from app.models.carrito import Carrito, CarritoItem
from app.models.oferta import Oferta
from app.services.offer_service import resolver_oferta_comprable

router = APIRouter(prefix='/cart', tags=['Carrito'])


class CartItemRequest(BaseModel):
    oferta_id: int
    cantidad: int = 1


def _get_or_create_cart(db: Session, usuario_id: int) -> Carrito:
    carrito = db.query(Carrito).filter_by(usuario_id=usuario_id, estado='activo').first()
    if not carrito:
        carrito = Carrito(usuario_id=usuario_id)
        db.add(carrito)
        db.flush()
    return carrito


@router.get('/')
def ver_carrito(
    current_user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
    mongo_db: Database = Depends(get_mongo_db),
):
    carrito = db.query(Carrito).filter_by(usuario_id=current_user.id, estado='activo').first()
    if not carrito:
        return {'items': [], 'total': 0}

    items = []
    total = Decimal('0')
    for item in carrito.items:
        offer = db.get(Oferta, item.oferta_id) if item.oferta_id else None
        current_price = offer.precio_actual if offer else item.precio_al_agregar
        product_ref = item.producto_ref or (offer.producto_ref if offer else None)
        product_doc = None
        if product_ref:
            try:
                product_doc = mongo_db.productos.find_one(
                    {'_id': ObjectId(product_ref)}, {'nombre': 1}
                )
            except Exception:
                product_doc = None
        subtotal = current_price * item.cantidad
        total += subtotal
        items.append({
            'id': item.id,
            'oferta_id': item.oferta_id,
            'producto_ref': item.producto_ref,
            'nombre': (
                product_doc.get('nombre')
                if product_doc and product_doc.get('nombre')
                else (offer.sku if offer else 'Producto eliminado')
            ),
            'precio': float(current_price),
            'precio_al_agregar': float(item.precio_al_agregar),
            'precio_cambio': current_price != item.precio_al_agregar,
            'cantidad': item.cantidad,
            'subtotal': float(subtotal),
        })

    return {'items': items, 'total': float(total)}


@router.post('/items', status_code=201)
def agregar_item(
    payload: CartItemRequest,
    current_user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if payload.cantidad < 1:
        raise HTTPException(status_code=422, detail='La cantidad debe ser positiva.')
    try:
        offer = resolver_oferta_comprable(db, oferta_id=payload.oferta_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    carrito = _get_or_create_cart(db, current_user.id)

    item = db.query(CarritoItem).filter_by(
        carrito_id=carrito.id, oferta_id=offer.id
    ).first()
    if item:
        item.cantidad += payload.cantidad
    else:
        item = CarritoItem(
            carrito_id=carrito.id,
            oferta_id=offer.id,
            producto_ref=offer.producto_ref,
            cantidad=payload.cantidad,
            precio_al_agregar=offer.precio_actual,
        )
        db.add(item)

    db.commit()
    return {
        'mensaje': 'Oferta agregada al carrito.',
        'oferta_id': offer.id,
    }


@router.delete('/items/{item_id}', status_code=204)
def eliminar_item(
    item_id: int,
    current_user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    carrito = db.query(Carrito).filter_by(usuario_id=current_user.id, estado='activo').first()
    if not carrito:
        raise HTTPException(status_code=404, detail='Carrito no encontrado.')

    item = db.query(CarritoItem).filter_by(id=item_id, carrito_id=carrito.id).first()
    if not item:
        raise HTTPException(status_code=404, detail='Item no encontrado.')

    db.delete(item)
    db.commit()
