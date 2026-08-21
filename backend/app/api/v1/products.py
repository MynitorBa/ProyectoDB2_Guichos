from fastapi import APIRouter, Depends, HTTPException, Query
from pymongo.database import Database

from app.core.db_mongo import get_mongo_db
from app.services import catalog_service

router = APIRouter(prefix='/products', tags=['Productos'])


@router.get('/')
def listar_productos(
    categoria: str | None = Query(None),
    precio_min: float | None = Query(None),
    precio_max: float | None = Query(None),
    disponible: bool | None = Query(None),
    q: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    orden: str = Query('precio_asc', enum=['precio_asc', 'precio_desc', 'nombre_asc', 'reciente']),
    db: Database = Depends(get_mongo_db),
):
    return catalog_service.listar_productos(
        db,
        categoria_slug=categoria,
        precio_min=precio_min,
        precio_max=precio_max,
        disponible=disponible,
        q=q,
        page=page,
        page_size=page_size,
        orden=orden,
    )


@router.get('/{producto_id}')
def obtener_producto(producto_id: str, db: Database = Depends(get_mongo_db)):
    producto = catalog_service.obtener_producto(db, producto_id)
    if not producto:
        raise HTTPException(status_code=404, detail='Producto no encontrado.')
    return producto
