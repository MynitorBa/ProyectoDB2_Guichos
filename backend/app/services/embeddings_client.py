"""Cliente del servicio de embeddings (``embeddings_service``, puerto 8002).

Pasa por el detector de fallas como cualquier motor: si el servicio no
responde, ``generar`` devuelve ``None`` y quien llama usa su respaldo (por
ejemplo, el producto se indexa sin vector y se completa cuando el servicio
vuelva). Nunca bloquea una compra ni una búsqueda.
"""

from __future__ import annotations

import logging

import httpx

from app.core import salud
from app.core.config import settings
from app.core.fault_injection import punto_de_falla

logger = logging.getLogger(__name__)

LOTE = 32  # textos por solicitud (el servicio acepta hasta 64)


def texto_producto(doc: dict) -> str:
    """El texto que representa a un producto: nombre, categorías, descripción y atributos.

    El nombre va primero y se repite en el resumen de atributos para que pese
    más que una descripción larga.
    """
    categorias = doc.get('categorias') or ([doc['categoria']] if doc.get('categoria') else [])
    nombres_categoria = [c.get('nombre') for c in categorias if isinstance(c, dict) and c.get('nombre')]
    atributos = doc.get('atributos') or {}
    if isinstance(atributos, dict):
        resumen = ', '.join(f'{k}: {v}' for k, v in atributos.items() if v not in (None, '', []))
    else:
        resumen = ''
    partes = [
        doc.get('nombre') or '',
        'Categoría: ' + ', '.join(nombres_categoria) if nombres_categoria else '',
        doc.get('descripcion') or '',
        resumen,
    ]
    return '. '.join(p.strip().rstrip('.') for p in partes if p and p.strip().rstrip('.'))


def generar(textos: list[str], *, http: httpx.Client | None = None,
            punto_falla: str | None = None) -> list[list[float]] | None:
    """Vectores normalizados de ``textos`` (en el mismo orden) o ``None`` si el servicio no responde."""
    if not textos:
        return []
    if not salud.disponible('embeddings'):
        return None
    cliente = http or httpx.Client(base_url=settings.EMBEDDINGS_URL, timeout=settings.EMBEDDINGS_TIMEOUT)
    try:
        if punto_falla:
            punto_de_falla(punto_falla)
        vectores: list[list[float]] = []
        for inicio in range(0, len(textos), LOTE):
            respuesta = cliente.post('/embeddings', json={'textos': textos[inicio:inicio + LOTE]})
            respuesta.raise_for_status()
            vectores.extend(respuesta.json()['vectores'])
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        # Sin conexión (rechazada o sin respuesta al conectar) el circuito se abre de una vez.
        salud.registrar_falla('embeddings', exc, confirmada=isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout)))
        logger.warning('El servicio de embeddings no respondió: %s', exc)
        return None
    finally:
        if http is None:
            cliente.close()
    salud.registrar_exito('embeddings')
    return vectores


def estado(*, http: httpx.Client | None = None) -> dict:
    """``/health`` del servicio (lanza ``httpx.HTTPError`` si no responde)."""
    cliente = http or httpx.Client(base_url=settings.EMBEDDINGS_URL, timeout=3)
    try:
        respuesta = cliente.get('/health')
        respuesta.raise_for_status()
        return respuesta.json()
    finally:
        if http is None:
            cliente.close()
