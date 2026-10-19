#!/usr/bin/env python3
"""Ejecuta una vez o sirve periódicamente el análisis de fraude."""

from __future__ import annotations

import argparse
import logging
import sys
import signal
import threading
from pathlib import Path

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings
from app.core.db_mysql import engine
from app.services.fraud_analysis_service import (
    FraudAnalysisBusy, run_fraud_analysis_once,
)
from app.services.fraud_analysis_worker import serve


def parse_args():
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--once', action='store_true')
    mode.add_argument('--serve', action='store_true')
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(name)s: %(message)s',
    )
    if not settings.FRAUD_ANALYSIS_ENABLED:
        print('Análisis automático deshabilitado (FRAUD_ANALYSIS_ENABLED=false).')
        return 0
    if args.once:
        try:
            print(run_fraud_analysis_once('automatico'))
            return 0
        except FraudAnalysisBusy as exc:
            print(str(exc))
            return 2

    stop = threading.Event()

    def request_stop(*_):
        stop.set()

    signal.signal(signal.SIGINT, request_stop)
    if hasattr(signal, 'SIGTERM'):
        signal.signal(signal.SIGTERM, request_stop)
    # Un lock distinto al de cada análisis protege la vida completa del
    # proceso. Así start-dev, un reinicio manual o una segunda consola no dejan
    # dos bucles horarios compitiendo entre sí.
    worker_lock = f'{settings.FRAUD_ANALYSIS_LOCK_NAME}:worker'
    with engine.connect() as lock_connection:
        acquired = lock_connection.execute(
            text('SELECT GET_LOCK(:name, 0)'), {'name': worker_lock},
        ).scalar()
        if acquired != 1:
            print('Ya existe un worker horario de fraude en ejecución.')
            return 3
        try:
            serve(stop)
        finally:
            lock_connection.execute(
                text('SELECT RELEASE_LOCK(:name)'), {'name': worker_lock},
            )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
