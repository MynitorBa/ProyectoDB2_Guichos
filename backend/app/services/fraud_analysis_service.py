"""Unidad de trabajo compartida por análisis manuales y automáticos."""

from __future__ import annotations

import os
import socket
import time
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db_mysql import engine
from app.core.db_neo4j import get_driver
from app.core.time import utc_now
from app.models.alerta_fraude import AlertaFraude
from app.models.fraud_analysis_run import FraudAnalysisRun
from app.services import fraud_detection_service as fraud


class FraudAnalysisBusy(RuntimeError):
    pass


def _serialize_run(row: FraudAnalysisRun | None) -> dict | None:
    if row is None:
        return None
    return {
        'id': row.id,
        'origen': row.origen,
        'estado': row.estado,
        'iniciada_en': row.iniciada_en.isoformat() if row.iniciada_en else None,
        'finalizada_en': row.finalizada_en.isoformat() if row.finalizada_en else None,
        'duracion_ms': row.duracion_ms,
        'resumen': row.resumen,
        'error': row.error,
    }


def run_fraud_analysis_once(
    origen: str, *, ahora: datetime | None = None,
    engine_override=None, driver_override=None,
    monotonic_fn=time.monotonic,
) -> dict:
    if origen not in {'manual', 'automatico'}:
        raise ValueError('Origen de análisis inválido.')
    db_engine = engine_override or engine
    lock_name = settings.FRAUD_ANALYSIS_LOCK_NAME
    timeout = settings.FRAUD_ANALYSIS_LOCK_TIMEOUT_SECONDS
    # El candado es por conexión. La bitácora y las alertas usan una sesión
    # independiente para que sus commits no queden dentro de la transacción
    # implícita abierta por GET_LOCK.
    lock_connection = db_engine.connect()
    db = Session(bind=db_engine, autoflush=False, expire_on_commit=False)
    acquired = False
    run_id: int | None = None
    started = monotonic_fn()
    try:
        acquired = bool(lock_connection.execute(
            text('SELECT GET_LOCK(:name, :timeout)'),
            {'name': lock_name, 'timeout': timeout},
        ).scalar())
        if not acquired:
            raise FraudAnalysisBusy('Ya existe un análisis de fraude en curso.')

        # Un proceso terminado abruptamente puede dejar una fila en_curso,
        # aunque MySQL ya haya liberado su lock al cerrar la conexión.
        stale_runs = db.query(FraudAnalysisRun).filter_by(estado='en_curso').all()
        for stale in stale_runs:
            stale.estado = 'fallida'
            stale.finalizada_en = utc_now()
            stale.error = 'Ejecución interrumpida; el candado ya no estaba activo.'

        run = FraudAnalysisRun(
            origen=origen, estado='en_curso', iniciada_en=ahora or utc_now(),
            ejecutor=f'{socket.gethostname()}:{os.getpid()}',
        )
        db.add(run)
        db.commit()
        run_id = run.id

        driver = driver_override or get_driver()
        with driver.session() as neo4j:
            informativas = fraud.resumen_fraude(neo4j)
            comerciales = fraud.recalcular_alertas(
                db, neo4j,
                ventana_autocompra_dias=settings.FRAUD_SELF_PURCHASE_WINDOW_DAYS,
                ahora=ahora,
                commit=False,
                ejecucion_id=run_id,
                origen=origen,
                inactivar_ausentes=True,
            )
        summary = {
            'informativas': {
                key: value['count'] for key, value in informativas.items()
            },
            **comerciales,
        }
        db.commit()

        finished = utc_now()
        run = db.get(FraudAnalysisRun, run_id)
        run.estado = 'exitosa'
        run.finalizada_en = finished
        run.duracion_ms = max(0, int((monotonic_fn() - started) * 1000))
        run.resumen = summary
        run.error = None
        db.commit()
        return _serialize_run(run)
    except FraudAnalysisBusy:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        if run_id is not None:
            run = db.get(FraudAnalysisRun, run_id)
            if run is not None:
                run.estado = 'fallida'
                run.finalizada_en = utc_now()
                run.duracion_ms = max(0, int((monotonic_fn() - started) * 1000))
                run.error = str(exc)[:2000]
                db.commit()
        raise
    finally:
        db.close()
        if acquired:
            try:
                lock_connection.execute(
                    text('SELECT RELEASE_LOCK(:name)'), {'name': lock_name},
                )
            except Exception:
                pass
        lock_connection.close()


def fraud_analysis_status(db: Session) -> dict:
    latest_manual = db.query(FraudAnalysisRun).filter_by(
        origen='manual'
    ).order_by(FraudAnalysisRun.id.desc()).first()
    latest_auto = db.query(FraudAnalysisRun).filter_by(
        origen='automatico'
    ).order_by(FraudAnalysisRun.id.desc()).first()
    latest_success = db.query(FraudAnalysisRun).filter_by(
        estado='exitosa'
    ).order_by(FraudAnalysisRun.id.desc()).first()
    running = db.query(FraudAnalysisRun).filter_by(
        estado='en_curso'
    ).order_by(FraudAnalysisRun.id.desc()).first()
    return {
        'ultima_manual': _serialize_run(latest_manual),
        'ultima_automatica': _serialize_run(latest_auto),
        'ultimo_exito': _serialize_run(latest_success),
        'en_curso': _serialize_run(running),
        'alertas_activas': db.query(AlertaFraude).filter_by(activa=True).count(),
        'alertas_historicas': db.query(AlertaFraude).filter_by(activa=False).count(),
        'habilitado': settings.FRAUD_ANALYSIS_ENABLED,
        'intervalo_segundos': settings.FRAUD_ANALYSIS_INTERVAL_SECONDS,
    }
