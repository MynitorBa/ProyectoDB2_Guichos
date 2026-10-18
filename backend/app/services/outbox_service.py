"""Transactional outbox: MySQL -> MongoDB, Elasticsearch, Cassandra, Neo4j y Redis.

Garantías:

- **Atomicidad con el negocio.** ``enqueue_outbox`` agrega filas a la
  transacción SQL en curso; si la operación hace rollback, el evento tampoco
  existe.
- **Una fila por destino.** Cada evento se encola una vez por componente que
  debe enterarse (ver ``RUTAS``). La caída de un componente no retrasa a los
  demás.
- **Idempotencia.** Cada manejador puede ejecutarse varias veces con el mismo
  resultado. Las proyecciones de MongoDB y Elasticsearch se recalculan desde el
  estado actual de MySQL (no aplican el delta del evento), por lo que tampoco
  dependen del orden de procesamiento.
- **Reintentos escalonados.** Ante un error, el evento espera
  ``min(2^intentos, 300)`` segundos; tras ``MAX_ATTEMPTS`` queda ``fallido``
  y solo se reintenta de forma manual (panel administrativo).
"""

import logging
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone

from bson import ObjectId
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.core.db_mongo import get_mongo_db
from app.core.db_mysql import SessionLocal
from app.core.fault_injection import punto_de_falla
from app.models.outbox import DESTINOS_OUTBOX, OutboxEvento


logger = logging.getLogger(__name__)
MAX_ATTEMPTS = 10
BACKOFF_MAXIMO_SEGUNDOS = 300
PAUSA_MAXIMA_DESTINO_SEGUNDOS = 30
POLL_SECONDS = 1.0
RECONCILIAR_BUSQUEDA_SEGUNDOS = 600
_stop_event = threading.Event()

# Destinos que deben recibir cada tipo de evento. Un tipo no listado se
# proyecta solo hacia MongoDB (comportamiento histórico del outbox).
RUTAS: dict[str, tuple[str, ...]] = {
    'inventario.actualizado': ('mongo', 'busqueda'),
    'inventario.reconciliado': ('mongo', 'busqueda'),
    'oferta.precio_actualizado': ('mongo', 'busqueda', 'neo4j'),
    'oferta.estado_actualizado': ('mongo', 'busqueda', 'neo4j'),
    'oferta.vendedor_actualizado': ('mongo', 'busqueda', 'neo4j'),
    'producto.oferta_principal_actualizada': ('mongo', 'busqueda', 'neo4j'),
    'producto.catalogo_actualizado': ('busqueda',),
    'flash.estado_cambiado': ('busqueda',),
    'analytics.pedido_actualizado': ('cassandra', 'busqueda'),
    'grafo.compra_registrada': ('neo4j',),
    'grafo.pedido_actualizado': ('neo4j',),
    'resena.creada': ('neo4j', 'busqueda'),
    'resena.actualizada': ('neo4j', 'busqueda'),
    'resena.moderada': ('neo4j', 'busqueda'),
    'resena.respuesta_creada': ('neo4j',),
    'carrito.limpiar': ('redis',),
    'flash.consumir': ('redis',),
}

# Pausa temporal por destino tras una falla: evita que el único hilo del worker
# gaste su tiempo en timeouts contra un componente caído mientras los demás
# destinos tienen trabajo pendiente.
_pausas: dict[str, float] = {}


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def destinos_de(tipo_evento: str) -> tuple[str, ...]:
    return RUTAS.get(tipo_evento, ('mongo',))


def enqueue_outbox(
    db: Session,
    *,
    tipo_evento: str,
    agregado_tipo: str,
    agregado_id: str | int,
    producto_ref: str | None,
    payload: dict,
    destinos: tuple[str, ...] | None = None,
) -> OutboxEvento:
    """Agrega una fila por destino a la transacción SQL actual; no hace commit.

    Devuelve la primera fila creada.
    """
    eventos = []
    for destino in destinos or destinos_de(tipo_evento):
        if destino not in DESTINOS_OUTBOX:
            raise ValueError(f'Destino de outbox desconocido: {destino}')
        evento = OutboxEvento(
            id=str(uuid.uuid4()),
            tipo_evento=tipo_evento,
            destino=destino,
            agregado_tipo=agregado_tipo,
            agregado_id=str(agregado_id),
            producto_ref=producto_ref,
            payload=payload,
            estado='pendiente',
            intentos=0,
        )
        db.add(evento)
        eventos.append(evento)
    return eventos[0]


