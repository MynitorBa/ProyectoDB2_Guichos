#!/usr/bin/env python3
"""Ejecuta las pruebas de falla del checkout distribuido y genera la evidencia.

Corre contra el sistema real en ejecución (``start-dev.ps1``): API en :8000,
pasarela simulada en :8001 y los contenedores Docker. Por cada escenario
provoca una falla concreta, toma una "foto" del estado antes y después
(inventario, pedido, pago, bitácora de la saga, cobros en la pasarela, outbox)
y verifica los invariantes de consistencia. Escribe un Markdown por escenario
en ``docs/evidencia/fallas/`` y un resumen.

Requisitos en backend/.env: ``FAULT_INJECTION_ENABLED=true`` y, para que los
escenarios de caída a mitad de la saga no tarden 10 minutos,
``CHECKOUT_RESERVA_MINUTOS=1`` y ``RECONCILIADOR_GRACIA_S=20``.

ATENCIÓN: crea pedidos reales (de la cuenta comprador1) y detiene/arranca
contenedores. Úsese solo en desarrollo.

Uso (desde backend/):
    .\\venv\\Scripts\\python.exe scripts\\demo_fallas.py               # todos
    .\\venv\\Scripts\\python.exe scripts\\demo_fallas.py E01 E03       # algunos
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import httpx

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from sqlalchemy import text  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.db_elastic import get_es  # noqa: E402
from app.core.db_mongo import get_mongo_db  # noqa: E402
from app.core.db_mysql import SessionLocal  # noqa: E402
from app.core.db_redis import get_redis  # noqa: E402
from app.services import consistency_service  # noqa: E402
from app.services import redis_cart_service as rcs  # noqa: E402

API = 'http://127.0.0.1:8000/api/v1'
PASARELA = 'http://127.0.0.1:8001'
OFERTA = 50            # Granola artesanal (HogarIdeal): barata y con stock amplio
COMPRADOR_ID = 7       # comprador1@gmail.com
DIRECCION_ID = 2
TARJETA = 1
SALIDA = BACKEND.parent / 'docs' / 'evidencia' / 'fallas'


# ── Utilidades ────────────────────────────────────────────────────────────────

def log(mensaje: str) -> None:
    print(f'[{datetime.now():%H:%M:%S}] {mensaje}', flush=True)


def esperar(condicion, limite: float, intervalo: float = 0.5):
    """Espera hasta que ``condicion()`` sea verdadera. Devuelve los segundos o None."""
    inicio = time.monotonic()
    while time.monotonic() - inicio < limite:
        if condicion():
            return round(time.monotonic() - inicio, 1)
        time.sleep(intervalo)
    return None


def docker(*args: str) -> None:
    subprocess.run(['docker', *args], check=True, capture_output=True)


def salud(contenedor: str) -> str:
    resultado = subprocess.run(
        ['docker', 'inspect', '--format', '{{.State.Health.Status}}', contenedor],
        capture_output=True, text=True,
    )
    return resultado.stdout.strip()


def sql(consulta: str, **params) -> list[dict]:
    with SessionLocal() as db:
        return [dict(r) for r in db.execute(text(consulta), params).mappings()]


class Cliente:
    def __init__(self):
        self.http = httpx.Client(base_url=API, timeout=60)
        self.comprador = self._token('comprador1@gmail.com')
        self.admin = self._token('admin@tiendaya.gt')

    def _token(self, email: str) -> dict:
        r = self.http.post('/auth/login', json={'email': email, 'password': 'password123'})
        r.raise_for_status()
        return {'Authorization': f'Bearer {r.json()["access_token"]}'}

    def checkout(self, clave: str | None = None):
        cabeceras = {**self.comprador, **({'Idempotency-Key': clave} if clave else {})}
        inicio = time.monotonic()
        r = self.http.post('/orders/checkout', headers=cabeceras,
                           json={'direccion_id': DIRECCION_ID, 'metodo_pago_id': TARJETA})
        try:
            cuerpo = r.json()
        except ValueError:
            cuerpo = r.text
        return r.status_code, cuerpo, round(time.monotonic() - inicio, 2)

    def pasarela(self, modo: str, **extra) -> None:
        self.http.post('/admin/fallas/pasarela', headers=self.admin, json={'modo': modo, **extra}).raise_for_status()

    def falla(self, punto: str, modo: str = 'una_vez') -> None:
        self.http.post('/admin/fallas', headers=self.admin, json={'punto': punto, 'modo': modo}).raise_for_status()

    def buscar(self, q: str) -> dict:
        return self.http.get('/search', params={'q': q}).json()


def preparar_carrito(cantidad: int = 1) -> None:
    r = get_redis()
    r.delete(f'carrito:{COMPRADOR_ID}')
    precio = sql('SELECT precio_actual FROM ofertas WHERE id = :o', o=OFERTA)[0]['precio_actual']
    rcs.agregar_item(r, COMPRADOR_ID, OFERTA, cantidad, Decimal(precio), None)


def carrito() -> list[int]:
    try:
        return [i['oferta_id'] for i in rcs.obtener_carrito(get_redis(), COMPRADOR_ID)]
    except Exception as exc:
        return [f'Redis no disponible ({exc.__class__.__name__})']


def inventario() -> dict:
    fila = sql("""SELECT cantidad_disponible AS disponible, cantidad_reservada AS reservado
                  FROM inventario WHERE oferta_id = :o AND bodega = 'principal'""", o=OFERTA)[0]
    return dict(fila)


def pedido(pedido_id: int) -> dict:
    filas = sql("""
        SELECT pe.id, pe.estado, pe.motivo_cancelacion, pa.estado AS pago, pa.intentos,
               pa.referencia_pasarela, pa.clave_idempotencia
        FROM pedidos pe JOIN pagos pa ON pa.pedido_id = pe.id WHERE pe.id = :p
    """, p=pedido_id)
    return filas[0] if filas else {}


def ultimo_pedido_del_comprador() -> int | None:
    filas = sql('SELECT MAX(id) AS id FROM pedidos WHERE usuario_id = :u', u=COMPRADOR_ID)
    return filas[0]['id']


def bitacora(pedido_id: int) -> list[dict]:
    return sql("""SELECT paso, resultado, DATE_FORMAT(creado_en, '%H:%i:%s.%f') AS hora
                  FROM checkout_saga_pasos WHERE pedido_id = :p ORDER BY id""", p=pedido_id)


def cobros(clave: str | None) -> list[dict]:
    if not clave:
        return []
    return [c for c in httpx.get(f'{PASARELA}/cobros', params={'limite': 1000}, timeout=10).json()
            if c['clave'] == clave]


def outbox(pedido_id: int) -> dict[str, dict[str, int]]:
    resumen: dict[str, dict[str, int]] = {}
    for fila in sql("""SELECT destino, estado, COUNT(*) AS n FROM outbox_eventos
                       WHERE agregado_tipo = 'pedido' AND agregado_id = :p
                       GROUP BY destino, estado""", p=str(pedido_id)):
        resumen.setdefault(fila['destino'], {})[fila['estado']] = fila['n']
    return resumen


def outbox_al_dia(pedido_id: int) -> bool:
    estados = outbox(pedido_id)
    return bool(estados) and all(set(e) == {'procesado'} for e in estados.values())


def invariantes() -> dict:
    with SessionLocal() as db:
        resultado = consistency_service.verificar(db, get_mongo_db(), get_es())
    return {
        'ok': resultado['ok'],
        'detalle': {i['id']: i['ok'] for i in resultado['invariantes']},
        'violados': [f"{i['id']}: {i['ejemplos'][:2]}" for i in resultado['invariantes'] if i['ok'] is False],
    }


# ── Registro de cada escenario ────────────────────────────────────────────────

@dataclass
class Escenario:
    codigo: str
    titulo: str
    falla: str
    provocacion: str
    esperado: str
    pasos: list[str] = field(default_factory=list)
    secciones: list[tuple[str, str]] = field(default_factory=list)
    metricas: dict = field(default_factory=dict)
    comprobaciones: list[tuple[str, bool]] = field(default_factory=list)

    def paso(self, texto: str) -> None:
        log(f'{self.codigo} · {texto}')
        self.pasos.append(f'{datetime.now():%H:%M:%S} — {texto}')

    def seccion(self, titulo: str, contenido) -> None:
        if not isinstance(contenido, str):
            contenido = '```json\n' + json.dumps(contenido, ensure_ascii=False, indent=2, default=str) + '\n```'
        self.secciones.append((titulo, contenido))

    def comprobar(self, descripcion: str, condicion: bool) -> None:
        self.comprobaciones.append((descripcion, bool(condicion)))
        log(f'{self.codigo} · {"OK " if condicion else "FALLA"} {descripcion}')

    @property
    def ok(self) -> bool:
        return all(c for _, c in self.comprobaciones)

    def markdown(self) -> str:
        lineas = [
            f'# {self.codigo} · {self.titulo}', '',
            f'**Resultado: {"✅ superado" if self.ok else "❌ con fallas"}** — generado por '
            '`backend/scripts/demo_fallas.py` contra el sistema en ejecución.', '',
            '| | |', '|---|---|',
            f'| Falla | {self.falla} |',
            f'| Cómo se provocó | {self.provocacion} |',
            f'| Comportamiento esperado | {self.esperado} |', '',
            '## Secuencia', '', *[f'1. {p}' for p in self.pasos], '',
            '## Comprobaciones', '', '| Comprobación | Resultado |', '|---|---|',
            *[f'| {d} | {"✅" if c else "❌"} |' for d, c in self.comprobaciones], '',
        ]
        if self.metricas:
            lineas += ['## Métricas', '', '| Métrica | Valor |', '|---|---|',
                       *[f'| {k} | {v} |' for k, v in self.metricas.items()], '']
        for titulo, contenido in self.secciones:
            lineas += [f'## {titulo}', '', contenido, '']
        return '\n'.join(lineas)


def foto(e: Escenario, momento: str, pedido_id: int | None = None) -> None:
    datos = {'inventario_oferta': inventario(), 'carrito_comprador': carrito()}
    if pedido_id:
        datos['pedido'] = pedido(pedido_id)
        datos['outbox_del_pedido'] = outbox(pedido_id)
        datos['cobros_en_pasarela'] = [
            {k: c[k] for k in ('id', 'estado', 'monto', 'creado_en')}
            for c in cobros(datos['pedido'].get('clave_idempotencia'))
        ]
    e.seccion(f'Estado {momento}', datos)


def cierre(e: Escenario, pedido_id: int | None) -> None:
    if pedido_id:
        e.seccion('Bitácora de la saga', '\n'.join(
            ['| Hora (UTC) | Paso | Resultado |', '|---|---|---|'] +
            [f"| {p['hora'][:12]} | {p['paso']} | {p['resultado']} |" for p in bitacora(pedido_id)]
        ))
    inv = invariantes()
    e.seccion('Invariantes después del escenario', inv)
    e.comprobar('Los invariantes de consistencia se cumplen', inv['ok'])


# ── Escenarios ────────────────────────────────────────────────────────────────

def e00_linea_base(c: Cliente) -> Escenario:
    e = Escenario('E00', 'Compra normal y ventana de consistencia eventual', 'Ninguna (línea base)',
                  'Pasarela en modo «aprobar».',
                  'Pedido confirmado y todos los componentes al día en pocos segundos.')
    c.pasarela('aprobar')
    preparar_carrito()
    antes = inventario()
    foto(e, 'antes')
    estado, cuerpo, segundos = c.checkout(str(uuid.uuid4()))
    e.paso(f'POST /orders/checkout → HTTP {estado} en {segundos} s')
    pid = cuerpo['pedido_id']
    e.seccion('Respuesta al cliente', cuerpo)
    tiempos = {}
    inicio = time.monotonic()
    pendientes = {'mongo', 'busqueda', 'cassandra', 'neo4j', 'redis'}
    while pendientes and time.monotonic() - inicio < 60:
        for destino, estados in outbox(pid).items():
            if destino in pendientes and set(estados) == {'procesado'}:
                tiempos[destino] = round(time.monotonic() - inicio, 2)
                pendientes.discard(destino)
        time.sleep(0.2)
    e.metricas['Respuesta del checkout'] = f'{segundos} s'
    for destino, valor in sorted(tiempos.items(), key=lambda kv: kv[1]):
        e.metricas[f'Proyección en {destino} tras confirmar'] = f'{valor} s'
    foto(e, 'después', pid)
    e.comprobar('HTTP 201 y pedido confirmado', estado == 201 and pedido(pid)['estado'] == 'confirmado')
    e.comprobar('Stock descontado en 1 unidad', inventario()['disponible'] == antes['disponible'] - 1)
    e.comprobar('Los 5 destinos del outbox quedaron procesados', not pendientes)
    cierre(e, pid)
    return e


def e01_rechazo(c: Cliente) -> Escenario:
    e = Escenario('E01', 'La pasarela rechaza el pago', 'Pago rechazado (fondos insuficientes)',
                  'Pasarela en modo «rechazar».',
                  'HTTP 402; el pedido se compensa (cancelado), se libera la reserva y el carrito se conserva.')
    c.pasarela('rechazar')
    preparar_carrito()
    antes = inventario()
    foto(e, 'antes')
    estado, cuerpo, segundos = c.checkout(str(uuid.uuid4()))
    e.paso(f'POST /orders/checkout → HTTP {estado} en {segundos} s')
    e.seccion('Respuesta al cliente', cuerpo)
    pid = cuerpo['detail']['pedido_id']
    foto(e, 'después', pid)
    p = pedido(pid)
    e.comprobar('HTTP 402 PAYMENT_DECLINED', estado == 402 and cuerpo['detail']['code'] == 'PAYMENT_DECLINED')
    e.comprobar('Pedido cancelado por pago_rechazado', (p['estado'], p['motivo_cancelacion']) == ('cancelado', 'pago_rechazado'))
    e.comprobar('Inventario igual que antes (reserva liberada)', inventario() == antes)
    e.comprobar('El carrito conserva el producto', carrito() == [OFERTA])
    e.comprobar('Ningún evento de venta hacia Cassandra/Neo4j',
                not {'cassandra', 'neo4j'} & set(outbox(pid)))
    c.pasarela('aprobar')
    cierre(e, pid)
    return e


def e02_cobrar_y_fallar(c: Cliente) -> Escenario:
    e = Escenario('E02', 'La pasarela cobra y responde error 500',
                  'Cargo realizado pero respuesta 500: el cliente no sabe si se cobró',
                  'Pasarela en modo «cobrar_y_fallar».',
                  'El reintento automático con la misma clave idempotente recibe el cobro ya hecho: '
                  'pedido confirmado con UN solo cargo.')
    c.pasarela('cobrar_y_fallar')
    preparar_carrito()
    estado, cuerpo, segundos = c.checkout(str(uuid.uuid4()))
    e.paso(f'POST /orders/checkout → HTTP {estado} en {segundos} s')
    e.seccion('Respuesta al cliente', cuerpo)
    pid = cuerpo['pedido_id']
    foto(e, 'después', pid)
    p = pedido(pid)
    e.metricas['Intentos contra la pasarela'] = p['intentos']
    e.comprobar('HTTP 201 y pedido confirmado', estado == 201 and p['estado'] == 'confirmado')
    e.comprobar('Hubo reintento (2 intentos)', p['intentos'] == 2)
    e.comprobar('Exactamente un cargo en la pasarela', len(cobros(p['clave_idempotencia'])) == 1)
    c.pasarela('aprobar')
    cierre(e, pid)
    return e


def e03_timeout(c: Cliente) -> Escenario:
    e = Escenario('E03', 'La pasarela cobra pero no responde a tiempo',
                  'Timeout en todos los intentos con el cargo ya realizado',
                  'Pasarela en modo «timeout» (responde a los 8 s; el cliente espera 3 s por intento).',
                  'HTTP 202: pedido pendiente con pago en verificación; el reconciliador consulta la pasarela '
                  'y lo confirma sin volver a cobrar.')
    c.pasarela('timeout', demora_timeout_s=8)
    preparar_carrito()
    antes = inventario()
    estado, cuerpo, segundos = c.checkout(str(uuid.uuid4()))
    e.paso(f'POST /orders/checkout → HTTP {estado} en {segundos} s')
    e.seccion('Respuesta al cliente', cuerpo)
    pid = cuerpo['pedido_id']
    c.pasarela('aprobar')
    foto(e, 'al responder al cliente', pid)
    resuelto = esperar(lambda: pedido(pid)['estado'] == 'confirmado', 60)
    # El reconciliador puede actuar antes de cualquier observación externa; la
    # bitácora de la saga registra el paso intermedio sin depender del momento.
    pasos = [(p['paso'], p['resultado']) for p in bitacora(pid)]
    en_verificacion = ('verificacion', 'pendiente') in pasos and ('reconciliador', 'aprobado') in pasos
    e.paso(f'El reconciliador confirmó el pedido {resuelto} s después de responder al cliente')
    e.metricas['Respuesta al cliente (202)'] = f'{segundos} s'
    e.metricas['Resolución por el reconciliador'] = f'{resuelto} s'
    foto(e, 'después', pid)
    p = pedido(pid)
    e.comprobar('HTTP 202 PAYMENT_PENDING', estado == 202 and cuerpo['codigo'] == 'PAYMENT_PENDING')
    e.comprobar('La bitácora registra el pago en verificación resuelto por el reconciliador', en_verificacion)
    e.comprobar('El reconciliador lo confirmó', resuelto is not None and p['estado'] == 'confirmado')
    e.comprobar('Un solo cargo en la pasarela', len(cobros(p['clave_idempotencia'])) == 1)
    e.comprobar('Stock descontado y reserva liberada', inventario() == {
        'disponible': antes['disponible'] - 1, 'reservado': antes['reservado']})
    cierre(e, pid)
    return e


def e04_error_sin_cobro(c: Cliente) -> Escenario:
    e = Escenario('E04', 'La pasarela responde 503 sin cobrar',
                  'Error 503 en todos los intentos; el cargo nunca ocurrió',
                  'Pasarela en modo «error_antes».',
                  'HTTP 202 (resultado desconocido); tras el periodo de gracia el reconciliador comprueba que no '
                  'existe el cobro y compensa: pedido cancelado y stock liberado.')
    c.pasarela('error_antes')
    preparar_carrito()
    antes = inventario()
    estado, cuerpo, segundos = c.checkout(str(uuid.uuid4()))
    e.paso(f'POST /orders/checkout → HTTP {estado} en {segundos} s')
    e.seccion('Respuesta al cliente', cuerpo)
    pid = cuerpo['pedido_id']
    c.pasarela('aprobar')
    resuelto = esperar(lambda: pedido(pid)['estado'] == 'cancelado', settings.RECONCILIADOR_GRACIA_S + 40)
    e.paso(f'El reconciliador compensó el pedido {resuelto} s después (gracia configurada: '
           f'{settings.RECONCILIADOR_GRACIA_S} s)')
    e.metricas['Compensación por el reconciliador'] = f'{resuelto} s'
    foto(e, 'después', pid)
    p = pedido(pid)
    e.comprobar('HTTP 202 PAYMENT_PENDING', estado == 202)
    e.comprobar('Pedido cancelado por pago_no_recibido', (p['estado'], p['motivo_cancelacion']) == ('cancelado', 'pago_no_recibido'))
    e.comprobar('Ningún cargo en la pasarela', cobros(p['clave_idempotencia']) == [])
    e.comprobar('Inventario igual que antes', inventario() == antes)
    cierre(e, pid)
    return e


def _caida_en(c: Cliente, codigo: str, punto: str, titulo: str, esperado: str, final: str) -> Escenario:
    e = Escenario(codigo, titulo, f'El proceso cae en el punto «{punto}»',
                  f'Punto de falla `{punto}` activado una vez (POST /admin/fallas).', esperado)
    c.pasarela('aprobar')
    c.falla(punto, 'una_vez')
    preparar_carrito()
    antes = inventario()
    estado, cuerpo, segundos = c.checkout(str(uuid.uuid4()))
    e.paso(f'POST /orders/checkout → HTTP {estado} en {segundos} s (el proceso "murió")')
    e.seccion('Respuesta al cliente', cuerpo)
    pid = ultimo_pedido_del_comprador()
    foto(e, 'justo después de la caída', pid)
    quedo_pendiente = pedido(pid)['estado'] == 'pendiente'
    limite = settings.CHECKOUT_RESERVA_MINUTOS * 60 + 30
    resuelto = esperar(lambda: pedido(pid)['estado'] == final, limite)
    e.paso(f'El recolector resolvió el pedido {resuelto} s después (reserva de '
           f'{settings.CHECKOUT_RESERVA_MINUTOS} min)')
    e.metricas['Resolución por el recolector'] = f'{resuelto} s'
    foto(e, 'después', pid)
    p = pedido(pid)
    e.comprobar('El cliente recibió un error (HTTP 500)', estado == 500)
    e.comprobar('El pedido quedó pendiente con su reserva', quedo_pendiente)
    e.comprobar(f'El recolector lo dejó {final}', p['estado'] == final)
    numero_cobros = len(cobros(p['clave_idempotencia']))
    if final == 'confirmado':
        e.comprobar('Un solo cargo en la pasarela', numero_cobros == 1)
        e.comprobar('Stock descontado una sola vez', inventario() == {
            'disponible': antes['disponible'] - 1, 'reservado': antes['reservado']})
    else:
        e.comprobar('Ningún cargo en la pasarela', numero_cobros == 0)
        e.comprobar('Inventario igual que antes', inventario() == antes)
    cierre(e, pid)
    return e


def e05_caida_antes_de_cobrar(c):
    return _caida_en(c, 'E05', 'checkout.despues_reserva', 'Caída entre la reserva y el cobro',
                     'El pedido queda pendiente reteniendo stock; al vencer la reserva el recolector consulta la '
                     'pasarela, no encuentra cargo y compensa.', 'cancelado')


def e06_caida_despues_de_cobrar(c):
    return _caida_en(c, 'E06', 'checkout.despues_cobro', 'Caída después de cobrar y antes de confirmar',
                     'El cargo existe pero el pedido quedó pendiente; el recolector consulta la pasarela con la misma '
                     'clave y confirma sin cobrar otra vez.', 'confirmado')


def e07_confirmacion_falla(c):
    return _caida_en(c, 'E07', 'checkout.confirmacion', 'Falla la transacción de confirmación',
                     'El rollback deja el pedido pendiente sin descontar stock; el recolector confirma con el cargo '
                     'existente.', 'confirmado')


def e08_doble_envio(c: Cliente) -> Escenario:
    e = Escenario('E08', 'Doble envío de la misma compra', 'Dos solicitudes simultáneas con la misma clave '
                  '(doble clic o reintento del navegador)',
                  'Dos hilos envían POST /orders/checkout a la vez con el mismo Idempotency-Key; luego un tercer reintento.',
                  'Un solo pedido y un solo cargo; la segunda solicitud recibe 409 (en proceso) o la repetición, '
                  'y el reintento posterior recibe el mismo pedido (200).')
    c.pasarela('aprobar', latencia_ms=1500)  # ventana para que las solicitudes se crucen
    preparar_carrito()
    clave = str(uuid.uuid4())
    resultados = []
    hilos = [threading.Thread(target=lambda: resultados.append(c.checkout(clave))) for _ in range(2)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    c.pasarela('aprobar', latencia_ms=0)
    for estado, cuerpo, segundos in resultados:
        e.paso(f'Solicitud simultánea → HTTP {estado} en {segundos} s')
    repetido = c.checkout(clave)
    e.paso(f'Reintento posterior con la misma clave → HTTP {repetido[0]}')
    e.seccion('Respuestas', {'simultaneas': [r[:2] for r in resultados], 'reintento': repetido[:2]})
    pedidos = sql('SELECT id FROM pedidos WHERE clave_idempotencia = :c', c=clave)
    pid = pedidos[0]['id'] if pedidos else None
    foto(e, 'después', pid)
    codigos = sorted(r[0] for r in resultados)
    e.comprobar('Exactamente un pedido con esa clave', len(pedidos) == 1)
    e.comprobar('Exactamente un cargo en la pasarela', len(cobros(clave)) == 1)
    e.comprobar('Una solicitud creó el pedido y la otra no duplicó (201 + 409/200)',
                codigos in ([200, 201], [201, 409]))
    e.comprobar('El reintento devolvió el mismo pedido (200, IDEMPOTENT_REPLAY)',
                repetido[0] == 200 and repetido[1].get('pedido_id') == pid)
    cierre(e, pid)
    return e


def e09_redis_caido(c: Cliente) -> Escenario:
    e = Escenario('E09', 'Redis no disponible al iniciar el checkout', 'El carrito (Redis) no responde',
                  '`docker pause tiendaya_redis` antes de enviar la compra.',
                  'HTTP 503 CART_UNAVAILABLE sin crear pedido ni tocar inventario; al volver Redis el carrito sigue ahí.')
    preparar_carrito()
    antes_pedidos = ultimo_pedido_del_comprador()
    antes = inventario()
    docker('pause', 'tiendaya_redis')
    e.paso('Redis pausado')
    try:
        estado, cuerpo, segundos = c.checkout(str(uuid.uuid4()))
        e.paso(f'POST /orders/checkout → HTTP {estado} en {segundos} s')
    finally:
        docker('unpause', 'tiendaya_redis')
        e.paso('Redis reanudado')
    e.seccion('Respuesta al cliente', cuerpo)
    foto(e, 'después')
    e.comprobar('HTTP 503 CART_UNAVAILABLE', estado == 503 and cuerpo['detail']['code'] == 'CART_UNAVAILABLE')
    e.comprobar('No se creó ningún pedido', ultimo_pedido_del_comprador() == antes_pedidos)
    e.comprobar('Inventario intacto', inventario() == antes)
    # El cliente Redis reabre su conexión tras la pausa; se da un margen breve.
    e.comprobar('El carrito sigue disponible al volver Redis',
                esperar(lambda: carrito() == [OFERTA], 10) is not None)
    cierre(e, None)
    return e


def _componente_caido(c: Cliente, codigo: str, contenedor: str, destino: str, nombre: str,
                      extra=None, verificacion_final=None) -> Escenario:
    e = Escenario(codigo, f'{nombre} caído durante una compra',
                  f'{nombre} detenido (`docker stop {contenedor}`)',
                  f'Se detiene {nombre}, se compra, se espera y se vuelve a arrancar.',
                  f'La compra se confirma igual (MySQL es la autoridad); los eventos hacia {nombre} esperan en el '
                  f'outbox con backoff y convergen al volver el servicio, sin afectar a los demás destinos.')
    c.pasarela('aprobar')
    preparar_carrito()
    docker('stop', contenedor)
    e.paso(f'{nombre} detenido')
    estado, cuerpo, segundos = c.checkout(str(uuid.uuid4()))
    e.paso(f'POST /orders/checkout → HTTP {estado} en {segundos} s')
    e.seccion('Respuesta al cliente', cuerpo)
    pid = cuerpo['pedido_id'] if isinstance(cuerpo, dict) and 'pedido_id' in cuerpo else None
    if extra:
        extra(e)
    # El índice de búsqueda lee el catálogo de MongoDB al indexar: depende de él.
    dependientes = {destino} | ({'busqueda'} if destino == 'mongo' else set())

    def otros_al_dia():
        return bool(pid) and all(
            set(estados) == {'procesado'}
            for d, estados in outbox(pid).items() if d not in dependientes
        )
    # Con un consumidor por destino, los demás se procesan sin esperar al caído.
    otros = esperar(otros_al_dia, 30)
    time.sleep(3)
    retenido = outbox(pid).get(destino, {}) if pid else {}
    e.metricas['Demás destinos al día, con el componente aún caído'] = f'{otros} s'
    foto(e, f'con {nombre} caído', pid)
    docker('start', contenedor)
    reinicio = time.monotonic()
    e.paso(f'{nombre} arrancado de nuevo')
    sano = esperar(lambda: salud(contenedor) == 'healthy', 240, 2)
    e.paso(f'{nombre} saludable tras {sano} s')
    convergio = esperar(lambda: outbox_al_dia(pid), 400, 1)
    ventana = round(time.monotonic() - reinicio, 1)
    e.paso(f'Outbox del pedido al día {ventana} s después de reiniciar {nombre}')
    e.metricas['Respuesta del checkout con el componente caído'] = f'{segundos} s'
    e.metricas[f'{nombre} saludable tras reiniciar'] = f'{sano} s'
    e.metricas['Ventana de consistencia eventual (desde el reinicio)'] = f'{ventana} s'
    foto(e, 'después', pid)
    e.comprobar('La compra se confirmó con el componente caído', estado == 201)
    e.comprobar(f'Los eventos hacia {nombre} quedaron retenidos (no perdidos)',
                bool(retenido) and set(retenido) != {'procesado'})
    e.comprobar('Los demás destinos no se bloquearon (al día con el componente aún caído)', otros is not None)
    e.comprobar(f'Al volver {nombre}, todo el outbox del pedido convergió', convergio is not None)
    if verificacion_final:
        verificacion_final(e, pid)
    cierre(e, pid)
    return e


def e10_mongo(c):
    return _componente_caido(c, 'E10', 'tiendaya_mongo', 'mongo', 'MongoDB')


def e11_elasticsearch(c):
    def busqueda_degradada(e):
        r = c.buscar('granola')
        e.seccion('Búsqueda con Elasticsearch caído', {'motor': r.get('motor'), 'degradado': r.get('degradado'),
                                                      'total': r.get('total')})
        e.comprobar('La búsqueda siguió funcionando en modo degradado (MongoDB)',
                    r.get('degradado') is True and r.get('total', 0) >= 1)

    def busqueda_restaurada(e, pid):
        r = c.buscar('granola')
        e.comprobar('Al volver, la búsqueda usa Elasticsearch otra vez', r.get('motor') == 'elasticsearch')
    return _componente_caido(c, 'E11', 'tiendaya_elasticsearch', 'busqueda', 'Elasticsearch',
                             busqueda_degradada, busqueda_restaurada)


def e12_neo4j(c):
    def compra_registrada(e, pid):
        from app.core.db_neo4j import get_driver
        with get_driver().session() as s:
            aristas = s.run('MATCH ()-[c:COMPRO {pedido_id: $p}]->() RETURN count(c) AS n', p=pid).single()['n']
        e.comprobar('La compra quedó registrada en Neo4j (arista COMPRO): habilita reseña verificada', aristas >= 1)
    return _componente_caido(c, 'E12', 'tiendaya_neo4j', 'neo4j', 'Neo4j', None, compra_registrada)


def e13_cassandra(c):
    return _componente_caido(c, 'E13', 'tiendaya_cassandra', 'cassandra', 'Cassandra')


ESCENARIOS = {
    'E00': e00_linea_base, 'E01': e01_rechazo, 'E02': e02_cobrar_y_fallar, 'E03': e03_timeout,
    'E04': e04_error_sin_cobro, 'E05': e05_caida_antes_de_cobrar, 'E06': e06_caida_despues_de_cobrar,
    'E07': e07_confirmacion_falla, 'E08': e08_doble_envio, 'E09': e09_redis_caido,
    'E10': e10_mongo, 'E11': e11_elasticsearch, 'E12': e12_neo4j, 'E13': e13_cassandra,
}


def main() -> int:
    elegidos = [a.upper() for a in sys.argv[1:]] or list(ESCENARIOS)
    if not settings.FAULT_INJECTION_ENABLED:
        print('Requiere FAULT_INJECTION_ENABLED=true en backend/.env (y el backend reiniciado).')
        return 2
    SALIDA.mkdir(parents=True, exist_ok=True)
    r = get_redis()
    clave_carrito = f'carrito:{COMPRADOR_ID}'
    respaldo = r.hgetall(clave_carrito)
    cliente = Cliente()
    resultados = []
    log(f'Escenarios: {", ".join(elegidos)} · reserva {settings.CHECKOUT_RESERVA_MINUTOS} min · '
        f'gracia {settings.RECONCILIADOR_GRACIA_S} s')
    try:
        for codigo in elegidos:
            log(f'── {codigo} ──')
            try:
                escenario = ESCENARIOS[codigo](cliente)
            except Exception as exc:  # El escenario no pudo completarse: se registra igual.
                escenario = Escenario(codigo, ESCENARIOS[codigo].__name__, '—', '—', '—')
                escenario.comprobar(f'Ejecución sin errores ({exc.__class__.__name__}: {exc})', False)
            (SALIDA / f'{codigo}.md').write_text(escenario.markdown(), encoding='utf-8')
            resultados.append(escenario)
    finally:
        cliente.pasarela('aprobar', latencia_ms=0)
        cliente.http.delete('/admin/fallas', headers=cliente.admin)
        r.delete(clave_carrito)
        if respaldo:
            r.hset(clave_carrito, mapping=respaldo)

    # Una corrida parcial (p. ej. `demo_fallas.py E10`) conserva las filas de los demás escenarios.
    indice = SALIDA / 'README.md'
    filas = {}
    if indice.exists():
        for linea in indice.read_text(encoding='utf-8').splitlines():
            if m := re.match(r'\| \[(E\d+) ', linea):
                filas[m.group(1)] = linea
    for e in resultados:
        clave = next(iter(e.metricas.items()), ('', ''))
        metrica = f'{clave[0]}: {clave[1]}' if clave[0] else '—'
        filas[e.codigo] = (f'| [{e.codigo} · {e.titulo}]({e.codigo}.md) | {e.falla} | '
                           f'{"✅" if e.ok else "❌"} | {metrica} |')
    resumen = [
        '# Pruebas de falla del checkout distribuido — resumen', '',
        f'Actualizado el {datetime.now():%Y-%m-%d %H:%M} con `backend/scripts/demo_fallas.py` contra el sistema '
        'en ejecución (API, pasarela simulada y contenedores Docker reales). Cada escenario tiene la hora '
        'exacta de su corrida en su propio archivo.', '',
        '| Escenario | Falla | Resultado | Métrica clave |', '|---|---|---|---|',
        *(filas[c] for c in sorted(filas)),
    ]
    indice.write_text('\n'.join(resumen) + '\n', encoding='utf-8')
    superados = sum(e.ok for e in resultados)
    log(f'Resultado: {superados}/{len(resultados)} escenarios superados. Evidencia en {SALIDA}')
    return 0 if superados == len(resultados) else 1


if __name__ == '__main__':
    raise SystemExit(main())
