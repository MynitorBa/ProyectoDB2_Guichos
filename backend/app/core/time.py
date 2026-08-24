"""Utilidades de tiempo consistentes con las columnas MySQL DATETIME."""

from datetime import datetime, timezone


def utc_now() -> datetime:
    """Devuelve UTC sin tzinfo para conservar el contrato DATETIME existente."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
