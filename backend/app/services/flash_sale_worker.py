"""Reconciliación periódica de reservas vencidas y promociones finalizadas."""

import logging
import threading
import time

import redis as redis_lib

from app.core.db_mysql import SessionLocal
from app.core.db_redis import get_redis
from app.core.time import utc_now
from app.models.inventario import Inventario, MovimientoInventario
from app.models.promocion_flash import PromocionFlash, ReservaFlash
from app.services import flash_sale_service as flash
from app.services.offer_history_service import registrar_saldo_inventario
from app.services.offer_service import enqueue_primary_offer_projection
from app.models.oferta import Oferta

logger = logging.getLogger(__name__)
_stop = threading.Event()
_thread: threading.Thread | None = None


def reconcile_once() -> int:
    now = utc_now()
    now_ts = int(time.time())
    processed = 0
    r = get_redis()
    with SessionLocal() as db:
        promotions = db.query(PromocionFlash).filter(
            PromocionFlash.estado.in_(['programada', 'activa'])
        ).all()
        for row in promotions:
            if row.estado == 'programada' and row.inicia_en <= now < row.finaliza_en:
                row.estado = 'activa'
                row.version += 1
                processed += 1

            active_reservations = db.query(ReservaFlash).filter(
                ReservaFlash.promocion_id == row.id,
                ReservaFlash.estado == 'reservada',
                ReservaFlash.expira_en > now,
            ).all()
            try:
                flash.rehidratar_si_falta(r, row, active_reservations)
                flash.limpiar_expiradas(r, row.id, now_ts)
            except redis_lib.RedisError:
                # MySQL debe poder cerrar la promoción aunque Redis esté caído.
                logger.warning('Redis no disponible al reconciliar promoción flash %s', row.id)
            expired = db.query(ReservaFlash).filter(
                ReservaFlash.promocion_id == row.id,
                ReservaFlash.estado == 'reservada',
                ReservaFlash.expira_en <= now,
            ).update({'estado': 'expirada'}, synchronize_session=False)
            processed += expired

            if now < row.finaliza_en:
                continue
            promotion = db.query(PromocionFlash).filter_by(id=row.id).with_for_update().one()
            if promotion.estado not in {'programada', 'activa'}:
                continue
            inventory = db.query(Inventario).filter_by(
                oferta_id=promotion.oferta_id, bodega='principal'
            ).with_for_update().one()
            remaining = max(0, promotion.unidades_totales - promotion.unidades_vendidas)
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
                    motivo=f'Fin promoción flash #{promotion.id}',
                    usuario_id=promotion.creado_por,
                ))
                registrar_saldo_inventario(
                    db, inventario=inventory, usuario_id=promotion.creado_por,
                    motivo=f'Fin promoción flash #{promotion.id}',
                )
            offer = db.get(Oferta, promotion.oferta_id)
            if offer:
                enqueue_primary_offer_projection(db, offer.producto_ref, offer.id)
            try:
                flash.cerrar(r, promotion.id)
            except redis_lib.RedisError:
                logger.warning('Redis no disponible al cerrar promoción flash %s', promotion.id)
            processed += 1
        db.commit()
    return processed


def _loop() -> None:
    while not _stop.is_set():
        try:
            reconcile_once()
        except Exception:
            logger.exception('Error reconciliando promociones flash')
        _stop.wait(1.0)


def start_flash_worker() -> None:
    global _thread
    if _thread and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_loop, name='tiendaya-flash-sales', daemon=True)
    _thread.start()


def stop_flash_worker() -> None:
    global _thread
    _stop.set()
    if _thread and _thread.is_alive():
        _thread.join(timeout=5)
    _thread = None
