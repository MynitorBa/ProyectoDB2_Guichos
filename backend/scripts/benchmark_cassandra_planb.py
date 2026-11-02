"""Comparación de consultas analíticas, solo en un entorno aislado.

Requiere MYSQL_DB=tiendaya_benchmark*, puerto MySQL distinto de 3307/3317 y
puerto Cassandra distinto de 9042/9142. No modifica datos. Produce CSV y JSON.
"""

import argparse
import csv
import json
import statistics
import sys
import time
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings  # noqa: E402
from app.core.db_cassandra import get_cassandra_session  # noqa: E402
from app.core.db_mysql import SessionLocal  # noqa: E402
from app.services.analytics_mysql_backup import MySQLAnalyticsAdapter  # noqa: E402
from app.services.analytics_service import (  # noqa: E402
    product_trends, product_weekly_trend, vendor_offer_summary,
    vendor_product_weekly_trend,
)


def _percentile(samples, percentile):
    ordered = sorted(samples)
    position = (len(ordered) - 1) * percentile / 100
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _metrics(samples):
    return {
        'promedio_ms': statistics.mean(samples), 'mediana_ms': statistics.median(samples),
        'p95_ms': _percentile(samples, 95), 'p99_ms': _percentile(samples, 99),
        'muestras': len(samples),
    }


def _canonical(items):
    def normalize(value):
        if isinstance(value, dict):
            return {key: normalize(item) for key, item in value.items()
                    if key not in ('imagen',)}
        if isinstance(value, list):
            return [normalize(item) for item in value]
        return value
    return sorted([normalize(item) for item in items], key=lambda item: json.dumps(item, sort_keys=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--semana', type=date.fromisoformat, required=True)
    parser.add_argument('--repeticiones', type=int, default=30)
    parser.add_argument('--salida', type=Path, required=True)
    parser.add_argument('--consulta', choices=('admin_trends', 'vendor_trends',
                        'product_trend', 'vendor_product_trend'), default='admin_trends')
    args = parser.parse_args()
    if args.semana.weekday() or args.repeticiones < 20:
        parser.error('La semana debe iniciar lunes y se requieren al menos 20 repeticiones')
    if not settings.MYSQL_DB.startswith('tiendaya_benchmark') or settings.MYSQL_PORT in (3307, 3317):
        parser.error('Se prohíbe ejecutar sobre PRINCIPAL o DEMO: use MySQL aislado')
    if settings.CASSANDRA_PORT in (9042, 9142):
        parser.error('Se prohíbe ejecutar sobre Cassandra PRINCIPAL o DEMO')

    cassandra = get_cassandra_session()
    with SessionLocal() as db:
        mysql = MySQLAnalyticsAdapter(db)
        if not mysql.ready():
            parser.error('El respaldo MySQL aislado no tiene backfill completo')
        candidate = db.execute(text('''
            SELECT vendedor_id, producto_ref FROM analitica_productos_vendedor_semana
            WHERE semana_inicio=:week ORDER BY unidades_vendidas DESC LIMIT 1
        '''), {'week': args.semana}).first()
        if not candidate:
            parser.error('No hay producto/vendedor en la semana seleccionada')
        vendor_id, product_ref = int(candidate[0]), candidate[1]
        start_week = args.semana - timedelta(weeks=4)
        def query(source):
            if args.consulta == 'admin_trends':
                return product_trends(args.semana, source, comparison_weeks=4)
            if args.consulta == 'vendor_trends':
                return vendor_offer_summary(vendor_id, args.semana, source, comparison_weeks=4)
            if args.consulta == 'product_trend':
                return product_weekly_trend(product_ref, start_week, args.semana, source)
            return vendor_product_weekly_trend(vendor_id, product_ref,
                                               start_week, args.semana, source)
        sources = {'cassandra': cassandra, 'mysql_respaldo': mysql}
        baseline = {name: _canonical(query(source))
                    for name, source in sources.items()}
        same = baseline['cassandra'] == baseline['mysql_respaldo']
        records = []
        for _ in range(3):
            for source in sources.values():
                query(source)
        for repetition in range(args.repeticiones):
            for name, source in sources.items():
                start = time.perf_counter()
                query(source)
                records.append({'repeticion': repetition + 1, 'fuente': name,
                                'latencia_ms': round((time.perf_counter() - start) * 1000, 3)})
    summary = {name: _metrics([row['latencia_ms'] for row in records if row['fuente'] == name])
               for name in sources}
    summary['diferencia_promedio_porcentaje'] = round(
        (summary['mysql_respaldo']['promedio_ms'] / summary['cassandra']['promedio_ms'] - 1) * 100, 2)
    result = {'semana': args.semana.isoformat(), 'consulta': args.consulta,
              'vendedor_id': vendor_id, 'producto_ref': product_ref,
              'mysql_db': settings.MYSQL_DB,
              'mysql_port': settings.MYSQL_PORT, 'cassandra_port': settings.CASSANDRA_PORT,
              'resultados_iguales': same, 'filas_cassandra': len(baseline['cassandra']),
              'filas_mysql': len(baseline['mysql_respaldo']), 'latencia': summary,
              'alcance': 'servicio analítico, sin HTTP ni carga comercial concurrente'}
    args.salida.mkdir(parents=True, exist_ok=True)
    (args.salida / 'analitica.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    with (args.salida / 'analitica.csv').open('w', newline='', encoding='utf-8') as output:
        writer = csv.DictWriter(output, fieldnames=('repeticion', 'fuente', 'latencia_ms'))
        writer.writeheader()
        writer.writerows(records)
    print(json.dumps(result, indent=2))
    if not same:
        raise SystemExit('Las fuentes no coinciden; revise el retraso de proyección antes de concluir')


if __name__ == '__main__':
    main()
