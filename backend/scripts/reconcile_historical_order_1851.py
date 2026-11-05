#!/usr/bin/env python3
"""Concilia exclusivamente el pedido DEMO #1851, con guardas estrictas."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

from sqlalchemy import text

from app.core.db_mysql import SessionLocal
from app.models.usuario import Usuario
from app.services.historical_reconciliation_service import (
    CLAVE_IDEMPOTENCIA, ConciliacionError, FallaConciliacionSimulada, conciliar_pedido_1851,
    leer_cobro_ledger,
)


ROOT = Path(__file__).resolve().parents[2]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest().upper()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true', help='confirma la transacción; sin esto hace rollback')
    parser.add_argument('--fail-before-commit', action='store_true')
    parser.add_argument('--ledger', type=Path, default=ROOT / 'payment_simulator/ledger.demo.db')
    parser.add_argument('--responsible-email', default='admin@tiendaya.gt')
    parser.add_argument('--allow-test-database', action='store_true', help=argparse.SUPPRESS)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    database = os.getenv('MYSQL_DB', 'tiendaya')
    is_demo = database == 'tiendaya_demo'
    is_test = args.allow_test_database and database.startswith('tiendaya_reconcile_test_')
    if not (is_demo or is_test):
        print(f'RECHAZADO: base no autorizada: {database}', file=sys.stderr)
        return 2
    if args.fail_before_commit and not args.apply:
        print('RECHAZADO: --fail-before-commit requiere --apply.', file=sys.stderr)
        return 2

    ledger = args.ledger.resolve()
    ledger_hash_before = sha256(ledger)
    with SessionLocal() as db:
        actual = db.execute(text('SELECT DATABASE()')).scalar_one()
        if actual != database:
            print(f'RECHAZADO: conexión efectiva {actual}, configuración {database}.', file=sys.stderr)
            return 2
        responsable = db.query(Usuario).filter_by(email=args.responsible_email).one_or_none()
        if responsable is None:
            print('RECHAZADO: responsable inexistente.', file=sys.stderr)
            return 2
        cobro = leer_cobro_ledger(ledger, CLAVE_IDEMPOTENCIA)
        # La clave se valida de nuevo contra el pedido bloqueado dentro del servicio.
        try:
            result = conciliar_pedido_1851(
                db, cobro=cobro, responsable_usuario_id=responsable.id,
                entorno_db=database, fallar_antes_commit=args.fail_before_commit,
            )
            if args.apply:
                db.commit()
            else:
                db.rollback()
                result = {**result, 'aplicada': False, 'dry_run_rollback': True}
        except FallaConciliacionSimulada as exc:
            db.rollback()
            print(json.dumps({'rollback_simulado': True, 'detalle': str(exc)}, ensure_ascii=False))
            return 3
        except Exception:
            db.rollback()
            raise

    ledger_hash_after = sha256(ledger)
    if ledger_hash_after != ledger_hash_before:
        raise ConciliacionError('El ledger cambió durante una operación que debía ser de solo lectura.')
    print(json.dumps({
        **result,
        'database': database,
        'ledger': ledger.name,
        'ledger_sha256': ledger_hash_after,
        'ledger_modificado': False,
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
