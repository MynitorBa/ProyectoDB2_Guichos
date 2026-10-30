"""Conexión singleton a Elasticsearch para el índice de búsqueda del catálogo."""
from __future__ import annotations

import threading

from elasticsearch import Elasticsearch

from app.core.config import settings

_client: Elasticsearch | None = None
_lock = threading.Lock()


def get_es() -> Elasticsearch:
    """Cliente compartido. Elasticsearch es una proyección: si no responde, el
    llamador decide el respaldo (la búsqueda usa MongoDB, el indexado reintenta)."""
    global _client
    if _client is not None:
        return _client
    with _lock:
        if _client is None:
            credenciales = (settings.ES_USERNAME, settings.ES_PASSWORD) if settings.ES_USERNAME else None
            _client = Elasticsearch(
                settings.ES_URL,
                basic_auth=credenciales,
                request_timeout=settings.ES_TIMEOUT,
                retry_on_timeout=False,
                max_retries=0,
            )
    return _client


def close_es() -> None:
    global _client
    if _client is not None:
        _client.close()
        _client = None


def es_health() -> dict:
    health = get_es().options(request_timeout=5).cluster.health()
    return {'status': health['status'], 'nodes': health['number_of_nodes']}
