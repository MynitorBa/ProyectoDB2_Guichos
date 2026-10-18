#!/usr/bin/env python3
"""Entrada de compatibilidad para el generador de reseñas retirado.

No crea compras ni reseñas ficticias. La proyección se reconstruye desde las
autoridades MySQL mediante ``backfill_neo4j_reviews.py``.
"""


def main() -> int:
    print(
        'Generador retirado: no se inventan compras ni reseñas en Neo4j. '
        'Ejecuta scripts/backfill_neo4j_reviews.py --apply para reconstruir '
        'la proyección desde MySQL.'
    )
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
