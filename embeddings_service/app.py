"""Servicio de embeddings de TiendaYa (Entrega 4).

Convierte textos en vectores con un modelo multilingüe local (fastembed, sobre
ONNX Runtime: sin PyTorch, sin llaves ni costo por uso y sin depender de
internet después de la primera descarga). Corre como proceso aparte, igual que
la pasarela de pagos: la API no carga el modelo en memoria y, si este servicio
cae, la tienda sigue funcionando (las recomendaciones por contenido usan su
respaldo).

Los vectores salen **normalizados** (norma 1): la similitud coseno es el
producto punto, que es lo que usa el índice kNN de Elasticsearch.

Configuración por variables de entorno:
- ``EMBEDDINGS_MODEL``      modelo de fastembed (por defecto mpnet multilingüe, 768 dimensiones).
- ``EMBEDDINGS_CACHE_DIR``  carpeta de los modelos descargados (por defecto ``%LOCALAPPDATA%/TiendaYa/modelos``, fuera de OneDrive).

Ejecutar (desde la raíz del proyecto):
    backend\\venv\\Scripts\\python.exe -m uvicorn embeddings_service.app:app --port 8002
"""

from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path

import numpy as np
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger('embeddings_service')

MODELO = os.getenv('EMBEDDINGS_MODEL', 'sentence-transformers/paraphrase-multilingual-mpnet-base-v2')
# Fuera de la carpeta del proyecto: el repositorio vive en OneDrive y el modelo pesa ~1 GB.
CACHE = Path(os.getenv('EMBEDDINGS_CACHE_DIR', Path(os.getenv('LOCALAPPDATA', Path.home())) / 'TiendaYa' / 'modelos'))
MAX_TEXTOS = 64
MAX_CARACTERES = 2000

app = FastAPI(title='TiendaYa · Servicio de embeddings', version='1.0')

_modelo = None
_dimensiones: int | None = None
_error: str | None = None
_cargado_en: float | None = None
_lock = threading.Lock()


def _cargar() -> None:
    """Carga el modelo (y lo descarga la primera vez). Corre en segundo plano."""
    global _modelo, _dimensiones, _error, _cargado_en
    try:
        os.environ.setdefault('HF_HUB_DISABLE_SYMLINKS_WARNING', '1')
        from fastembed import TextEmbedding
        inicio = time.monotonic()
        modelo = TextEmbedding(MODELO, cache_dir=str(CACHE))
        dimensiones = len(next(iter(modelo.embed(['prueba']))))
        with _lock:
            _modelo, _dimensiones, _error = modelo, dimensiones, None
            _cargado_en = round(time.monotonic() - inicio, 1)
        logger.info('Modelo %s listo (%s dimensiones) en %s s.', MODELO, dimensiones, _cargado_en)
    except Exception as exc:  # noqa: BLE001 - se informa en /health
        with _lock:
            _error = f'{exc.__class__.__name__}: {exc}'
        logger.exception('No se pudo cargar el modelo %s', MODELO)


@app.on_event('startup')
def iniciar() -> None:
    # La carga tarda (mpnet ~20 s); el servicio responde /health mientras tanto.
    threading.Thread(target=_cargar, name='carga-modelo', daemon=True).start()


class SolicitudEmbeddings(BaseModel):
    textos: list[str] = Field(min_length=1, max_length=MAX_TEXTOS)


@app.get('/health')
def salud() -> dict:
    with _lock:
        return {
            'modelo': MODELO,
            'listo': _modelo is not None,
            'dimensiones': _dimensiones,
            'carga_segundos': _cargado_en,
            'error': _error,
        }


@app.post('/embeddings')
def embeddings(solicitud: SolicitudEmbeddings) -> dict:
    with _lock:
        modelo, dimensiones = _modelo, _dimensiones
    if modelo is None:
        raise HTTPException(503, 'El modelo todavía se está cargando.' if _error is None else 'El modelo no se pudo cargar.')
    textos = [(texto or '').strip()[:MAX_CARACTERES] or '-' for texto in solicitud.textos]
    vectores = np.array(list(modelo.embed(textos)), dtype=np.float32)
    vectores /= np.clip(np.linalg.norm(vectores, axis=1, keepdims=True), 1e-12, None)
    return {
        'modelo': MODELO,
        'dimensiones': dimensiones,
        'vectores': [[round(float(x), 6) for x in fila] for fila in vectores],
    }
