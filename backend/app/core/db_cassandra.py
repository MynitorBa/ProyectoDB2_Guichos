"""Conexión diferida a Cassandra para la proyección analítica de TiendaYa."""

from __future__ import annotations

import logging
import threading
from pathlib import Path

from cassandra.cluster import EXEC_PROFILE_DEFAULT, Cluster, ExecutionProfile, Session
from cassandra.policies import DCAwareRoundRobinPolicy

from app.core.config import settings


logger = logging.getLogger(__name__)
_lock = threading.Lock()
_cluster: Cluster | None = None
_session: Session | None = None


def _schema_path() -> Path:
    return Path(__file__).resolve().parents[3] / 'database' / 'cassandra' / '01_analytics_schema.cql'


def _statements(cql: str) -> list[str]:
    lines = [line for line in cql.splitlines() if not line.lstrip().startswith('--')]
    return [statement.strip() for statement in '\n'.join(lines).split(';') if statement.strip()]


def get_cassandra_session(*, initialize: bool = True) -> Session:
    global _cluster, _session
    if _session is not None:
        return _session
    with _lock:
        if _session is not None:
            return _session
        cluster = Cluster(
            [settings.CASSANDRA_HOST],
            port=settings.CASSANDRA_PORT,
            execution_profiles={
                EXEC_PROFILE_DEFAULT: ExecutionProfile(
                    load_balancing_policy=DCAwareRoundRobinPolicy(
                        local_dc=settings.CASSANDRA_LOCAL_DC
                    ),
                    request_timeout=10,
                )
            },
            connect_timeout=10,
        )
        session = cluster.connect()
        if initialize:
            for statement in _statements(_schema_path().read_text(encoding='utf-8')):
                session.execute(statement)
            session.set_keyspace(settings.CASSANDRA_KEYSPACE)
        _cluster = cluster
        _session = session
        return session


def cassandra_health() -> dict:
    row = get_cassandra_session().execute(
        'SELECT release_version, data_center FROM system.local'
    ).one()
    return {
        'status': 'ok',
        'version': row.release_version,
        'data_center': row.data_center,
        'keyspace': settings.CASSANDRA_KEYSPACE,
    }


def close_cassandra() -> None:
    global _cluster, _session
    with _lock:
        if _session is not None:
            _session.shutdown()
        if _cluster is not None:
            _cluster.shutdown()
        _session = None
        _cluster = None
