from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from decimal import Decimal
from bson import ObjectId
from pymongo.database import Database
import redis as redis_lib

from app.core.db_mongo import get_mongo_db
from app.core.db_mysql import get_db
from app.core.db_redis import get_redis
from app.core.deps import get_current_user
from app.models.usuario import Usuario
from app.models.oferta import Oferta
from app.services.offer_service import resolver_oferta_comprable, stock_by_offer
from app.services import redis_cart_service as rcs

router = APIRouter(prefix='/cart', tags=['Carrito'])


def _cart_unavailable(exc: Exception) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={'detail': 'El carrito no está disponible temporalmente.', 'code': 'CART_UNAVAILABLE'},
    )


class CartItemRequest(BaseModel):
    oferta_id: int
    cantidad: int = 1


class UpdateCantidadRequest(BaseModel):
    cantidad: int


# ── GET /cart/ ────────────────────────────────────────────────────────────────


@router.get('/')
def ver_carrito(
    current_user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
    mongo_db: Database = Depends(get_mongo_db),
    r: redis_lib.Redis = Depends(get_redis),
):
    try:
        items_raw = rcs.obtener_carrito(r, current_user.id)
    except redis_lib.RedisError as exc:
        raise _cart_unavailable(exc) from exc
    if not items_raw:
        return {'items': [], 'total': 0, 'tiene_alertas': False, 'ttl_segundos': -2}

    offer_ids = [i['oferta_id'] for i in items_raw]
    stocks = stock_by_offer(db, offer_ids)

    items = []
    total = Decimal('0')
    tiene_alertas = False

    for raw in items_raw:
        oferta_id = raw['oferta_id']
        precio_al_agregar = Decimal(raw['precio_al_agregar'])
        producto_ref = raw.get('producto_ref')
        cantidad = raw['cantidad']

        offer = db.get(Oferta, oferta_id)
        current_price = offer.precio_actual if offer else precio_al_agregar
        available_stock = stocks.get(oferta_id, 0) if offer else 0
        sin_stock = offer is None or offer.estado != 'activa' or available_stock < cantidad
        precio_cambio = current_price != precio_al_agregar
        if sin_stock or precio_cambio:
            tiene_alertas = True

        product_doc = None
        if producto_ref:
            try:
                product_doc = mongo_db.productos.find_one(
                    {'_id': ObjectId(producto_ref)}, {'nombre': 1}
                )
            except Exception:
                product_doc = None

        subtotal = current_price * cantidad
        if not sin_stock:
            total += subtotal

        items.append({
            'oferta_id': oferta_id,
            'producto_ref': producto_ref,
            'nombre': (
                product_doc.get('nombre')
                if product_doc and product_doc.get('nombre')
                else (offer.sku if offer else 'Producto eliminado')
            ),
            'precio': float(current_price),
            'precio_al_agregar': float(precio_al_agregar),
            'precio_cambio': precio_cambio,
            'sin_stock': sin_stock,
            'stock_disponible': available_stock,
            'cantidad': cantidad,
            'subtotal': float(subtotal) if not sin_stock else 0.0,
        })

    try:
        ttl = rcs.ttl_restante(r, current_user.id)
    except redis_lib.RedisError as exc:
        raise _cart_unavailable(exc) from exc

    return {
        'items': items,
        'total': float(total),
        'tiene_alertas': tiene_alertas,
        'ttl_segundos': ttl,
    }


# ── POST /cart/items ──────────────────────────────────────────────────────────


@router.post('/items', status_code=201)
def agregar_item(
    payload: CartItemRequest,
    current_user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
    r: redis_lib.Redis = Depends(get_redis),
):
    if payload.cantidad < 1:
        raise HTTPException(status_code=422, detail='La cantidad debe ser positiva.')

    try:
        offer = resolver_oferta_comprable(db, oferta_id=payload.oferta_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    try:
        nueva_cantidad = rcs.agregar_item(
            r,
            usuario_id=current_user.id,
            oferta_id=offer.id,
            cantidad=payload.cantidad,
            precio_al_agregar=offer.precio_actual,
            producto_ref=offer.producto_ref,
        )
        ttl = rcs.ttl_restante(r, current_user.id)
    except redis_lib.RedisError as exc:
        raise _cart_unavailable(exc) from exc
    return {
        'mensaje': 'Oferta agregada al carrito.',
        'oferta_id': offer.id,
        'cantidad': nueva_cantidad,
        'ttl_segundos': ttl,
    }


# ── PATCH /cart/items/{oferta_id} ─────────────────────────────────────────────


@router.patch('/items/{oferta_id}', status_code=200)
def actualizar_cantidad(
    oferta_id: int,
    payload: UpdateCantidadRequest,
    current_user: Usuario = Depends(get_current_user),
    r: redis_lib.Redis = Depends(get_redis),
):
    if payload.cantidad < 1:
        raise HTTPException(status_code=422, detail='La cantidad debe ser positiva.')

    try:
        ok = rcs.actualizar_cantidad(r, current_user.id, oferta_id, payload.cantidad)
    except redis_lib.RedisError as exc:
        raise _cart_unavailable(exc) from exc
    if not ok:
        raise HTTPException(status_code=404, detail='Ítem no encontrado en el carrito.')

    try:
        ttl = rcs.ttl_restante(r, current_user.id)
    except redis_lib.RedisError as exc:
        raise _cart_unavailable(exc) from exc
    return {'mensaje': 'Cantidad actualizada.', 'ttl_segundos': ttl}


# ── DELETE /cart/items/{oferta_id} ────────────────────────────────────────────


@router.delete('/items/{oferta_id}', status_code=204)
def eliminar_item(
    oferta_id: int,
    current_user: Usuario = Depends(get_current_user),
    r: redis_lib.Redis = Depends(get_redis),
):
    try:
        ok = rcs.eliminar_item(r, current_user.id, oferta_id)
    except redis_lib.RedisError as exc:
        raise _cart_unavailable(exc) from exc
    if not ok:
        raise HTTPException(status_code=404, detail='Ítem no encontrado en el carrito.')


# ── DELETE /cart/ ─────────────────────────────────────────────────────────────


@router.delete('/', status_code=204)
def vaciar_carrito(
    current_user: Usuario = Depends(get_current_user),
    r: redis_lib.Redis = Depends(get_redis),
):
    try:
        rcs.vaciar_carrito(r, current_user.id)
    except redis_lib.RedisError as exc:
        raise _cart_unavailable(exc) from exc
