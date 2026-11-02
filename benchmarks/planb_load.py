"""Carga acotada de analítica y reserva de inventario en motores aislados.

La operación comercial es un proxy de bloqueo/actualización con ROLLBACK;
NO mide el checkout completo ni produce compras. Nunca apunta a PRINCIPAL/DEMO.
"""
from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app.core.config import settings  # noqa: E402
from app.core.db_cassandra import get_cassandra_session  # noqa: E402
from app.core.db_mysql import SessionLocal  # noqa: E402
from app.services.analytics_mysql_backup import MySQLAnalyticsAdapter  # noqa: E402
from app.services.analytics_service import product_trends  # noqa: E402


def percentile(values, p):
    if not values:
        return None
    ordered = sorted(values)
    pos = (len(ordered) - 1) * p / 100
    lo = int(pos)
    return round(ordered[lo] + (ordered[min(lo + 1, len(ordered) - 1)] - ordered[lo]) * (pos - lo), 3)


def summarize(samples, seconds):
    return {'n': len(samples), 'qps': round(len(samples) / seconds, 2),
            'promedio_ms': round(statistics.mean(samples), 3) if samples else None,
            'p50_ms': percentile(samples, 50), 'p95_ms': percentile(samples, 95),
            'p99_ms': percentile(samples, 99)}


def mysql_status(db):
    names = ('Slow_queries', 'Innodb_row_lock_waits', 'Innodb_row_lock_time', 'Threads_connected')
    result = {}
    for name in names:
        row = db.execute(text('SHOW GLOBAL STATUS LIKE :name'), {'name': name}).first()
        result[name] = int(row[1]) if row else None
    return result


def docker_sample():
    cmd = ['docker', 'stats', '--no-stream', '--format', '{{.Name}}|{{.CPUPerc}}|{{.MemUsage}}',
           'tiendaya_benchmark_mysql', 'tiendaya_benchmark_cassandra']
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=12, check=True)
    return result.stdout.strip().splitlines()


def run_case(name, source, analytics_workers, seconds, week, inventory_ids):
    deadline = time.perf_counter() + seconds
    lock = threading.Lock()
    latencies = {'analitica': [], 'inventario_proxy': []}
    errors = []
    samples = []
    cassandra = get_cassandra_session() if source == 'cassandra' else None

    def record(kind, duration):
        with lock:
            latencies[kind].append(duration * 1000)

    def analytics_worker():
        try:
            with SessionLocal() as db:
                adapter = MySQLAnalyticsAdapter(db) if source == 'mysql' else None
                while time.perf_counter() < deadline:
                    started = time.perf_counter()
                    product_trends(week, cassandra if source == 'cassandra' else adapter,
                                   comparison_weeks=4)
                    record('analitica', time.perf_counter() - started)
        except Exception as exc:
            with lock:
                errors.append(repr(exc))

    def inventory_worker(inventory_id):
        try:
            with SessionLocal() as db:
                while time.perf_counter() < deadline:
                    started = time.perf_counter()
                    try:
                        db.execute(text('SELECT id FROM inventario WHERE id=:id FOR UPDATE'),
                                   {'id': inventory_id}).one()
                        db.execute(text('UPDATE inventario SET cantidad_reservada=cantidad_reservada+1 '
                                        'WHERE id=:id'), {'id': inventory_id})
                    finally:
                        db.rollback()
                    record('inventario_proxy', time.perf_counter() - started)
        except Exception as exc:
            with lock:
                errors.append(repr(exc))

    def monitor():
        while time.perf_counter() < deadline:
            try:
                samples.append({'segundo': round(seconds - (deadline - time.perf_counter()), 2),
                                'docker': docker_sample()})
            except Exception as exc:
                samples.append({'error': repr(exc)})
            time.sleep(1)

    with SessionLocal() as db:
        before = mysql_status(db)
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=analytics_workers + len(inventory_ids) + 1) as pool:
        futures = [pool.submit(analytics_worker) for _ in range(analytics_workers)]
        futures += [pool.submit(inventory_worker, item) for item in inventory_ids]
        futures.append(pool.submit(monitor))
        for future in futures:
            future.result()
    elapsed = time.perf_counter() - started
    with SessionLocal() as db:
        after = mysql_status(db)
    return {'escenario': name, 'fuente': source, 'analitica_hilos': analytics_workers,
            'inventario_hilos': len(inventory_ids), 'duracion_s': round(elapsed, 3),
            'analitica': summarize(latencies['analitica'], elapsed),
            'inventario_proxy': summarize(latencies['inventario_proxy'], elapsed),
            'mysql_status_inicio': before, 'mysql_status_final': after,
            'mysql_status_delta': {k: after[k] - before[k] for k in before if after[k] is not None},
            'docker_muestras': samples, 'errores': errors}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--segundos', type=int, default=15)
    parser.add_argument('--repeticiones', type=int, default=2)
    parser.add_argument('--salida', type=Path, required=True)
    args = parser.parse_args()
    if args.segundos < 5 or args.segundos > 30 or args.repeticiones < 1 or args.repeticiones > 3:
        parser.error('Límites: 5–30 segundos y 1–3 repeticiones')
    if (settings.MYSQL_DB != 'tiendaya_benchmark_20261101' or settings.MYSQL_PORT != 3337
            or settings.CASSANDRA_PORT != 9242):
        parser.error('Solo se permite MySQL 3337 y Cassandra 9242 del benchmark aislado')
    with SessionLocal() as db:
        inventory_ids = db.execute(text('SELECT id FROM inventario ORDER BY id LIMIT 2')).scalars().all()
        if len(inventory_ids) != 2:
            parser.error('Se necesitan dos filas de inventario aislado')
        if not MySQLAnalyticsAdapter(db).ready():
            parser.error('Backfill MySQL incompleto')
    week = date(2026, 9, 14)
    cases = [('A', 'cassandra', 2), ('B', 'mysql', 2), ('C', 'mysql', 6)]
    results = []
    for repetition in range(1, args.repeticiones + 1):
        for name, source, workers in cases:
            result = run_case(name, source, workers, args.segundos, week, inventory_ids)
            result['repeticion'] = repetition
            results.append(result)
            print(name, repetition, result['analitica'], result['inventario_proxy'],
                  'errores=', len(result['errores']), flush=True)
            if result['errores']:
                break
        if results[-1]['errores']:
            break
    args.salida.parent.mkdir(parents=True, exist_ok=True)
    args.salida.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    if any(result['errores'] for result in results):
        raise SystemExit('Carga incompleta: revisar errores en JSON')


if __name__ == '__main__':
    main()
