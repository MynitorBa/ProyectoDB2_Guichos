from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.db_mongo import get_mongo_db
from app.core.db_mysql import get_db
from app.models.vendedor import Vendedor
from app.services.store_config_service import DEFAULT_SECCIONES, DEFAULT_TEMA, get_config

router = APIRouter(prefix='/stores', tags=['Tiendas'])


@router.get('/{vendor_id}')
def get_store_profile(vendor_id: int, db: Session = Depends(get_db)):
    vendor = db.get(Vendedor, vendor_id)
    if not vendor:
        raise HTTPException(404, 'Tienda no encontrada.')
    return {
        'id': vendor.id,
        'nombre_comercial': vendor.nombre_comercial,
        'descripcion': vendor.descripcion,
        'logo_url': vendor.logo_url,
        'es_tiendaya': vendor.es_tiendaya,
        'fecha_registro': vendor.fecha_registro.isoformat() if vendor.fecha_registro else None,
    }


@router.get('/{vendor_id}/config')
def get_store_config_public(
    vendor_id: int,
    db: Session = Depends(get_db),
    mongo_db=Depends(get_mongo_db),
):
    vendor = db.get(Vendedor, vendor_id)
    if not vendor:
        raise HTTPException(404, 'Tienda no encontrada.')
    config = get_config(mongo_db, vendor_id)
    if config:
        return config
    return {'tema': DEFAULT_TEMA, 'secciones': DEFAULT_SECCIONES, 'vendedor_id': vendor_id}
