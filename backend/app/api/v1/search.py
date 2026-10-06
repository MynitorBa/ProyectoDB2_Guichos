from fastapi import APIRouter, Depends, Query, Request
from pymongo.database import Database
from sqlalchemy.orm import Session

from app.core.db_mongo import get_mongo_db
from app.core.db_mysql import get_db
from app.core.db_redis import get_redis
from app.core.deps import get_es
from app.services import search_service
from app.services.search_service import ORDENES, ParametrosBusqueda

router = APIRouter(prefix='/search', tags=['Búsqueda'])

PREFIJO_ATRIBUTO = 'attr.'


# Búsqueda de texto libre con tolerancia a errores, relevancia y facetas.
# Los atributos se filtran con parámetros repetibles attr.<nombre>=<valor>,
# por ejemplo ?attr.talla=M&attr.talla=L&attr.color=Azul
@router.get('')
def buscar_productos(
    request: Request,
    q: str = Query('', max_length=200),
    categoria: str | None = Query(None),
    vendedor: list[str] = Query([]),
    precio_min: float | None = Query(None, ge=0),
    precio_max: float | None = Query(None, ge=0),
    solo_stock: bool = Query(False),
    solo_flash: bool = Query(False),
    solo_tiendaya: bool = Query(False),
    orden: str | None = Query(None, enum=list(ORDENES)),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    es=Depends(get_es),
    mysql_db: Session = Depends(get_db),
    mongo: Database = Depends(get_mongo_db),
    redis_db=Depends(get_redis),
):
    atributos: dict[str, list[str]] = {}
    for clave in request.query_params:
        if clave.startswith(PREFIJO_ATRIBUTO) and len(clave) > len(PREFIJO_ATRIBUTO):
            valores = [v for v in request.query_params.getlist(clave) if v]
            if valores:
                atributos[clave[len(PREFIJO_ATRIBUTO):]] = valores
    parametros = ParametrosBusqueda(
        q=q, categoria=categoria, vendedores=vendedor,
        precio_min=precio_min, precio_max=precio_max, atributos=atributos,
        solo_stock=solo_stock, solo_flash=solo_flash, solo_tiendaya=solo_tiendaya,
        orden=orden, page=page, page_size=page_size,
    )
    return search_service.buscar(es, mysql_db, mongo, parametros, redis_db)


# Autocompletado mientras se escribe: productos (tolera errores) y categorías
@router.get('/suggest')
def sugerir_productos(
    q: str = Query(..., min_length=2, max_length=100),
    limite: int = Query(6, ge=1, le=10),
    es=Depends(get_es),
    mysql_db: Session = Depends(get_db),
    mongo: Database = Depends(get_mongo_db),
):
    return search_service.sugerir(es, mysql_db, mongo, q, limite)
