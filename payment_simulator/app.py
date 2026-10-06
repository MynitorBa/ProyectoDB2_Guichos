"""Pasarela de pagos simulada para TiendaYa (Entrega 3).

Representa un procesador de pagos externo: un sistema independiente, con su
propio registro de cobros (SQLite), que no participa en las transacciones de
MySQL. Por eso el checkout no puede confirmar el cobro y el pedido de forma
atómica y necesita una estrategia de consistencia (saga con compensación).

Garantía principal, igual que en pasarelas reales: **idempotencia por clave**.
Repetir ``POST /cobros`` con el mismo ``Idempotency-Key`` devuelve el mismo
cobro y nunca cobra dos veces.

Modos de falla (``POST /control`` o encabezado ``X-Simular-Modo`` por solicitud):

- ``aprobar``           Cobra y responde aprobado (por defecto).
- ``rechazar``          Registra un rechazo (fondos insuficientes).
- ``timeout``           Cobra, pero tarda más que el timeout del cliente.
- ``cobrar_y_fallar``   Cobra y responde 500: el cliente no sabe si se cobró.
- ``error_antes``       Responde 503 sin registrar nada.

Ejecutar (desde la raíz del proyecto):
    backend\\venv\\Scripts\\python.exe -m uvicorn payment_simulator.app:app --port 8001
"""

from __future__ import annotations

import os
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

MODOS = ('aprobar', 'rechazar', 'timeout', 'cobrar_y_fallar', 'error_antes')
DB_PATH = Path(os.getenv('PASARELA_DB', Path(__file__).with_name('ledger.db')))

app = FastAPI(title='Pasarela de pagos simulada', version='1.0.0')
_lock = threading.Lock()
_control = {'modo': 'aprobar', 'latencia_ms': 0, 'demora_timeout_s': 8.0}


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat()


def _conexion() -> sqlite3.Connection:
    conexion = sqlite3.connect(DB_PATH, check_same_thread=False)
    conexion.row_factory = sqlite3.Row
    return conexion


def _inicializar() -> None:
    with _conexion() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS cobros (
                clave TEXT PRIMARY KEY,
                id TEXT NOT NULL UNIQUE,
                monto TEXT NOT NULL,
                moneda TEXT NOT NULL,
                referencia TEXT,
                estado TEXT NOT NULL CHECK (estado IN ('aprobado','rechazado','reembolsado')),
                motivo TEXT,
                creado_en TEXT NOT NULL,
                actualizado_en TEXT NOT NULL
            )
        """)


_inicializar()


class Cobro(BaseModel):
    monto: Decimal = Field(gt=0)
    moneda: str = 'GTQ'
    referencia: str | None = None


class Control(BaseModel):
    modo: str = 'aprobar'
    latencia_ms: int = Field(0, ge=0, le=60_000)
    demora_timeout_s: float = Field(8.0, ge=0, le=120)


def _a_dict(fila: sqlite3.Row) -> dict:
    return dict(fila)


def _buscar(clave: str) -> dict | None:
    with _conexion() as c:
        fila = c.execute('SELECT * FROM cobros WHERE clave = ?', (clave,)).fetchone()
    return _a_dict(fila) if fila else None


def _registrar(clave: str, cobro: Cobro, estado: str, motivo: str | None) -> dict:
    """Inserta el cobro una sola vez por clave; si ya existe devuelve el original."""
    with _lock, _conexion() as c:
        existente = c.execute('SELECT * FROM cobros WHERE clave = ?', (clave,)).fetchone()
        if existente:
            return _a_dict(existente)
        ahora = _ahora()
        c.execute(
            'INSERT INTO cobros VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (clave, f'ch_{uuid.uuid4().hex[:16]}', str(cobro.monto), cobro.moneda,
             cobro.referencia, estado, motivo, ahora, ahora),
        )
        return _a_dict(c.execute('SELECT * FROM cobros WHERE clave = ?', (clave,)).fetchone())


@app.get('/health')
def health():
    return {'status': 'ok', **_control}


@app.get('/control')
def ver_control():
    return _control


@app.post('/control')
def cambiar_control(control: Control):
    if control.modo not in MODOS:
        raise HTTPException(422, f'Modo desconocido. Opciones: {", ".join(MODOS)}')
    _control.update(control.model_dump())
    return _control


@app.post('/cobros')
def cobrar(
    cobro: Cobro,
    idempotency_key: str = Header(..., alias='Idempotency-Key', min_length=8, max_length=80),
    x_simular_modo: str | None = Header(None, alias='X-Simular-Modo'),
):
    modo = x_simular_modo if x_simular_modo in MODOS else _control['modo']
    existente = _buscar(idempotency_key)
    if existente:
        # Reintento con la misma clave: mismo resultado, sin cobrar de nuevo.
        # Una pasarela lenta también es lenta al responder el reintento.
        if modo == 'timeout':
            time.sleep(_control['demora_timeout_s'])
        return JSONResponse(existente, headers={'Idempotent-Replayed': 'true'})

    if _control['latencia_ms']:
        time.sleep(_control['latencia_ms'] / 1000)

    if modo == 'error_antes':
        raise HTTPException(503, 'Procesador no disponible; no se realizó ningún cargo.')
    if modo == 'rechazar':
        return _registrar(idempotency_key, cobro, 'rechazado', 'fondos_insuficientes')

    registro = _registrar(idempotency_key, cobro, 'aprobado', None)
    if modo == 'timeout':
        # El cobro ya existe, pero la respuesta llega después de que el cliente se rindió.
        time.sleep(_control['demora_timeout_s'])
    elif modo == 'cobrar_y_fallar':
        raise HTTPException(500, 'Error interno después de procesar el cargo.')
    return registro


@app.get('/cobros/{clave}')
def consultar(clave: str):
    registro = _buscar(clave)
    if not registro:
        raise HTTPException(404, 'No existe un cobro con esa clave.')
    return registro


@app.post('/cobros/{clave}/reembolso')
def reembolsar(clave: str):
    with _lock, _conexion() as c:
        fila = c.execute('SELECT * FROM cobros WHERE clave = ?', (clave,)).fetchone()
        if not fila:
            raise HTTPException(404, 'No existe un cobro con esa clave.')
        if fila['estado'] == 'rechazado':
            raise HTTPException(409, 'Un cobro rechazado no se puede reembolsar.')
        if fila['estado'] == 'aprobado':
            c.execute(
                "UPDATE cobros SET estado = 'reembolsado', actualizado_en = ? WHERE clave = ?",
                (_ahora(), clave),
            )
        return _a_dict(c.execute('SELECT * FROM cobros WHERE clave = ?', (clave,)).fetchone())


@app.get('/cobros')
def listar(limite: int = 50):
    with _conexion() as c:
        filas = c.execute('SELECT * FROM cobros ORDER BY creado_en DESC LIMIT ?', (limite,)).fetchall()
    return [_a_dict(f) for f in filas]
