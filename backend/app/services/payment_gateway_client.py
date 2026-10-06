"""Cliente de la pasarela de pagos (externa, no transaccional).

Distingue tres desenlaces, porque cada uno exige una reacción distinta del
checkout:

- **Definitivo** (``aprobado`` / ``rechazado``): la pasarela respondió.
- **No enviado**: no se pudo abrir la conexión. Es seguro afirmar que no hubo
  cargo, así que el pedido se puede compensar de inmediato.
- **Desconocido**: la solicitud salió pero no llegó una respuesta válida
  (timeout o error 5xx). Pudo haberse cobrado; el pedido queda en
  verificación y el reconciliador consulta la pasarela con la misma clave.

Los reintentos usan siempre la misma clave idempotente, así que nunca generan
un segundo cargo.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from decimal import Decimal

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

APROBADO = 'aprobado'
RECHAZADO = 'rechazado'
REEMBOLSADO = 'reembolsado'
NO_ENCONTRADO = 'no_encontrado'
NO_ENVIADO = 'no_enviado'
DESCONOCIDO = 'desconocido'


@dataclass
class ResultadoPasarela:
    estado: str
    referencia: str | None = None
    motivo: str | None = None
    intentos: int = 0
    detalle: list[str] = field(default_factory=list)

    @property
    def definitivo(self) -> bool:
        return self.estado in (APROBADO, RECHAZADO, REEMBOLSADO)


class PasarelaPagos:
    def __init__(self, base_url: str | None = None, timeout: float | None = None, reintentos: int | None = None):
        self.base_url = (base_url or settings.PAYMENT_GATEWAY_URL).rstrip('/')
        self.timeout = timeout if timeout is not None else settings.PAYMENT_TIMEOUT
        self.reintentos = reintentos if reintentos is not None else settings.PAYMENT_RETRIES

    def _cliente(self) -> httpx.Client:
        return httpx.Client(base_url=self.base_url, timeout=self.timeout)

    def cobrar(self, clave: str, monto: Decimal, referencia: str, moneda: str = 'GTQ') -> ResultadoPasarela:
        """Solicita el cargo. Reintenta con la misma clave ante fallas de red o 5xx."""
        resultado = ResultadoPasarela(estado=NO_ENVIADO)
        cuerpo = {'monto': str(monto), 'moneda': moneda, 'referencia': referencia}
        for intento in range(1, self.reintentos + 2):
            resultado.intentos = intento
            try:
                with self._cliente() as cliente:
                    respuesta = cliente.post('/cobros', json=cuerpo, headers={'Idempotency-Key': clave})
            except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
                # Nunca se estableció la conexión (rechazada o sin respuesta al
                # abrirla): la pasarela no recibió nada, así que no hubo cargo.
                resultado.detalle.append(f'intento {intento}: sin conexión ({exc.__class__.__name__})')
            except httpx.TimeoutException as exc:
                # La solicitud pudo haberse procesado: a partir de aquí el
                # resultado ya no puede considerarse "no enviado".
                resultado.estado = DESCONOCIDO
                resultado.detalle.append(f'intento {intento}: timeout ({exc.__class__.__name__})')
            except httpx.HTTPError as exc:
                resultado.estado = DESCONOCIDO
                resultado.detalle.append(f'intento {intento}: error de red ({exc.__class__.__name__})')
            else:
                if respuesta.status_code >= 500:
                    resultado.estado = DESCONOCIDO
                    resultado.detalle.append(f'intento {intento}: HTTP {respuesta.status_code}')
                elif respuesta.status_code >= 400:
                    # Error del cliente (datos inválidos): la pasarela no cobró.
                    resultado.estado = RECHAZADO
                    resultado.motivo = f'solicitud_invalida_{respuesta.status_code}'
                    return resultado
                else:
                    datos = respuesta.json()
                    resultado.estado = datos['estado']
                    resultado.referencia = datos.get('id')
                    resultado.motivo = datos.get('motivo')
                    return resultado
            if intento <= self.reintentos:
                time.sleep(0.2 * intento)
        logger.warning('Cobro %s sin respuesta definitiva: %s', clave, resultado.detalle)
        return resultado

    def consultar(self, clave: str) -> ResultadoPasarela:
        """Estado actual del cobro asociado a la clave (para reconciliar)."""
        try:
            with self._cliente() as cliente:
                respuesta = cliente.get(f'/cobros/{clave}')
        except httpx.HTTPError as exc:
            return ResultadoPasarela(estado=DESCONOCIDO, detalle=[f'consulta: {exc.__class__.__name__}'])
        if respuesta.status_code == 404:
            return ResultadoPasarela(estado=NO_ENCONTRADO)
        if respuesta.status_code >= 400:
            return ResultadoPasarela(estado=DESCONOCIDO, detalle=[f'consulta: HTTP {respuesta.status_code}'])
        datos = respuesta.json()
        return ResultadoPasarela(estado=datos['estado'], referencia=datos.get('id'), motivo=datos.get('motivo'))

    def reembolsar(self, clave: str) -> ResultadoPasarela:
        """Compensación del cargo. Idempotente: reembolsar dos veces no devuelve dos veces."""
        try:
            with self._cliente() as cliente:
                respuesta = cliente.post(f'/cobros/{clave}/reembolso')
        except httpx.HTTPError as exc:
            return ResultadoPasarela(estado=DESCONOCIDO, detalle=[f'reembolso: {exc.__class__.__name__}'])
        if respuesta.status_code == 404:
            return ResultadoPasarela(estado=NO_ENCONTRADO)
        if respuesta.status_code >= 400:
            return ResultadoPasarela(estado=DESCONOCIDO, detalle=[f'reembolso: HTTP {respuesta.status_code}'])
        datos = respuesta.json()
        return ResultadoPasarela(estado=datos['estado'], referencia=datos.get('id'))


_pasarela: PasarelaPagos | None = None


def get_pasarela() -> PasarelaPagos:
    global _pasarela
    if _pasarela is None or _pasarela.base_url != settings.PAYMENT_GATEWAY_URL.rstrip('/'):
        _pasarela = PasarelaPagos()
    return _pasarela