def encolar_reindexado(db: Session, producto_ref: str, motivo: str) -> None:
    """Pide reindexar un producto cuyo contenido de catálogo cambió."""
    enqueue_outbox(
        db,
        tipo_evento='producto.catalogo_actualizado',
        agregado_tipo='producto',
        agregado_id=producto_ref,
        producto_ref=producto_ref,
        payload={'motivo': motivo},
    )


def encolar_resena(
    db: Session, *, tipo_evento: str, resena_id: int,
    producto_ref: str, payload: dict | None = None,
) -> None:
    enqueue_outbox(
        db, tipo_evento=tipo_evento, agregado_tipo='resena',
        agregado_id=resena_id, producto_ref=producto_ref, payload=payload or {},
    )


# ── Manejadores por destino ───────────────────────────────────────────────────

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


def _proyectar_mongo(event: OutboxEvento, db: Session) -> None:
    if not event.producto_ref:
        return
    from app.services.offer_service import proyeccion_oferta_principal

    mongo = get_mongo_db()
    # Estado actual, no el delta del evento: corrige cualquier proyección
    # previa incompleta y hace irrelevante el orden de llegada.
    projection = proyeccion_oferta_principal(db, event.producto_ref)
    result = mongo.productos.update_one(
        {'_id': ObjectId(event.producto_ref)},
        {'$set': projection},
    )
    if result.matched_count != 1:
        raise RuntimeError(
            f'No existe producto MongoDB {event.producto_ref} para evento {event.id}'
        )
    history = (event.payload or {}).get('history')
    if history:
        _append_history_idempotent(mongo, event, history)


def _refs_del_evento(event: OutboxEvento, db: Session) -> list[str]:
    if event.producto_ref:
        return [event.producto_ref]
    if event.agregado_tipo == 'pedido':
        from app.models.pedido import PedidoLinea

        filas = db.query(PedidoLinea.producto_ref).filter(
            PedidoLinea.pedido_id == int(event.agregado_id)
        ).distinct().all()
        return [ref for (ref,) in filas if ref]
    return []


def _neo4j_opcional():
    try:
        from app.core.db_neo4j import get_driver
        return get_driver()
    except Exception as exc:  # El rating es opcional; el índice no espera a Neo4j.
        logger.warning('Indexado sin rating: Neo4j no disponible (%s)', exc)
        return None


def _proyectar_busqueda(event: OutboxEvento, db: Session) -> None:
    refs = _refs_del_evento(event, db)
    if not refs:
        return
    from app.core.db_elastic import get_es
    from app.services.search_index_service import indexar_productos

    indexar_productos(get_es(), db, get_mongo_db(), refs, _neo4j_opcional())


def _proyectar_cassandra(event: OutboxEvento, db: Session) -> None:
    from app.services.analytics_service import project_order

    project_order(int(event.agregado_id))


