"""Reconstruye únicamente las tablas derivadas del Plan B de Cassandra.

Uso: python scripts/backfill_mysql_analytics.py --dry-run
     python scripts/backfill_mysql_analytics.py --apply
Ejecutar --apply solo después de migración 27 y respaldo MySQL verificado.
"""

import argparse
import sys
from pathlib import Path

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.db_mysql import SessionLocal  # noqa: E402
from app.services.analytics_mysql_backup import TABLES, rebuild_week_mysql  # noqa: E402
from app.services.analytics_service import _paid_lines, _week_for_row  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--dry-run', action='store_true')
    group.add_argument('--apply', action='store_true')
    group.add_argument('--apply-if-needed', action='store_true')
    args = parser.parse_args()
    with SessionLocal() as db:
        if args.apply_if_needed and db.execute(text(
            'SELECT backfill_completo FROM analitica_respaldo_control WHERE id=1'
        )).scalar():
            print('Respaldo analítico inicial ya completo; sin cambios.')
            return
        source = _paid_lines(db)
        weeks = {_week_for_row(row) for row in source}
        applying = args.apply or args.apply_if_needed
        if applying:
            for table in TABLES:
                weeks.update(db.execute(text(f'SELECT DISTINCT semana_inicio FROM {table}')).scalars())
        print({'semanas': len(weeks), 'lineas_elegibles': len(source), 'modo': 'apply' if applying else 'dry-run'})
        if applying:
            db.execute(text('UPDATE analitica_respaldo_control SET backfill_completo=FALSE WHERE id=1'))
            db.commit()
            for week in sorted(weeks):
                print(rebuild_week_mysql(week, db))
            db.execute(text('UPDATE analitica_respaldo_control SET backfill_completo=TRUE, actualizado_en=UTC_TIMESTAMP(6) WHERE id=1'))
            db.commit()


if __name__ == '__main__':
    main()
