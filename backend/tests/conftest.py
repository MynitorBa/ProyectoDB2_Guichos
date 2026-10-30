"""Fixtures compartidas de la batería de integración.

El checkout llama a una pasarela de pagos externa. Las pruebas no usan mocks:
levantan el mismo simulador (``payment_simulator``) como proceso aparte, en un
puerto propio y con un registro temporal, para no tocar la pasarela de
desarrollo.
"""

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
import pytest

# Las pruebas ejercitan también los endpoints del laboratorio de consistencia,
# que main.py solo registra con la inyección de fallas habilitada. Se fija antes
# de importar la configuración para no depender del backend/.env de cada equipo.
os.environ['FAULT_INJECTION_ENABLED'] = 'true'

from app.core.config import settings  # noqa: E402

RAIZ = Path(__file__).resolve().parents[2]
PUERTO_PASARELA = 8091
URL_PASARELA = f'http://127.0.0.1:{PUERTO_PASARELA}'


@pytest.fixture(scope='session')
def es_indexador():
    """Cliente con el usuario indexador: crear y borrar índices temporales de prueba.

    El backend (tiendaya_api) no puede crear ni borrar índices (control de acceso).
    """
    from dotenv import dotenv_values
    from elasticsearch import Elasticsearch

    clave = dotenv_values(Path(__file__).resolve().parents[2] / '.env').get('ES_INDEXADOR_PASSWORD')
    credenciales = ('tiendaya_indexador', clave) if clave else None
    return Elasticsearch(settings.ES_URL, basic_auth=credenciales, request_timeout=15)


@pytest.fixture(autouse=True)
def circuitos_cerrados():
    """Cada prueba empieza con todos los motores marcados como disponibles.

    Una prueba que simula un motor caído abre su circuito; sin esto, las
    siguientes usarían el respaldo durante la espera del detector de fallas.
    """
    from app.core import salud
    salud.reiniciar()
    yield
    salud.reiniciar()


@pytest.fixture(scope='session', autouse=True)
def pasarela_simulada():
    ledger = Path(tempfile.gettempdir()) / f'pasarela_pruebas_{os.getpid()}.db'
    entorno = {**os.environ, 'PASARELA_DB': str(ledger)}
    proceso = subprocess.Popen(
        [sys.executable, '-m', 'uvicorn', 'payment_simulator.app:app',
         '--port', str(PUERTO_PASARELA), '--log-level', 'warning'],
        cwd=RAIZ, env=entorno,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        limite = time.time() + 20
        while True:
            try:
                httpx.get(f'{URL_PASARELA}/health', timeout=0.5)
                break
            except httpx.HTTPError:
                if time.time() > limite or proceso.poll() is not None:
                    raise RuntimeError('No arrancó la pasarela simulada para las pruebas.')
                time.sleep(0.2)
        anterior = settings.PAYMENT_GATEWAY_URL
        settings.PAYMENT_GATEWAY_URL = URL_PASARELA
        yield URL_PASARELA
        settings.PAYMENT_GATEWAY_URL = anterior
    finally:
        proceso.terminate()
        try:
            proceso.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proceso.kill()
        try:
            ledger.unlink(missing_ok=True)
        except PermissionError:
            pass  # Windows libera el archivo unos instantes después; está en %TEMP%.


PUERTO_EMBEDDINGS = 8092
URL_EMBEDDINGS = f'http://127.0.0.1:{PUERTO_EMBEDDINGS}'


@pytest.fixture(scope='session', autouse=True)
def servicio_embeddings():
    """Servicio de embeddings real en un puerto propio, como la pasarela.

    Usa el mismo modelo y la misma carpeta de modelos que el de desarrollo, así
    que solo la primera corrida lo descarga.
    """
    proceso = subprocess.Popen(
        [sys.executable, '-m', 'uvicorn', 'embeddings_service.app:app',
         '--port', str(PUERTO_EMBEDDINGS), '--log-level', 'warning'],
        cwd=RAIZ, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        limite = time.time() + 600  # la primera vez descarga el modelo
        while True:
            try:
                if httpx.get(f'{URL_EMBEDDINGS}/health', timeout=1).json().get('listo'):
                    break
            except httpx.HTTPError:
                pass
            if time.time() > limite or proceso.poll() is not None:
                raise RuntimeError('No arrancó el servicio de embeddings para las pruebas.')
            time.sleep(0.5)
        anterior = settings.EMBEDDINGS_URL
        settings.EMBEDDINGS_URL = URL_EMBEDDINGS
        yield URL_EMBEDDINGS
        settings.EMBEDDINGS_URL = anterior
    finally:
        proceso.terminate()
        try:
            proceso.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proceso.kill()


def modo_pasarela(modo: str, **extra) -> None:
    """Cambia el comportamiento de la pasarela de pruebas."""
    httpx.post(f'{URL_PASARELA}/control', json={'modo': modo, **extra}, timeout=5).raise_for_status()


@pytest.fixture
def pasarela_en_modo():
    """Permite a una prueba elegir el modo de falla; siempre vuelve a 'aprobar'."""
    yield modo_pasarela
    modo_pasarela('aprobar', latencia_ms=0, demora_timeout_s=8.0)
