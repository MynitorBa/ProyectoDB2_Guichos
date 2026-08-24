"""Transactional outbox MySQL -> proyecciones e historial MongoDB."""

import logging
import threading
import uuid
from datetime import datetime, timedelta, timezone

from bson import ObjectId
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.core.db_mongo import get_mongo_db
from app.core.db_mysql import SessionLocal
from app.models.outbox import OutboxEvento


logger = logging.getLogger(__name__)
MAX_ATTEMPTS = 5
POLL_SECONDS = 1.0
_stop_event = threading.Event()
_worker_thread: threading.Thread | None = None


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def enqueue_outbox(
    db: Session,
    *,
    tipo_evento: str,
    agregado_tipo: str,
    agregado_id: str | int,
    producto_ref: str | None,
    payload: dict,
) -> OutboxEvento:
    """Agrega el mensaje a la transacción SQL actual; no hace commit."""
    event = OutboxEvento(
        id=str(uuid.uuid4()),
        tipo_evento=tipo_evento,
        agregado_tipo=agregado_tipo,
        agregado_id=str(agregado_id),
        producto_ref=producto_ref,
        payload=payload,
        estado='pendiente',
        intentos=0,
    )
    db.add(event)
    return event


def _append_history_idempotent(mongo, event: OutboxEvento, history: dict) -> None:
    if mongo.producto_eventos.find_one({'outbox_id': event.id}, {'_id': 1}):
        return
    latest = mongo.producto_eventos.find_one(
        {'producto_id': event.producto_ref},
        sort=[('version', -1)],
        projection={'version': 1},
    )
    version = int(latest.get('version', 0) if latest else 0) + 1
    mongo.producto_eventos.update_one(
        {'outbox_id': event.id},
        {'$setOnInsert': {
            'outbox_id': event.id,
            'producto_id': event.producto_ref,
            'tipo_evento': history['tipo_evento'],
            'datos_anteriores': history.get('datos_anteriores', {}),
            'datos_nuevos': history.get('datos_nuevos', {}),
            'usuario_id': history.get('usuario_id'),
            'timestamp': _now(),
            'version': version,
        }},
        upsert=True,
    )


def project_event(event: OutboxEvento) -> None:
    """Operaciones idempotentes: `$set` y upsert por `outbox_id`."""
    if not event.producto_ref:
        return
    mongo = get_mongo_db()
    projection = event.payload.get('projection', {})
    result = mongo.productos.update_one(
        {'_id': ObjectId(event.producto_ref)},
        {'$set': projection},
    )
    if result.matched_count != 1:
        raise RuntimeError(
            f'No existe producto MongoDB {event.producto_ref} para evento {event.id}'
        )
    history = event.payload.get('history')
    if history:
        _append_history_idempotent(mongo, event, history)


def _claim_one() -> str | None:
    retry_before = _now() - timedelta(seconds=2)
    with SessionLocal() as db:
        event = (
            db.execute(
                select(OutboxEvento)
                .where(
                    OutboxEvento.intentos < MAX_ATTEMPTS,
                    or_(
                        OutboxEvento.estado == 'pendiente',
                        and_(
                            OutboxEvento.estado == 'error',
                            OutboxEvento.procesado_en <= retry_before,
                        ),
                    ),
                )
                .order_by(OutboxEvento.creado_en, OutboxEvento.id)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            .scalars()
            .first()
        )
        if not event:
            return None
        event.estado = 'procesando'
        event.intentos += 1
        event.procesado_en = _now()  # también funciona como instante de claim
        event.ultimo_error = None
        event_id = event.id
        db.commit()
        return event_id


def process_one() -> bool:
    event_id = _claim_one()
    if not event_id:
        return False
    try:
        with SessionLocal() as db:
            event = db.get(OutboxEvento, event_id)
            if not event:
                return True
            # El objeto permanece utilizable durante esta sesión.
            project_event(event)
        with SessionLocal() as db:
            event = db.get(OutboxEvento, event_id)
            if event:
                event.estado = 'procesado'
                event.procesado_en = _now()
                event.ultimo_error = None
                db.commit()
    except Exception as exc:
        logger.exception('Error procesando outbox %s', event_id)
        with SessionLocal() as db:
            event = db.get(OutboxEvento, event_id)
            if event:
                event.estado = 'error'
                event.procesado_en = _now()
                event.ultimo_error = str(exc)[:4000]
                db.commit()
    return True


def process_batch(limit: int = 20) -> int:
    processed = 0
    for _ in range(limit):
        if not process_one():
            break
        processed += 1
    return processed


def _recover_stale_claims() -> None:
    threshold = _now() - timedelta(minutes=5)
    with SessionLocal() as db:
        rows = db.query(OutboxEvento).filter(
            OutboxEvento.estado == 'procesando',
            OutboxEvento.procesado_en < threshold,
        ).all()
        for event in rows:
            event.estado = 'pendiente'
            event.procesado_en = None
        if rows:
            db.commit()


def _worker_loop() -> None:
    _recover_stale_claims()
    while not _stop_event.is_set():
        processed = process_batch()
        if not processed:
            _stop_event.wait(POLL_SECONDS)


def start_outbox_worker() -> None:
    global _worker_thread
    if _worker_thread and _worker_thread.is_alive():
        return
    _stop_event.clear()
    _worker_thread = threading.Thread(
        target=_worker_loop,
        name='tiendaya-outbox',
        daemon=True,
    )
    _worker_thread.start()


def stop_outbox_worker() -> None:
    global _worker_thread
    _stop_event.set()
    if _worker_thread and _worker_thread.is_alive():
        _worker_thread.join(timeout=5)
    _worker_thread = None
