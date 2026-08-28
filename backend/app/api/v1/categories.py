from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pymongo.database import Database

from app.core.db_mysql import get_db
from app.core.db_mongo import get_mongo_db
from app.models.categoria import Categoria

router = APIRouter(prefix='/categories', tags=['Categorías'])


# Lista categorías activas ordenadas por el campo 'orden' para respetar la jerarquía visual
@router.get('/')
def listar_categorias(db: Session = Depends(get_db)):
    categorias = db.query(Categoria).filter_by(activa=True).order_by(Categoria.orden).all()
    return [
        {
            'id': c.id,
            'nombre': c.nombre,
            'slug': c.slug,
            'descripcion': c.descripcion,
            'padre_id': c.categoria_padre_id,
            'imagen_url': c.imagen_url,
        }
        for c in categorias
    ]


# Devuelve la definición de atributos de una categoría desde MongoDB (usada por el frontend para renderizar formularios dinámicos)
@router.get('/{slug}/schema')
def esquema_categoria(slug: str, mongo_db: Database = Depends(get_mongo_db)):
    esquema = mongo_db.categoria_esquemas.find_one({'categoria_slug': slug})
    if not esquema:
        raise HTTPException(status_code=404, detail=f'Esquema para categoría "{slug}" no encontrado.')
    esquema['_id'] = str(esquema['_id'])
    return esquema
