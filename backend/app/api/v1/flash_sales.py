import time
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import redis as redis_lib
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.db_mysql import get_db
from app.core.db_redis import get_redis
from app.core.deps import get_current_user, require_role
from app.core.time import utc_now
from app.models.inventario import Inventario, MovimientoInventario
from app.models.oferta import Oferta
from app.models.promocion_flash import PromocionFlash, ReservaFlash
from app.models.usuario import Usuario
from app.models.vendedor import Vendedor
from app.services import flash_sale_service as flash
from app.services import redis_cart_service as carts
from app.services.offer_history_service import registrar_saldo_inventario
from app.services.offer_service import enqueue_primary_offer_projection

router = APIRouter(prefix='/flash-sales', tags=['Ventas flash'])
vendor_router = APIRouter(prefix='/vendor/flash-sales', tags=['Vendedor - ventas flash'])
get_vendor_user = require_role('vendedor', 'administrador')


class FlashCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    oferta_id: int
    precio_promocional: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    unidades: int = Field(gt=0, le=2147483647, strict=True)
    inicia_en: datetime
    finaliza_en: datetime


class FlashReserve(BaseModel):
    cantidad: int = Field(default=1, ge=1, le=1, strict=True)


def _naive_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _vendor(db: Session, user: Usuario) -> Vendedor:
    vendor = db.query(Vendedor).filter_by(usuario_id=user.id).first()
    if not vendor or vendor.estado_verificacion != 'verificado':
        raise HTTPException(403, 'Necesitas un perfil de vendedor verificado.')
    return vendor


def _delete_redis_safely(r: redis_lib.Redis, promotion_id: int) -> None:
    try:
        flash.eliminar(r, promotion_id)
    except redis_lib.RedisError:
        pass


def _finish_if_needed(db: Session, r: redis_lib.Redis, promotion: PromocionFlash) -> None:
    now = utc_now()
    if promotion.estado == 'programada' and promotion.inicia_en <= now < promotion.finaliza_en:
        promotion.estado = 'activa'
        promotion.version += 1
        db.commit()
    if promotion.estado not in {'programada', 'activa'} or now < promotion.finaliza_en:
        return
    promotion = db.query(PromocionFlash).filter_by(id=promotion.id).with_for_update().one()
    if promotion.estado not in {'programada', 'activa'}:
        db.rollback()
        return
    remaining = max(0, promotion.unidades_totales - promotion.unidades_vendidas)
    inventory = db.query(Inventario).filter_by(
        oferta_id=promotion.oferta_id, bodega='principal'
    ).with_for_update().one()
    release = min(remaining, inventory.cantidad_reservada)
    inventory.cantidad_reservada -= release
    promotion.estado = 'finalizada'
    promotion.version += 1
    db.query(ReservaFlash).filter_by(
        promocion_id=promotion.id, estado='reservada'
    ).update({'estado': 'expirada'}, synchronize_session=False)
    if release:
        db.add(MovimientoInventario(
            inventario_id=inventory.id, tipo='liberacion', cantidad=release,
            motivo=f'Fin promoción flash #{promotion.id}', usuario_id=promotion.creado_por,
        ))
        registrar_saldo_inventario(
            db, inventario=inventory, usuario_id=promotion.creado_por,
            motivo=f'Fin promoción flash #{promotion.id}',
        )
    offer = db.get(Oferta, promotion.oferta_id)
    if offer:
        enqueue_primary_offer_projection(db, offer.producto_ref, offer.id)
    db.commit()
    try:
        flash.cerrar(r, promotion.id)
    except redis_lib.RedisError:
        pass


def _ensure_redis_state(db: Session, r: redis_lib.Redis, promotion: PromocionFlash) -> None:
    if promotion.estado not in {'programada', 'activa'}:
        return
    reservations = db.query(ReservaFlash).filter(
        ReservaFlash.promocion_id == promotion.id,
        ReservaFlash.estado == 'reservada',
        ReservaFlash.expira_en > utc_now(),
    ).all()
    try:
        flash.rehidratar_si_falta(r, promotion, reservations)
    except redis_lib.RedisError as exc:
        raise HTTPException(503, 'Las ventas flash no están disponibles temporalmente.') from exc