def _proyectar_neo4j(event: OutboxEvento, db: Session) -> None:
    """Proyecta compras o reseñas desde la autoridad MySQL."""
    from app.core.db_neo4j import get_driver
    if event.agregado_tipo == 'resena':
        from app.services.review_service import proyectar_resena_mysql

        with get_driver().session() as s:
            proyectar_resena_mysql(s, db, int(event.agregado_id))
        return
    from app.models.pedido import Pedido, PedidoLinea
    from app.models.pedido_vendedor import PedidoVendedor
    from app.models.oferta import Oferta
    from app.models.producto_variante_referencia import ProductoVarianteReferencia
    from app.models.usuario import Usuario
    from app.models.vendedor import Vendedor
    from app.services.review_service import (
        ensure_producto, ensure_usuario, ensure_vendedor, proyectar_oferta,
        registrar_compra,
    )

    if event.agregado_tipo == 'oferta':
        offer = db.get(Oferta, int(event.agregado_id))
        if not offer:
            # La relación es una proyección reconstruible; si la autoridad ya
            # no contiene la oferta, retirar solo esa relación es idempotente.
            with get_driver().session() as s:
                s.run(
                    'MATCH ()-[o:OFRECE {oferta_id:$oferta_id}]->() DELETE o',
                    oferta_id=int(event.agregado_id),
                )
            return
        seller = db.get(Vendedor, offer.vendedor_id)
        variant = db.get(ProductoVarianteReferencia, offer.producto_variante_id)
        if not seller or not variant:
            raise RuntimeError(f'Oferta {offer.id} sin vendedor o variante canónica.')
        with get_driver().session() as s:
            proyectar_oferta(
                s, vendedor_id=seller.id,
                vendedor_nombre=seller.nombre_comercial,
                vendedor_usuario_id=seller.usuario_id,
                producto_ref=offer.producto_ref, oferta_id=offer.id,
                producto_variante_id=offer.producto_variante_id,
                variante_ref=variant.variante_ref, sku=offer.sku,
                estado=offer.estado,
            )
        return

    pedido = db.get(Pedido, int(event.agregado_id))
    if not pedido:
        raise RuntimeError(f'Pedido {event.agregado_id} inexistente para evento {event.id}')
    if pedido.estado in {'cancelado', 'reembolsado'} or not any(
        pago.estado == 'aprobado' for pago in pedido.pagos
    ):
        with get_driver().session() as s:
            s.run(
                'MATCH (c:Compra {pedido_id:$pedido_id}) DETACH DELETE c',
                pedido_id=pedido.id,
            )
        return
    usuario = db.get(Usuario, pedido.usuario_id)
    lineas = (
        db.query(PedidoLinea, Vendedor)
        .join(PedidoVendedor, PedidoVendedor.id == PedidoLinea.pedido_vendedor_id)
        .join(Vendedor, Vendedor.id == PedidoVendedor.vendedor_id)
        .filter(PedidoLinea.pedido_id == pedido.id)
        .all()
    )
    fecha = pedido.fecha_creacion.replace(tzinfo=timezone.utc).isoformat()
    from app.models.promocion_flash import PromocionFlash, ReservaFlash
    flash_by_offer = {
        offer_id: promo_id
        for offer_id, promo_id in (
            db.query(PromocionFlash.oferta_id, ReservaFlash.promocion_id)
            .join(ReservaFlash, ReservaFlash.promocion_id == PromocionFlash.id)
            .filter(
                ReservaFlash.pedido_id == pedido.id,
                ReservaFlash.estado == 'convertida',
            )
            .all()
        )
    }
    with get_driver().session() as s:
        ensure_usuario(s, usuario.id, f'{usuario.nombre} {usuario.apellido}'.strip(), usuario.email)
        for linea, vendedor in lineas:
            if not linea.producto_ref:
                continue
            ensure_producto(s, linea.producto_ref, linea.producto_nombre)
            ensure_vendedor(s, vendedor.id, vendedor.nombre_comercial)
            offer = db.get(Oferta, linea.oferta_id)
            variant = (
                db.get(ProductoVarianteReferencia, offer.producto_variante_id)
                if offer else None
            )
            if offer and variant:
                proyectar_oferta(
                    s, vendedor_id=vendedor.id,
                    vendedor_nombre=vendedor.nombre_comercial,
                    vendedor_usuario_id=vendedor.usuario_id,
                    producto_ref=linea.producto_ref, oferta_id=offer.id,
                    producto_variante_id=offer.producto_variante_id,
                    variante_ref=variant.variante_ref, sku=offer.sku,
                    estado=offer.estado,
                )
            registrar_compra(
                s, usuario.id, linea.producto_ref, pedido.id, linea.oferta_id, fecha,
                linea_id=linea.id, vendedor_id=vendedor.id,
                cantidad=linea.cantidad,
                precio_unitario=float(linea.precio_unitario),
                sku=linea.sku_snapshot,
                promocion_flash_id=flash_by_offer.get(linea.oferta_id),
            )


def _proyectar_redis(event: OutboxEvento, db: Session) -> None:
    from app.core.db_redis import get_redis

    r = get_redis()
    payload = event.payload or {}
    if event.tipo_evento == 'carrito.limpiar':
        from app.services import redis_cart_service as rcs

        # Solo las ofertas compradas: lo agregado después del pedido se conserva.
        for oferta_id in payload.get('oferta_ids', []):
            rcs.eliminar_item(r, int(payload['usuario_id']), int(oferta_id))
    elif event.tipo_evento == 'flash.consumir':
        from app.services import flash_sale_service as flash

        # El script Lua devuelve False si la reserva ya no estaba: idempotente.
        flash.consumir(
            r, int(payload['promocion_id']), int(payload['usuario_id']), payload['token']
        )


MANEJADORES = {
    'mongo': _proyectar_mongo,
    'busqueda': _proyectar_busqueda,
    'cassandra': _proyectar_cassandra,
    'neo4j': _proyectar_neo4j,
    'redis': _proyectar_redis,
}


def project_event(event: OutboxEvento, db: Session | None = None) -> None:
    """Aplica un evento en su destino. Repetirlo produce el mismo resultado."""
    # Eventos sin destino explícito (anteriores a la migración 19) usan su ruta principal.
    destino = getattr(event, 'destino', None) or destinos_de(event.tipo_evento)[0]
    punto_de_falla(f'outbox.{destino}')
    manejador = MANEJADORES[destino]
    if db is not None:
        manejador(event, db)
        return
    with SessionLocal() as session:
        manejador(event, session)


