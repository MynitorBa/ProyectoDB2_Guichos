"""Bitácora local de transiciones de los planes B, separada por entorno.

SQLite permite registrar también la caída de MySQL. El archivo está en data/,
fuera de Git, y no se crea al importar el módulo ni durante un sondeo sano.
"""

from __future__ import annotations

import logging
import re
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.core.config import settings

logger = logging.getLogger(__name__)
RETENCION_DIAS = 90
RESPALDOS = {
    'mysql': 'lectura y cola de pedidos',
    'mongo': 'catálogo MySQL',
    'redis': 'carrito MySQL',
    'elasticsearch': 'búsqueda básica',
    'neo4j': 'recomendaciones guardadas; análisis pendiente',
    'cassandra': 'analítica MySQL',
    'embeddings': 'búsqueda textual',
}


def database_path() -> Path:
    identity = re.sub(r'[^a-zA-Z0-9_-]', '_', settings.MYSQL_DB)
    return Path(__file__).resolve().parents[2] / 'data' / f'planb_incidents_{identity}_{settings.MYSQL_PORT}.sqlite3'


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA busy_timeout=5000')
    conn.execute('''CREATE TABLE IF NOT EXISTS incidents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        motor TEXT NOT NULL,
        tipo TEXT NOT NULL DEFAULT 'caida',
        estado_anterior TEXT NOT NULL,
        estado_nuevo TEXT NOT NULL,
        fecha_inicio TEXT NOT NULL,
        fecha_recuperacion TEXT,
        ultima_comprobacion TEXT NOT NULL,
        codigo_error TEXT,
        respaldo TEXT,
        resultado TEXT NOT NULL,
        estado_sync TEXT NOT NULL DEFAULT 'no_verificado'
    )''')
    conn.execute('CREATE UNIQUE INDEX IF NOT EXISTS uq_incident_active ON incidents(motor) WHERE fecha_recuperacion IS NULL')
    conn.execute('CREATE INDEX IF NOT EXISTS ix_incident_time ON incidents(fecha_inicio)')
    return conn


def record_outage(motor: str, codigo_error: str | None = None, *, path: Path | None = None) -> None:
    if motor not in RESPALDOS:
        raise ValueError('Motor desconocido')
    now = datetime.now(timezone.utc).isoformat()
    try:
        with closing(_connect(path or database_path())) as conn, conn:
            conn.execute('''INSERT OR IGNORE INTO incidents
                (motor, estado_anterior, estado_nuevo, fecha_inicio,
                 ultima_comprobacion, codigo_error, respaldo, resultado)
                VALUES (?, 'ok', 'caido', ?, ?, ?, ?, 'respaldo_pendiente_verificacion')''',
                (motor, now, now, (codigo_error or '')[:80], RESPALDOS[motor]))
            cutoff = (datetime.now(timezone.utc) - timedelta(days=RETENCION_DIAS)).isoformat()
            conn.execute('DELETE FROM incidents WHERE fecha_recuperacion IS NOT NULL AND fecha_recuperacion < ?', (cutoff,))
    except (OSError, sqlite3.Error):
        logger.exception('No se pudo persistir la transición de salud de %s', motor)


def record_recovery(motor: str, *, path: Path | None = None) -> None:
    if motor not in RESPALDOS:
        raise ValueError('Motor desconocido')
    target = path or database_path()
    if not target.is_file():
        return
    now = datetime.now(timezone.utc).isoformat()
    try:
        with closing(_connect(target)) as conn, conn:
            conn.execute('''UPDATE incidents SET fecha_recuperacion=?, ultima_comprobacion=?,
                estado_nuevo='recuperado', resultado='motor_recuperado', estado_sync='no_verificado'
                WHERE motor=? AND fecha_recuperacion IS NULL''', (now, now, motor))
    except (OSError, sqlite3.Error):
        logger.exception('No se pudo persistir la recuperación de %s', motor)


def record_check(motor: str, *, path: Path | None = None) -> None:
    """Actualiza la última comprobación de un incidente abierto, como máximo por minuto."""
    if motor not in RESPALDOS:
        raise ValueError('Motor desconocido')
    target = path or database_path()
    if not target.is_file():
        return
    now = datetime.now(timezone.utc).isoformat()
    try:
        with closing(_connect(target)) as conn, conn:
            conn.execute('UPDATE incidents SET ultima_comprobacion=? WHERE motor=? AND fecha_recuperacion IS NULL',
                         (now, motor))
    except (OSError, sqlite3.Error):
        logger.exception('No se pudo actualizar el incidente de %s', motor)


def list_incidents(*, motor: str | None = None, estado: str | None = None,
                   tipo: str | None = None, desde: datetime | None = None,
                   hasta: datetime | None = None, limit: int = 100,
                   path: Path | None = None) -> list[dict]:
    target = path or database_path()
    if not target.is_file():
        return []
    clauses, params = [], []
    if motor:
        clauses.append('motor=?'); params.append(motor)
    if estado == 'activo':
        clauses.append('fecha_recuperacion IS NULL')
    elif estado == 'recuperado':
        clauses.append('fecha_recuperacion IS NOT NULL')
    if tipo:
        clauses.append('tipo=?'); params.append(tipo)
    if desde:
        clauses.append('fecha_inicio>=?'); params.append(desde.isoformat())
    if hasta:
        clauses.append('fecha_inicio<=?'); params.append(hasta.isoformat())
    sql = 'SELECT * FROM incidents' + (' WHERE ' + ' AND '.join(clauses) if clauses else '') + ' ORDER BY id DESC LIMIT ?'
    params.append(min(max(limit, 1), 500))
    with closing(_connect(target)) as conn:
        rows = [dict(row) for row in conn.execute(sql, params)]
    for row in rows:
        row['estado'] = 'activo' if row['fecha_recuperacion'] is None else 'recuperado'
        row['duracion_segundos'] = round((
            datetime.fromisoformat(row['fecha_recuperacion'] or datetime.now(timezone.utc).isoformat())
            - datetime.fromisoformat(row['fecha_inicio'])
        ).total_seconds())
    return rows
