"""Consistencia del checkout distribuido: invariantes, fallas simuladas y saga (solo admin)."""

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from pymongo.database import Database
from sqlalchemy.orm import Session

from app.core import fault_injection
from app.core.config import settings
from app.core.db_mongo import get_mongo_db
from app.core.db_mysql import get_db
from app.core.deps import get_admin_user, get_es
from app.models.checkout_saga import CheckoutSagaPaso
from app.models.pago import Pago
from app.models.pedido import Pedido
from app.models.usuario import Usuario
from app.services import casos_falla_service, consistency_service
from app.services.checkout_recovery_worker import reconcile_once

# Diagnóstico de solo lectura (invariantes y bitácora de la saga): siempre disponible para admin.
router = APIRouter(prefix='/admin', tags=['Consistencia'])
# Control de fallas y recuperación manual: herramienta de desarrollo que usa el
# laboratorio de consistencia. main.py solo lo registra con FAULT_INJECTION_ENABLED,
# así que en producción estos endpoints no existen.
router_fallas = APIRouter(prefix='/admin', tags=['Laboratorio de consistencia (solo desarrollo)'])

MODOS_PASARELA = ('aprobar', 'rechazar', 'timeout', 'cobrar_y_fallar', 'error_antes')


class FallaPayload(BaseModel):
    punto: str
    modo: str = Field('una_vez', description="'una_vez', 'siempre' u 'off'")


class PasarelaPayload(BaseModel):
    modo: str = 'aprobar'
    latencia_ms: int = Field(0, ge=0, le=60_000)
    demora_timeout_s: float = Field(8.0, ge=0, le=120)


def _exigir_fallas_habilitadas() -> None:
    if not fault_injection.habilitada():
        raise HTTPException(403, detail={
            'detail': 'La inyección de fallas está deshabilitada (FAULT_INJECTION_ENABLED=false).',
            'code': 'FAULT_INJECTION_DISABLED',
        })


# Verifica los invariantes: sin sobreventa, reservas explicadas, cobros ↔ pedidos, proyecciones
@router.get('/consistencia')
def verificar_consistencia(
    _: Usuario = Depends(get_admin_user),
    db: Session = Depends(get_db),
    mongo: Database = Depends(get_mongo_db),
    es=Depends(get_es),
):
    return consistency_service.verificar(db, mongo, es)


@router.get('/fallas')
def estado_fallas(_: Usuario = Depends(get_admin_user)):
    try:
        pasarela = httpx.get(f'{settings.PAYMENT_GATEWAY_URL}/control', timeout=2).json()
    except httpx.HTTPError:
        pasarela = None
    return {**fault_injection.estado(), 'pasarela': pasarela}


# Activa (una vez o siempre) o desactiva un punto de falla del checkout o del outbox
@router_fallas.post('/fallas')
def configurar_falla(payload: FallaPayload, _: Usuario = Depends(get_admin_user)):
    _exigir_fallas_habilitadas()
    try:
        if payload.modo == 'off':
            fault_injection.desactivar(payload.punto)
        else:
            fault_injection.activar(payload.punto, payload.modo)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return fault_injection.estado()


@router_fallas.delete('/fallas')
def desactivar_fallas(_: Usuario = Depends(get_admin_user)):
    fault_injection.desactivar()
    return fault_injection.estado()


# Cambia el comportamiento de la pasarela simulada (aprobar, rechazar, timeout...)
@router_fallas.post('/fallas/pasarela')
def configurar_pasarela(payload: PasarelaPayload, _: Usuario = Depends(get_admin_user)):
    _exigir_fallas_habilitadas()
    if payload.modo not in MODOS_PASARELA:
        raise HTTPException(422, f'Modo desconocido. Opciones: {", ".join(MODOS_PASARELA)}')
    try:
        respuesta = httpx.post(f'{settings.PAYMENT_GATEWAY_URL}/control', json=payload.model_dump(), timeout=3)
        respuesta.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(503, f'Pasarela simulada no disponible: {exc.__class__.__name__}') from exc
    return respuesta.json()


# Casos de falla específicos («¿qué pasa si Redis se cae justo al comprar?»)
@router_fallas.get('/fallas/casos')
def casos_falla(_: Usuario = Depends(get_admin_user)):
    return casos_falla_service.listar()


# Prepara un caso: limpia los demás puntos, pasarela aprobando y arma los del caso una vez
@router_fallas.post('/fallas/casos/{caso_id}/preparar')
def preparar_caso(caso_id: str, _: Usuario = Depends(get_admin_user)):
    _exigir_fallas_habilitadas()
    try:
        return casos_falla_service.preparar(caso_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(503, f'Pasarela simulada no disponible: {exc.__class__.__name__}') from exc


# Ejecuta ya el reconciliador y el recolector (sin esperar al ciclo del worker)
@router_fallas.post('/checkout/recuperar')
def recuperar_checkout(_: Usuario = Depends(get_admin_user)):
    return reconcile_once()


# Bitácora de la saga: últimas transiciones, con el estado actual del pedido y su pago
@router.get('/checkout/saga')
def bitacora_saga(
    pedido_id: int | None = Query(None),
    limite: int = Query(60, ge=1, le=500),
    _: Usuario = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    consulta = (
        db.query(CheckoutSagaPaso, Pedido.estado, Pedido.motivo_cancelacion, Pago.estado)
        .join(Pedido, Pedido.id == CheckoutSagaPaso.pedido_id)
        .outerjoin(Pago, Pago.pedido_id == Pedido.id)
    )
    if pedido_id is not None:
        consulta = consulta.filter(CheckoutSagaPaso.pedido_id == pedido_id)
    return [
        {
            'id': paso.id,
            'pedido_id': paso.pedido_id,
            'paso': paso.paso,
            'resultado': paso.resultado,
            'detalle': paso.detalle,
            'creado_en': paso.creado_en.isoformat() if paso.creado_en else None,
            'pedido_estado': pedido_estado,
            'motivo_cancelacion': motivo,
            'pago_estado': pago_estado,
        }
        for paso, pedido_estado, motivo, pago_estado in
        consulta.order_by(CheckoutSagaPaso.id.desc()).limit(limite)
    ]
