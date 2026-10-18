#!/usr/bin/env python3
"""Muestra señales de fraude reales sin inyectar ni eliminar datos.

El antiguo simulador creaba usuarios, compras y reseñas ficticias directamente
en Neo4j. Eso dejó de ser válido cuando MySQL pasó a ser la autoridad. Esta
versión conserva la demostración como una auditoría de solo lectura sobre la
proyección definitiva de nodos ``Compra``.

Uso desde ``backend/``::

    ./venv/Scripts/python.exe scripts/simulate_fraud.py

``--limpiar`` se acepta únicamente por compatibilidad y no elimina nada.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.db_neo4j import close_driver, get_driver  # noqa: E402
from app.services.fraud_detection_service import (  # noqa: E402
    detectar_autocompras,
    detectar_bombardeo,
    detectar_cluster_coordinado,
    detectar_flash_pagadas,
    detectar_reviewer_unico_vendedor,
    detectar_sin_compra,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--limpiar', action='store_true',
        help='Compatibilidad: no realiza ninguna eliminación.',
    )
    args = parser.parse_args()
    if args.limpiar:
        print(
            'No se eliminó ningún dato. La limpieza destructiva del simulador '
            'heredado fue retirada; Neo4j es una proyección reconstruible.'
        )
        return 0

    driver = get_driver()
    try:
        with driver.session() as session:
            result = {
                'bombardeo': detectar_bombardeo(session),
                'resenas_sin_compra_verificada': detectar_sin_compra(session),
                'reviewer_unico_vendedor': detectar_reviewer_unico_vendedor(session),
                'clusters_coordinados': detectar_cluster_coordinado(session),
                'autocompras_pagadas': detectar_autocompras(session),
                'ventas_flash_pagadas': detectar_flash_pagadas(session),
            }
        print('AUDITORÍA DE SEÑALES REALES (solo lectura)')
        print(json.dumps(
            {name: {'total': len(rows), 'muestra': rows[:5]}
             for name, rows in result.items()},
            ensure_ascii=False, indent=2, default=str,
        ))
        return 0
    finally:
        close_driver()


if __name__ == '__main__':
    raise SystemExit(main())
