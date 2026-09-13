"""Reconstruye la proyección analítica Cassandra desde MySQL de forma repetible."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.db_cassandra import cassandra_health, close_cassandra, get_cassandra_session
from app.core.db_mysql import SessionLocal
from app.services.analytics_service import _paid_lines, rebuild_all


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    with SessionLocal() as db:
        rows = _paid_lines(db)
        print(f'Líneas pagadas elegibles en MySQL: {len(rows)}')
        if args.dry_run:
            print('Dry-run: Cassandra no fue modificada.')
            return 0
        session = get_cassandra_session()
        print(f'Cassandra: {cassandra_health()}')
        result = rebuild_all(db, session)
        print(f'Proyección reconstruida: {result}')
    close_cassandra()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
