from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pymongo.database import Database
from sqlalchemy.orm import Session

from app.core.db_mongo import get_mongo_db
from app.core.db_mysql import get_db
from app.core.db_redis import get_redis
from app.core.deps import get_current_user, get_es, get_optional_user
from app.models.usuario import Usuario
from app.models.producto_imagen import ProductoImagen
from app.services import catalog_service
from app.services import recommendation_service
from app.services import para_ti_service, similares_service

router = APIRouter(prefix='/products', tags=['Productos'])


# Catálogo público con filtros de categoría, precio, disponibilidad, búsqueda y paginación; los precios vienen de MySQL
@router.get('/')
def listar_productos(
    categoria: str | None = Query(None),
    precio_min: float | None = Query(None),
    precio_max: float | None = Query(None),
    disponible: bool | None = Query(None),
    q: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    orden: str = Query('precio_asc', enum=['precio_asc', 'precio_desc', 'nombre_asc', 'reciente', 'mas_vendidos', 'descuento_desc']),
    vendedor_id: int | None = Query(None),
    solo_flash: bool = Query(False),
    db: Database = Depends(get_mongo_db),
    mysql_db: Session = Depends(get_db),
    redis_db = Depends(get_redis),
):
    return catalog_service.listar_productos(
        db,
        mysql_db,
        categoria_slug=categoria,
        precio_min=precio_min,
        precio_max=precio_max,
        disponible=disponible,
        q=q,
        page=page,
        page_size=page_size,
        orden=orden,
        vendedor_id=vendedor_id,
        solo_flash=solo_flash,
        redis_db=redis_db,
    )


@router.get('/para-ti')
def te_podria_interesar(
    vistos: str | None = Query(None, description='Productos vistos en este navegador, separados por coma'),
    limite: int = Query(8, ge=1, le=20),
    user: Usuario | None = Depends(get_optional_user),
    db: Database = Depends(get_mongo_db),
    mysql_db: Session = Depends(get_db),
    redis_db=Depends(get_redis),
    es=Depends(get_es),
):
    """«Te podría interesar» del inicio: vecinos por vector del carrito y lo visto."""
    return para_ti_service.recomendar(
        mysql_db, db, es, redis_db, usuario_id=user.id if user else None,
        vistos_cliente=(vistos or '').split(','), limite=limite,
    )


@router.post('/{producto_id}/visto', status_code=204)
def registrar_visto(
    producto_id: str,
    user: Usuario = Depends(get_current_user),
    redis_db=Depends(get_redis),
):
    """Historial de vistos del usuario (Redis); alimenta «Te podría interesar»."""
    para_ti_service.registrar_visto(redis_db, user.id, producto_id)


# Sirve imágenes almacenadas como BLOB en MySQL con caché de 24 horas
@router.get('/images/{image_id}')
def servir_imagen(
    image_id: int,
    mysql_db: Session = Depends(get_db),
):
    img = mysql_db.get(ProductoImagen, image_id)
    if not img or not img.datos:
        raise HTTPException(status_code=404, detail='Imagen no encontrada.')
    return Response(
        content=img.datos,
        media_type=img.mime_type,
        headers={'Cache-Control': 'public, max-age=86400'},
    )


@router.get('/{producto_id}/recommendations')
def recomendaciones_producto(
    producto_id: str,
    limite: int = Query(8, ge=1, le=20),
    user: Usuario | None = Depends(get_optional_user),
    db: Database = Depends(get_mongo_db),
    mysql_db: Session = Depends(get_db),
):
    items, origen = recommendation_service.recomendar_con_origen(
        mysql_db, db, producto_ref=producto_id,
        usuario_id=user.id if user else None, limite=limite,
    )
    # origen: 'grafo' (Neo4j), 'cache' (copia horaria en MySQL) o 'mas_vendidos'.
    return {'items': items, 'origen': origen}


@router.get('/{producto_id}/similares')
def productos_similares(
    producto_id: str,
    excluir: str | None = Query(None, description='Referencias separadas por coma que ya se muestran'),
    limite: int = Query(8, ge=1, le=20),
    db: Database = Depends(get_mongo_db),
    mysql_db: Session = Depends(get_db),
    redis_db=Depends(get_redis),
    es=Depends(get_es),
):
    """«También te podría interesar»: vecinos por vector (kNN en Elasticsearch)."""
    items, origen = similares_service.similares(
        mysql_db, db, es, redis_db, producto_ref=producto_id,
        excluir=[r for r in (excluir or '').split(',') if r], limite=limite,
    )
    # origen: 'vectores' o 'mas_vendidos' (respaldo si el índice no responde).
    return {'items': items, 'origen': origen}


# Detalle de un producto por su _id de MongoDB enriquecido con todas las ofertas activas de MySQL
@router.get('/{producto_id}')
def obtener_producto(
    producto_id: str,
    db: Database = Depends(get_mongo_db),
    mysql_db: Session = Depends(get_db),
):
    producto = catalog_service.obtener_producto(db, producto_id, mysql_db)
    if not producto:
        raise HTTPException(status_code=404, detail='Producto no encontrado.')
    return producto
