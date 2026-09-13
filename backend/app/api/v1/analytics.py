"""Consultas de tendencias servidas desde Cassandra."""

from datetime import date

from cassandra import DriverException
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.db_cassandra import cassandra_health
from app.core.db_mysql import get_db
from app.core.deps import get_admin_user, require_role
from app.models.usuario import Usuario
from app.models.vendedor import Vendedor
from app.services.analytics_service import (
    current_week_start,
    product_trends,
    vendor_offer_summary,
)


router = APIRouter(prefix='/analytics', tags=['Analítica Cassandra'])
get_vendor_user = require_role('vendedor', 'administrador')


def _week(value: date | None) -> date:
    chosen = value or current_week_start()
    if chosen.weekday() != 0:
        raise HTTPException(422, 'semana_inicio debe ser un lunes.')
    return chosen


def _unavailable(exc: Exception) -> HTTPException:
    return HTTPException(
        503,
        'La analítica histórica no está disponible temporalmente; las compras continúan funcionando.',
    )


@router.get('/health')
def health(_: Usuario = Depends(get_admin_user)):
    try:
        return cassandra_health()
    except DriverException as exc:
        raise _unavailable(exc) from exc


@router.get('/admin/trends')
def admin_trends(
    semana_inicio: date | None = Query(None),
    _: Usuario = Depends(get_admin_user),
):
    selected = _week(semana_inicio)
    try:
        items = product_trends(selected)
    except DriverException as exc:
        raise _unavailable(exc) from exc
    return {'semana_inicio': selected.isoformat(), 'items': items}


@router.get('/vendor/trends')
def vendor_trends(
    semana_inicio: date | None = Query(None),
    user: Usuario = Depends(get_vendor_user),
    db: Session = Depends(get_db),
):
    vendor = db.query(Vendedor).filter_by(usuario_id=user.id).first()
    if not vendor:
        raise HTTPException(403, 'No tienes perfil de vendedor configurado.')
    selected = _week(semana_inicio)
    try:
        items = vendor_offer_summary(vendor.id, selected)
    except DriverException as exc:
        raise _unavailable(exc) from exc
    return {
        'semana_inicio': selected.isoformat(),
        'vendedor_id': vendor.id,
        'items': items,
    }
