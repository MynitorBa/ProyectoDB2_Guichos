from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from decimal import Decimal

from app.core.db_mysql import get_db
from app.core.deps import get_current_user
from app.models.usuario import Usuario
from app.models.carrito import Carrito, CarritoItem
from app.models.producto import Producto

router = APIRouter(prefix='/cart', tags=['Carrito'])


class CartItemRequest(BaseModel):
    producto_id: int
    cantidad: int = 1


def _get_or_create_cart(db: Session, usuario_id: int) -> Carrito:
    carrito = db.query(Carrito).filter_by(usuario_id=usuario_id, estado='activo').first()
    if not carrito:
        carrito = Carrito(usuario_id=usuario_id)
        db.add(carrito)
        db.flush()
    return carrito


@router.get('/')
def ver_carrito(current_user: Usuario = Depends(get_current_user), db: Session = Depends(get_db)):
    carrito = db.query(Carrito).filter_by(usuario_id=current_user.id, estado='activo').first()
    if not carrito:
        return {'items': [], 'total': 0}

    items = []
    total = Decimal('0')
    for item in carrito.items:
        prod = db.get(Producto, item.producto_id)
        subtotal = item.precio_al_agregar * item.cantidad
        total += subtotal
        items.append({
            'id': item.id,
            'producto_id': item.producto_id,
            'producto_ref': item.producto_ref,
            'nombre': prod.nombre if prod else 'Producto eliminado',
            'precio': float(item.precio_al_agregar),
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
    prod = db.get(Producto, payload.producto_id)
    if not prod:
        raise HTTPException(status_code=404, detail='Producto no encontrado.')

    carrito = _get_or_create_cart(db, current_user.id)

    item = db.query(CarritoItem).filter_by(carrito_id=carrito.id, producto_id=payload.producto_id).first()
    if item:
        item.cantidad += payload.cantidad
    else:
        item = CarritoItem(
            carrito_id=carrito.id,
            producto_id=payload.producto_id,
            producto_ref=prod.producto_ref,
            cantidad=payload.cantidad,
            precio_al_agregar=prod.precio,
        )
        db.add(item)

    db.commit()
    return {'mensaje': 'Producto agregado al carrito.'}


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
