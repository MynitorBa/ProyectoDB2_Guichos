"""Bucle independiente y detenible para el análisis horario de fraude."""

from __future__ import annotations

import logging
import threading
from datetime import datetime
from typing import Callable

from app.core.config import settings
from app.core.db_mysql import SessionLocal
from app.core.time import utc_now
from app.models.fraud_analysis_run import FraudAnalysisRun
from app.services.fraud_analysis_service import (
    FraudAnalysisBusy, run_fraud_analysis_once,
)


logger = logging.getLogger(__name__)


def seconds_until_due(
    *, now: datetime | None = None, interval_seconds: int | None = None,
) -> float:
    now = now or utc_now()
    interval = interval_seconds or settings.FRAUD_ANALYSIS_INTERVAL_SECONDS
    with SessionLocal() as db:
        last = db.query(FraudAnalysisRun).filter_by(
            origen='automatico', estado='exitosa',
        ).order_by(FraudAnalysisRun.id.desc()).first()
    if last is None or last.finalizada_en is None:
        return 0.0
    elapsed = (now - last.finalizada_en).total_seconds()
    return max(0.0, float(interval) - elapsed)


def serve(
    stop_event: threading.Event, *, interval_seconds: int | None = None,
    run_once: Callable[[str], dict] = run_fraud_analysis_once,
    due_seconds: Callable[[], float] | None = None,
) -> None:
    interval = interval_seconds or settings.FRAUD_ANALYSIS_INTERVAL_SECONDS
    next_delay = due_seconds or (
        lambda: seconds_until_due(interval_seconds=interval)
    )
    while not stop_event.is_set():
        if stop_event.wait(max(0.0, next_delay())):
            break
        try:
            result = run_once('automatico')
            logger.info('Análisis automático de fraude: %s', result)
        except FraudAnalysisBusy:
            logger.info('Análisis automático omitido: existe otra ejecución en curso.')
        except Exception:
            logger.exception('Falló el análisis automático de fraude; se reintentará.')
        # Después del intento se espera un intervalo completo. En un reinicio,
        # seconds_until_due consulta el último éxito persistido.
        next_delay = lambda: float(interval)