def _serialize(db: Session, r: redis_lib.Redis, promotion: PromocionFlash) -> dict:
    _finish_if_needed(db, r, promotion)
    _ensure_redis_state(db, r, promotion)
    now_ts = int(time.time())
    if promotion.estado in {'programada', 'activa'}:
        try:
            flash.limpiar_expiradas(r, promotion.id, now_ts)
        except redis_lib.RedisError as exc:
            raise HTTPException(503, 'Las ventas flash no están disponibles temporalmente.') from exc
        db.query(ReservaFlash).filter(
            ReservaFlash.promocion_id == promotion.id,
            ReservaFlash.estado == 'reservada',
            ReservaFlash.expira_en <= utc_now(),
        ).update({'estado': 'expirada'}, synchronize_session=False)
        db.commit()
    try:
        state = flash.obtener_estado(r, promotion.id)
    except redis_lib.RedisError as exc:
        raise HTTPException(503, 'Las ventas flash no están disponibles temporalmente.') from exc
    offer = db.get(Oferta, promotion.oferta_id)
    vendor = db.get(Vendedor, offer.vendedor_id) if offer else None
    return {
        'id': promotion.id,
        'oferta_id': promotion.oferta_id,
        'vendedor_id': vendor.id if vendor else None,
        'vendedor_nombre': vendor.nombre_comercial if vendor else 'Vendedor',
        'precio_normal': float(offer.precio_actual) if offer else None,
        'precio_promocional': float(promotion.precio_promocional),
        'unidades_totales': promotion.unidades_totales,
        'unidades_vendidas': promotion.unidades_vendidas,
        'unidades_disponibles': state.get(
            'disponibles', max(0, promotion.unidades_totales - promotion.unidades_vendidas)
        ),
        'max_por_usuario': promotion.max_por_usuario,
        'segundos_reserva': promotion.segundos_reserva,
        'inicia_en': promotion.inicia_en.isoformat(),
        'finaliza_en': promotion.finaliza_en.isoformat(),
        'estado': promotion.estado,
        'version': promotion.version,
    }


@vendor_router.post('', status_code=201)
def create_flash_sale(
    payload: FlashCreate,
    user: Usuario = Depends(get_vendor_user),
    db: Session = Depends(get_db),
    r: redis_lib.Redis = Depends(get_redis),
):
    vendor = _vendor(db, user)
    starts = _naive_utc(payload.inicia_en)
    ends = _naive_utc(payload.finaliza_en)
    now = utc_now()
    if ends <= starts or ends <= now:
        raise HTTPException(422, 'El período de la promoción no es válido.')
    offer = db.query(Oferta).filter_by(
        id=payload.oferta_id, vendedor_id=vendor.id, estado='activa'
    ).with_for_update().first()
    if not offer:
        raise HTTPException(404, 'No existe una oferta activa propia con ese id.')
    if payload.precio_promocional >= offer.precio_actual:
        raise HTTPException(422, 'El precio flash debe ser menor que el precio normal.')
    inventory = db.query(Inventario).filter_by(
        oferta_id=offer.id, bodega='principal'
    ).with_for_update().first()
    available = (
        inventory.cantidad_disponible - inventory.cantidad_reservada if inventory else 0
    )
    if available < payload.unidades:
        raise HTTPException(409, f'Solo hay {available} unidades libres para apartar.')

    promotion = PromocionFlash(
        oferta_id=offer.id,
        creado_por=user.id,
        precio_promocional=payload.precio_promocional,
        unidades_totales=payload.unidades,
        unidades_vendidas=0,
        max_por_usuario=1,
        segundos_reserva=300,
        inicia_en=starts,
        finaliza_en=ends,
        estado='activa' if starts <= now else 'programada',
    )
    db.add(promotion)
    inventory.cantidad_reservada += payload.unidades
    redis_initialized = False
    try:
        db.flush()
        db.add(MovimientoInventario(
            inventario_id=inventory.id, tipo='reserva', cantidad=payload.unidades,
            motivo=f'Promoción flash #{promotion.id}', usuario_id=user.id,
        ))
        registrar_saldo_inventario(
            db, inventario=inventory, usuario_id=user.id,
            motivo=f'Promoción flash #{promotion.id}',
        )
        enqueue_primary_offer_projection(db, offer.producto_ref, offer.id)
        flash.inicializar(
            r,
            promocion_id=promotion.id,
            unidades=payload.unidades,
            max_por_usuario=1,
            inicia_ts=int(starts.replace(tzinfo=timezone.utc).timestamp()),
            finaliza_ts=int(ends.replace(tzinfo=timezone.utc).timestamp()),
            precio=payload.precio_promocional,
        )
        redis_initialized = True
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if redis_initialized and promotion.id:
            _delete_redis_safely(r, promotion.id)
        raise HTTPException(409, 'Esta oferta ya tiene una promoción vigente.') from exc
    except redis_lib.RedisError as exc:
        db.rollback()
        if promotion.id:
            _delete_redis_safely(r, promotion.id)
        raise HTTPException(503, 'Redis no está disponible; no se creó la promoción.') from exc
    except SQLAlchemyError:
        db.rollback()
        if redis_initialized and promotion.id:
            _delete_redis_safely(r, promotion.id)
        raise
    return _serialize(db, r, promotion)


