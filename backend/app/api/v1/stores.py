from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.db_mysql import get_db
from app.models.vendedor import Vendedor

router = APIRouter(prefix='/stores', tags=['Tiendas'])


# Perfil público de una tienda de vendedor; no requiere autenticación
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
