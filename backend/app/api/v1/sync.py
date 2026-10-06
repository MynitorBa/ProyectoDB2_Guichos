"""Observabilidad y operación de la sincronización entre componentes (solo admin)."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from pymongo.database import Database
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db_mongo import get_mongo_db
from app.core.db_mysql import get_db
from app.core.deps import get_admin_user
from app.models.outbox import DESTINOS_OUTBOX
from app.models.usuario import Usuario
from app.services import outbox_service

router = APIRouter(prefix='/admin/sync', tags=['Sincronización'])


class ReintentoPayload(BaseModel):
    evento_id: str | None = None
    destino: str | None = None


# Estado del outbox por destino: pendientes, errores, fallidos y antigüedad del más viejo
@router.get('/outbox')
def resumen_outbox(
    _: Usuario = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    return {
        'destinos': outbox_service.resumen_por_destino(db),
        'problemas': outbox_service.listar_eventos(db, estados=['error', 'fallido'], limite=50),
    }


@router.get('/outbox/eventos')
def eventos_outbox(
    estado: list[str] = Query(['pendiente', 'procesando', 'error', 'fallido']),
    destino: str | None = Query(None, enum=list(DESTINOS_OUTBOX)),
    limite: int = Query(50, ge=1, le=500),
    _: Usuario = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    return outbox_service.listar_eventos(db, estados=estado, destino=destino, limite=limite)


# Devuelve a 'pendiente' los eventos en error o fallidos (uno, por destino o todos)
@router.post('/outbox/reintentar')
def reintentar_outbox(
    payload: ReintentoPayload,
    _: Usuario = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    if payload.destino and payload.destino not in DESTINOS_OUTBOX:
        raise HTTPException(422, 'Destino desconocido.')
    return {'reintentados': outbox_service.reintentar(
        db, evento_id=payload.evento_id, destino=payload.destino
    )}


# Compara el índice de búsqueda con el catálogo de MongoDB
@router.get('/busqueda')
def estado_busqueda(
    _: Usuario = Depends(get_admin_user),
    mongo: Database = Depends(get_mongo_db),
):
    from app.core.db_elastic import get_es
    from app.services.search_index_service import indice_actual

    activos = mongo.productos.count_documents({'estado': 'activo'})
    try:
        es = get_es()
        return {
            'disponible': True,
            'indice': indice_actual(es),
            'documentos': es.count(index=settings.ES_INDEX_ALIAS)['count'],
            'productos_activos': activos,
        }
    except Exception as exc:
        return {'disponible': False, 'error': str(exc)[:300], 'productos_activos': activos}


# Reindexa lo desfasado (o todo con completo=true) sin esperar la reconciliación periódica
@router.post('/busqueda/reindexar')
def reindexar_busqueda(
    completo: bool = Query(False),
    _: Usuario = Depends(get_admin_user),
    db: Session = Depends(get_db),
    mongo: Database = Depends(get_mongo_db),
):
    from app.core.db_elastic import get_es
    from app.services import search_index_service as indice

    es = get_es().options(request_timeout=30)
    try:
        if completo:
            refs = [str(d['_id']) for d in mongo.productos.find({'estado': 'activo'}, {'_id': 1})]
            sobrantes = sorted(set(indice.ids_indexados(es)) - set(refs))
            return indice.indexar_productos(es, db, mongo, refs + sobrantes, refrescar=True)
        return indice.reconciliar_desfasados(es, db, mongo)
    except Exception as exc:
        raise HTTPException(503, f'Elasticsearch no disponible: {str(exc)[:200]}') from exc