# ── Worker ────────────────────────────────────────────────────────────────────

def backoff_segundos(intentos: int) -> int:
    return min(2 ** max(intentos, 0), BACKOFF_MAXIMO_SEGUNDOS)


def _destinos_en_pausa() -> list[str]:
    ahora = time.monotonic()
    return [destino for destino, hasta in _pausas.items() if hasta > ahora]


def _pausar(destino: str, intentos: int) -> None:
    _pausas[destino] = time.monotonic() + min(2 ** max(intentos, 0), PAUSA_MAXIMA_DESTINO_SEGUNDOS)


# Toma el evento más antiguo listo para procesar con SKIP LOCKED (sin doble proceso).
# Con ``destino`` solo considera los eventos de ese componente.
def _claim_one(destino: str | None = None) -> str | None:
    ahora = _now()
    pausados = _destinos_en_pausa()
    if destino is not None and destino in pausados:
        return None
    with SessionLocal() as db:
        query = (
            select(OutboxEvento)
            .where(
                OutboxEvento.intentos < MAX_ATTEMPTS,
                or_(
                    OutboxEvento.estado == 'pendiente',
                    and_(
                        OutboxEvento.estado == 'error',
                        or_(
                            OutboxEvento.siguiente_intento_en.is_(None),
                            OutboxEvento.siguiente_intento_en <= ahora,
                        ),
                    ),
                ),
            )
            .order_by(OutboxEvento.secuencia)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if destino is not None:
            query = query.where(OutboxEvento.destino == destino)
        elif pausados:
            query = query.where(OutboxEvento.destino.notin_(pausados))
        event = db.execute(query).scalars().first()
        if not event:
            return None
        event.estado = 'procesando'
        event.intentos += 1
        event.procesado_en = ahora  # también funciona como instante de claim
        event.ultimo_error = None
        event_id = event.id
        db.commit()
        return event_id


def process_one(destino_filtro: str | None = None) -> bool:
    event_id = _claim_one(destino_filtro)
    if not event_id:
        return False
    destino = None
    try:
        with SessionLocal() as db:
            event = db.get(OutboxEvento, event_id)
            if not event:
                return True
            destino = event.destino
            project_event(event, db)
        with SessionLocal() as db:
            event = db.get(OutboxEvento, event_id)
            if event:
                event.estado = 'procesado'
                event.procesado_en = _now()
                event.siguiente_intento_en = None
                event.ultimo_error = None
                db.commit()
        _pausas.pop(destino, None)
    except Exception as exc:
        logger.exception('Error procesando outbox %s (%s)', event_id, destino)
        with SessionLocal() as db:
            event = db.get(OutboxEvento, event_id)
            if event:
                agotado = event.intentos >= MAX_ATTEMPTS
                event.estado = 'fallido' if agotado else 'error'
                event.procesado_en = _now()
                event.siguiente_intento_en = (
                    None if agotado else _now() + timedelta(seconds=backoff_segundos(event.intentos))
                )
                event.ultimo_error = str(exc)[:4000]
                db.commit()
                if destino:
                    _pausar(destino, event.intentos)
    return True


def process_batch(limit: int = 20, destino: str | None = None) -> int:
    processed = 0
    for _ in range(limit):
        if not process_one(destino):
            break
        processed += 1
    return processed


# Devuelve a 'pendiente' los eventos que llevan más de 5 minutos en 'procesando' (crashes o reinicios)
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


def _reconciliar_busqueda() -> None:
    """Red de seguridad periódica para escrituras de catálogo sin evento."""
    from app.core.db_elastic import get_es
    from app.services.search_index_service import reconciliar_desfasados

    with SessionLocal() as db:
        resumen = reconciliar_desfasados(get_es(), db, get_mongo_db(), _neo4j_opcional())
    if resumen.get('indexados') or resumen.get('eliminados'):
        logger.info('Reconciliación del índice de búsqueda: %s', resumen)


def _worker_loop(destino: str) -> None:
    """Consumidor de un único destino.

    Cada componente tiene su propio hilo: si uno está caído, sus intentos
    esperan su timeout y su backoff sin retrasar a los demás destinos.
    SKIP LOCKED garantiza que dos consumidores nunca tomen el mismo evento.
    """
    reconcilia = destino == 'busqueda'
    proxima_reconciliacion = time.monotonic() + RECONCILIAR_BUSQUEDA_SEGUNDOS
    while not _stop_event.is_set():
        try:
            processed = process_batch(destino=destino)
        except Exception:  # p. ej. MySQL momentáneamente caído
            logger.exception('Error en el consumidor del outbox (%s)', destino)
            processed = 0
        if reconcilia and time.monotonic() >= proxima_reconciliacion:
            proxima_reconciliacion = time.monotonic() + RECONCILIAR_BUSQUEDA_SEGUNDOS
            try:
                _reconciliar_busqueda()
            except Exception as exc:
                logger.warning('No se pudo reconciliar el índice de búsqueda: %s', exc)
        if not processed:
            _stop_event.wait(POLL_SECONDS)


_worker_threads: dict[str, threading.Thread] = {}


# Arranca un consumidor por destino al iniciar la app; no duplica los que ya corren
def start_outbox_worker() -> None:
    _stop_event.clear()
    _recover_stale_claims()
    for destino in DESTINOS_OUTBOX:
        hilo = _worker_threads.get(destino)
        if hilo and hilo.is_alive():
            continue
        hilo = threading.Thread(
            target=_worker_loop, args=(destino,), name=f'tiendaya-outbox-{destino}', daemon=True,
        )
        _worker_threads[destino] = hilo
        hilo.start()


def stop_outbox_worker() -> None:
    _stop_event.set()
    for hilo in _worker_threads.values():
        if hilo.is_alive():
            hilo.join(timeout=5)
    _worker_threads.clear()


# ── Operación y observabilidad ────────────────────────────────────────────────

def resumen_por_destino(db: Session) -> list[dict]:
    """Conteos por destino y estado, más la antigüedad del pendiente más viejo."""
    conteos = db.query(
        OutboxEvento.destino, OutboxEvento.estado, func.count()
    ).group_by(OutboxEvento.destino, OutboxEvento.estado).all()
    mas_antiguos = dict(db.query(
        OutboxEvento.destino, func.min(OutboxEvento.creado_en)
    ).filter(
        OutboxEvento.estado.in_(['pendiente', 'procesando', 'error'])
    ).group_by(OutboxEvento.destino).all())

    ahora = _now()
    resumen = {
        destino: {
            'destino': destino,
            'pendiente': 0, 'procesando': 0, 'procesado': 0, 'error': 0, 'fallido': 0,
            'pendiente_mas_antiguo_segundos': None,
            'en_pausa': destino in _destinos_en_pausa(),
        }
        for destino in DESTINOS_OUTBOX
    }
    for destino, estado, total in conteos:
        resumen[destino][estado] = total
    for destino, creado_en in mas_antiguos.items():
        resumen[destino]['pendiente_mas_antiguo_segundos'] = round((ahora - creado_en).total_seconds(), 1)
    return list(resumen.values())


def listar_eventos(db: Session, *, estados: list[str], destino: str | None = None, limite: int = 50) -> list[dict]:
    query = db.query(OutboxEvento).filter(OutboxEvento.estado.in_(estados))
    if destino:
        query = query.filter(OutboxEvento.destino == destino)
    return [
        {
            'id': e.id,
            'secuencia': e.secuencia,
            'tipo_evento': e.tipo_evento,
            'destino': e.destino,
            'agregado': f'{e.agregado_tipo}:{e.agregado_id}',
            'producto_ref': e.producto_ref,
            'estado': e.estado,
            'intentos': e.intentos,
            'ultimo_error': e.ultimo_error,
            'creado_en': e.creado_en.isoformat() if e.creado_en else None,
            'siguiente_intento_en': e.siguiente_intento_en.isoformat() if e.siguiente_intento_en else None,
        }
        for e in query.order_by(OutboxEvento.secuencia.desc()).limit(limite)
    ]


def reintentar(db: Session, *, evento_id: str | None = None, destino: str | None = None) -> int:
    """Devuelve a 'pendiente' eventos en error o fallidos (todos o uno)."""
    query = db.query(OutboxEvento).filter(OutboxEvento.estado.in_(['error', 'fallido']))
    if evento_id:
        query = query.filter(OutboxEvento.id == evento_id)
    if destino:
        query = query.filter(OutboxEvento.destino == destino)
    filas = query.all()
    for evento in filas:
        evento.estado = 'pendiente'
        evento.intentos = 0
        evento.siguiente_intento_en = None
        evento.procesado_en = None
    if destino:
        _pausas.pop(destino, None)
    else:
        _pausas.clear()
    db.commit()
    return len(filas)
