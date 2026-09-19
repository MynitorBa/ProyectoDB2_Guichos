"""Endpoints privados del editor de tienda (solo vendedores verificados)."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.db_mongo import get_mongo_db
from app.core.db_mysql import get_db
from app.core.deps import get_current_user, require_role
from app.models.usuario import Usuario
from app.models.vendedor import Vendedor
from app.services.store_config_service import DEFAULT_SECCIONES, DEFAULT_TEMA, get_config, save_config

router = APIRouter(prefix='/vendor/store', tags=['Editor de tienda'])
_require_vendor = require_role('vendedor', 'administrador')


def _get_verified_vendor(user: Usuario, db: Session) -> Vendedor:
    vendor = db.query(Vendedor).filter_by(usuario_id=user.id, estado_verificacion='verificado').first()
    if not vendor:
        raise HTTPException(403, 'Necesitas un perfil de vendedor verificado.')
    return vendor


class StoreConfigPayload(BaseModel):
    tema: dict[str, Any] = {}
    secciones: list[dict[str, Any]] = []


@router.get('/config')
def get_store_config(
    user: Usuario = Depends(_require_vendor),
    db: Session = Depends(get_db),
    mongo_db=Depends(get_mongo_db),
):
    vendor = _get_verified_vendor(user, db)
    config = get_config(mongo_db, vendor.id)
    if config:
        return config
    return {'tema': DEFAULT_TEMA, 'secciones': DEFAULT_SECCIONES, 'vendedor_id': vendor.id}


@router.put('/config')
def save_store_config(
    payload: StoreConfigPayload,
    user: Usuario = Depends(_require_vendor),
    db: Session = Depends(get_db),
    mongo_db=Depends(get_mongo_db),
):
    vendor = _get_verified_vendor(user, db)
    return save_config(mongo_db, vendor.id, payload.model_dump())