@vendor_router.get('')
def list_own_flash_sales(
    user: Usuario = Depends(get_vendor_user),
    db: Session = Depends(get_db),
    r: redis_lib.Redis = Depends(get_redis),
):
    vendor = _vendor(db, user)
    rows = db.query(PromocionFlash).join(Oferta).filter(
        Oferta.vendedor_id == vendor.id
    ).order_by(PromocionFlash.id.desc()).all()
    return [_serialize(db, r, row) for row in rows]


@router.get('/active')
def active_flash_sales(
    oferta_id: int | None = Query(None),
    db: Session = Depends(get_db),
    r: redis_lib.Redis = Depends(get_redis),
):
    query = db.query(PromocionFlash).filter(
        PromocionFlash.estado.in_(['programada', 'activa'])
    )
    if oferta_id is not None:
        query = query.filter(PromocionFlash.oferta_id == oferta_id)
    rows = query.order_by(PromocionFlash.finaliza_en).all()
    result = [_serialize(db, r, row) for row in rows]
    now = utc_now()
    return [item for item, row in zip(result, rows) if row.inicia_en <= now < row.finaliza_en and item['estado'] == 'activa']


@router.post('/{promotion_id}/reserve', status_code=201)
def reserve_flash_sale(
    promotion_id: int,
    payload: FlashReserve,
    user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
    r: redis_lib.Redis = Depends(get_redis),
):
    promotion = db.get(PromocionFlash, promotion_id)
    if not promotion:
        raise HTTPException(404, 'Promoción no encontrada.')
    _finish_if_needed(db, r, promotion)
    now = utc_now()
    if promotion.estado not in {'programada', 'activa'} or not (
        promotion.inicia_en <= now < promotion.finaliza_en
    ):
        raise HTTPException(409, 'La promoción no está activa.')
    _ensure_redis_state(db, r, promotion)
    offer = db.get(Oferta, promotion.oferta_id)
    token = str(uuid4())
    try:
        result = flash.reservar(
            r,
            promocion_id=promotion.id,
            usuario_id=user.id,
            cantidad=payload.cantidad,
            token=token,
            ahora_ts=int(time.time()),
            segundos_reserva=promotion.segundos_reserva,
        )
    except redis_lib.RedisError as exc:
        raise HTTPException(503, 'Las ventas flash no están disponibles temporalmente.') from exc
    if result['codigo'] == 0:
        raise HTTPException(409, 'Las unidades promocionales se agotaron.')
    if result['codigo'] == -1:
        raise HTTPException(409, 'La promoción no está activa.')
    if result['codigo'] == -2:
        raise HTTPException(422, 'Solo puedes reservar una unidad promocional.')

    if result['codigo'] == 2:
        reservation = db.query(ReservaFlash).filter_by(
            promocion_id=promotion.id, usuario_id=user.id, estado='reservada'
        ).first()
        if not reservation:
            flash.liberar(r, promotion.id, user.id, result['token'])
            raise HTTPException(409, 'La reserva anterior no pudo recuperarse; intenta nuevamente.')
    else:
        db.query(ReservaFlash).filter(
            ReservaFlash.promocion_id == promotion.id,
            ReservaFlash.usuario_id == user.id,
            ReservaFlash.estado == 'reservada',
            ReservaFlash.expira_en <= utc_now(),
        ).update({'estado': 'expirada'}, synchronize_session=False)
        reservation = ReservaFlash(
            token=result['token'], promocion_id=promotion.id, usuario_id=user.id,
            cantidad=payload.cantidad, precio_unitario=promotion.precio_promocional,
            expira_en=datetime.fromtimestamp(result['expira_ts'], timezone.utc).replace(tzinfo=None),
        )
        db.add(reservation)
        try:
            db.commit()
        except Exception:
            db.rollback()
            flash.liberar(r, promotion.id, user.id, result['token'])
            raise

    try:
        carts.establecer_item_flash(
            r, user.id, offer.id, reservation.cantidad,
            promotion.precio_promocional, offer.producto_ref,
            promotion.id, reservation.token,
        )
    except redis_lib.RedisError as exc:
        flash.liberar(r, promotion.id, user.id, reservation.token)
        reservation.estado = 'cancelada'
        db.commit()
        raise HTTPException(503, 'No se pudo agregar la reserva al carrito.') from exc

    return {
        'token': reservation.token,
        'promocion_id': promotion.id,
        'oferta_id': offer.id,
        'precio': float(promotion.precio_promocional),
        'cantidad': reservation.cantidad,
        'expira_en': reservation.expira_en.isoformat(),
        'unidades_disponibles': result['disponibles'],
    }


