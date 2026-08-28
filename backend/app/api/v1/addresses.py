from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.db_mysql import get_db
from app.core.deps import get_current_user
from app.models.usuario import Usuario
from app.models.direccion import Direccion
from app.schemas.direccion import DireccionCreate, DireccionResponse

router = APIRouter(prefix='/addresses', tags=['Direcciones'])


# Solo devuelve las direcciones activas del usuario (las eliminadas se marcan activa=False)
@router.get('/', response_model=list[DireccionResponse])
def listar_direcciones(
    current_user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return db.query(Direccion).filter_by(usuario_id=current_user.id, activa=True).all()


# Si la nueva dirección es predeterminada, desactiva primero la predeterminada existente
@router.post('/', response_model=DireccionResponse, status_code=201)
def crear_direccion(
    payload: DireccionCreate,
    current_user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if payload.es_predeterminada:
        db.query(Direccion).filter_by(usuario_id=current_user.id).update({'es_predeterminada': False})

    dir_ = Direccion(usuario_id=current_user.id, **payload.model_dump())
    db.add(dir_)
    db.commit()
    db.refresh(dir_)
    return dir_


# Actualiza todos los campos de una dirección; aplica la misma lógica de predeterminada única
@router.put('/{dir_id}', response_model=DireccionResponse)
def actualizar_direccion(
    dir_id: int,
    payload: DireccionCreate,
    current_user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    dir_ = db.get(Direccion, dir_id)
    if not dir_ or dir_.usuario_id != current_user.id:
        raise HTTPException(status_code=404, detail='Dirección no encontrada.')

    if payload.es_predeterminada:
        db.query(Direccion).filter_by(usuario_id=current_user.id).update({'es_predeterminada': False})

    for k, v in payload.model_dump().items():
        setattr(dir_, k, v)

    db.commit()
    db.refresh(dir_)
    return dir_


# Borrado lógico: establece activa=False en lugar de eliminar el registro para preservar historial de pedidos
@router.delete('/{dir_id}', status_code=204)
def eliminar_direccion(
    dir_id: int,
    current_user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    dir_ = db.get(Direccion, dir_id)
    if not dir_ or dir_.usuario_id != current_user.id:
        raise HTTPException(status_code=404, detail='Dirección no encontrada.')
    dir_.activa = False
    db.commit()
