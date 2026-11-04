#!/usr/bin/env python3
"""Verifica los invariantes de consistencia entre MySQL, la pasarela de pagos,
MongoDB y Elasticsearch. Solo lee; no corrige nada.

Uso (desde backend/):
    .\\venv\\Scripts\\python.exe scripts\\verificar_consistencia.py
    .\\venv\\Scripts\\python.exe scripts\\verificar_consistencia.py --json
Sale con código 1 si algún invariante se viola.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from app.core.db_elastic import get_es  # noqa: E402
from app.core.db_mongo import get_mongo_db  # noqa: E402
from app.core.db_mysql import SessionLocal  # noqa: E402
from app.services.consistency_service import verificar  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description='Invariantes de consistencia de TiendaYa.')
    parser.add_argument('--json', action='store_true', help='Imprime el resultado completo en JSON.')
    args = parser.parse_args()

    with SessionLocal() as db:
        resultado = verificar(db, get_mongo_db(), get_es())

    if args.json:
        print(json.dumps(resultado, ensure_ascii=False, indent=2, default=str))
    else:
        for inv in resultado['invariantes']:
            marca = {True: 'OK  ', False: 'FALLA', None: 'N/D '}[inv['ok']]
            print(f"[{marca}] {inv['id']} {inv['titulo']} — {inv['detalle']}")
            if inv.get('nota'):
                print(f'        nota: {inv["nota"]}')
            for ejemplo in inv['ejemplos']:
                print(f'        {ejemplo}')
        if resultado['ok']:
            print('\nTodos los invariantes se verificaron y se cumplen.')
        elif resultado['violado']:
            print('\nHay invariantes violados.')
        else:
            print(f"\nNingún invariante violado, pero no se pudo verificar: {', '.join(resultado['no_verificables'])}.")
    # 0 = todo verificado y cumplido; 1 = alguno violado; 2 = sin violaciones pero incompleto.
    return 0 if resultado['ok'] else (1 if resultado['violado'] else 2)


if __name__ == '__main__':
    raise SystemExit(main())