@vendor_router.post('/{promotion_id}/cancel')
def cancel_flash_sale(
    promotion_id: int,
    user: Usuario = Depends(get_vendor_user),
    db: Session = Depends(get_db),
    r: redis_lib.Redis = Depends(get_redis),
):
    vendor = _vendor(db, user)
    promotion = db.query(PromocionFlash).join(Oferta).filter(
        PromocionFlash.id == promotion_id,
        Oferta.vendedor_id == vendor.id,
    ).with_for_update().first()
    if not promotion:
        raise HTTPException(404, 'Promoción no encontrada o sin permiso.')
    if promotion.estado not in {'programada', 'activa'}:
        raise HTTPException(409, 'La promoción ya no se puede cancelar.')
    inventory = db.query(Inventario).filter_by(
        oferta_id=promotion.oferta_id, bodega='principal'
    ).with_for_update().one()
    remaining = max(0, promotion.unidades_totales - promotion.unidades_vendidas)
    release = min(remaining, inventory.cantidad_reservada)
    inventory.cantidad_reservada -= release
    promotion.estado = 'cancelada'
    promotion.version += 1
    db.query(ReservaFlash).filter_by(
        promocion_id=promotion.id, estado='reservada'
    ).update({'estado': 'cancelada'}, synchronize_session=False)
    if release:
        db.add(MovimientoInventario(
            inventario_id=inventory.id, tipo='liberacion', cantidad=release,
            motivo=f'Cancelación promoción flash #{promotion.id}', usuario_id=user.id,
        ))
        registrar_saldo_inventario(
            db, inventario=inventory, usuario_id=user.id,
            motivo=f'Cancelación promoción flash #{promotion.id}',
        )
    offer = db.get(Oferta, promotion.oferta_id)
    enqueue_primary_offer_projection(db, offer.producto_ref, offer.id)
    db.commit()
    try:
        flash.eliminar(r, promotion.id)
    except redis_lib.RedisError:
        pass
    return {'id': promotion.id, 'estado': promotion.estado, 'unidades_liberadas': release}
