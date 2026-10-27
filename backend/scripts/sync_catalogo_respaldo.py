#!/usr/bin/env python3
r"""Llena o pone al día la copia del catálogo de MongoDB en MySQL (plan B de MongoDB)
y el autocompletado de respaldo en Redis (plan B de Elasticsearch).

Idempotente: copia los documentos nuevos o editados desde la última copia y
retira los que ya no existen en MongoDB.

Uso (desde backend/):
    .\venv\Scripts\python.exe scripts\sync_catalogo_respaldo.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from app.core.db_mongo import get_mongo_db  # noqa: E402
from app.core.db_mysql import SessionLocal  # noqa: E402
from app.services.catalogo_respaldo_service import reconciliar, reconstruir_autocompletado  # noqa: E402


def main() -> int:
    with SessionLocal() as db:
        resumen = reconciliar(get_mongo_db(), db)
        db.commit()
    print(f"Copia del catálogo al día: {resumen['copiados']} copiados, {resumen['retirados']} retirados.")
    try:
        print(f'Autocompletado de respaldo en Redis: {reconstruir_autocompletado()} productos.')
    except Exception as exc:  # noqa: BLE001 - Redis es opcional para la copia
        print(f'Autocompletado de respaldo no construido (Redis no disponible): {exc}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
