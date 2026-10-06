"""Recuperación del checkout: cierra las sagas que quedaron a medias.

Dos tareas periódicas, ambas basadas en consultar la pasarela con la clave
idempotente del pago (la pasarela es la fuente de verdad sobre el cargo):

- **Reconciliador**: pagos ``en_verificacion`` (el cobro salió pero no hubo
  respuesta definitiva). Aprobado → confirma (o reembolsa si ya no es
  cumplible); rechazado → compensa; no existe → compensa tras un periodo de
  gracia; pasarela sin respuesta → espera al siguiente ciclo.
- **Recolector de reservas vencidas**: pedidos ``pendiente`` cuya reserva
  venció con el pago aún ``pendiente`` (el proceso cayó entre pasos). Se
  consulta la pasarela por si el cobro alcanzó a salir y se confirma,
  compensa o pasa a verificación.

Todas las transiciones son las mismas de ``checkout_service`` y están
protegidas por estado, así que este worker puede coincidir con una solicitud
en curso o con otra instancia sin duplicar efectos.
"""

from __future__ import annotations

import logging
import threading
from datetime import timedelta

from app.core.config import settings
from app.core.db_mysql import SessionLocal
from app.core.time import utc_now
from app.models.pago import Pago
from app.models.pedido import Pedido
from app.services import checkout_service as saga
from app.services import payment_gateway_client as pg

logger = logging.getLogger(__name__)
_stop = threading.Event()
_thread: threading.Thread | None = None


def _resolver(db, pedido_id: int, consulta: pg.ResultadoPasarela, pasarela, origen: str,
              *, compensar_si_no_existe: bool) -> str:
    """Aplica lo que dice la pasarela. Devuelve el desenlace o 'sin_cambios'."""
    if consulta.estado == pg.DESCONOCIDO:
        return 'sin_cambios'
    if consulta.estado == pg.NO_ENCONTRADO and not compensar_si_no_existe:
        return 'sin_cambios'
    # Solo se registra en la bitácora cuando la consulta lleva a actuar.
    saga.registrar_paso(db, pedido_id, origen, consulta.estado, {'referencia': consulta.referencia})
    db.commit()
    if consulta.estado == pg.NO_ENCONTRADO:
        saga.compensar_pedido(db, pedido_id, 'pago_no_recibido', origen=origen)
        return saga.NO_ENVIADO
    return saga.aplicar_resultado_cobro(db, pedido_id, consulta, pasarela, origen)


def reconciliar_pagos(db, pasarela: pg.PasarelaPagos, ahora=None) -> dict:
    ahora = ahora or utc_now()
    gracia = ahora - timedelta(seconds=settings.RECONCILIADOR_GRACIA_S)
    filas = (
        db.query(Pedido.id, Pedido.fecha_creacion, Pago.clave_idempotencia)
        .join(Pago, Pago.pedido_id == Pedido.id)
        .filter(Pedido.estado == 'pendiente', Pago.estado == 'en_verificacion')
        .order_by(Pedido.id)
        .all()
    )
    db.commit()
    resumen: dict[str, int] = {}
    for pedido_id, creado_en, clave in filas:
        consulta = pasarela.consultar(clave)
        desenlace = _resolver(
            db, pedido_id, consulta, pasarela, 'reconciliador',
            # Un cobro "no encontrado" recién creado puede seguir en tránsito.
            compensar_si_no_existe=creado_en <= gracia,
        )
        resumen[desenlace] = resumen.get(desenlace, 0) + 1
    return resumen


def recolectar_vencidos(db, pasarela: pg.PasarelaPagos, ahora=None) -> dict:
    ahora = ahora or utc_now()
    filas = (
        db.query(Pedido.id, Pago.clave_idempotencia, Pago.metodo_pago_id)
        .join(Pago, Pago.pedido_id == Pedido.id)
        .filter(
            Pedido.estado == 'pendiente',
            Pedido.reserva_expira_en.isnot(None),
            Pedido.reserva_expira_en < ahora,
            Pago.estado == 'pendiente',
        )
        .order_by(Pedido.id)
        .all()
    )
    db.commit()
    resumen: dict[str, int] = {}
    for pedido_id, clave, metodo_pago_id in filas:
        if saga.es_contra_entrega(db, metodo_pago_id):
            # No hay cobro que verificar: la caída fue antes de confirmar.
            saga.confirmar_pedido(db, pedido_id, origen='recolector')
            desenlace = saga.CONFIRMADO
        else:
            consulta = pasarela.consultar(clave)
            if consulta.estado == pg.DESCONOCIDO:
                # Sin respuesta de la pasarela: queda en manos del reconciliador.
                saga.marcar_en_verificacion(db, pedido_id, {'origen': 'recolector'})
                desenlace = saga.EN_VERIFICACION
            else:
                desenlace = _resolver(db, pedido_id, consulta, pasarela, 'recolector',
                                      compensar_si_no_existe=True)
        resumen[desenlace] = resumen.get(desenlace, 0) + 1
    return resumen


def reconcile_once(pasarela: pg.PasarelaPagos | None = None) -> dict:
    pasarela = pasarela or pg.get_pasarela()
    with SessionLocal() as db:
        return {
            'reconciliador': reconciliar_pagos(db, pasarela),
            'recolector': recolectar_vencidos(db, pasarela),
        }


def _loop() -> None:
    while not _stop.is_set():
        try:
            resumen = reconcile_once()
            if any(resumen.values()):
                logger.info('Recuperación del checkout: %s', resumen)
        except Exception:
            logger.exception('Error en la recuperación del checkout')
        _stop.wait(settings.RECONCILIADOR_INTERVALO_S)


def start_checkout_recovery_worker() -> None:
    global _thread
    if _thread and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_loop, name='tiendaya-checkout-recovery', daemon=True)
    _thread.start()


def stop_checkout_recovery_worker() -> None:
    global _thread
    _stop.set()
    if _thread and _thread.is_alive():
        _thread.join(timeout=5)
    _thread = None
