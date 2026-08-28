from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.db_mysql import get_db
from app.core.deps import get_current_user
from app.models.notificacion import Notificacion
from app.models.usuario import Usuario

GT_TZ = timezone(timedelta(hours=-6))
router = APIRouter(prefix='/notifications', tags=['Notificaciones'])


# Devuelve hasta 50 notificaciones del usuario: las no leídas primero, luego por fecha descendente
@router.get('/')
def listar_notificaciones(
    current_user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    notifs = (
        db.query(Notificacion)
        .filter_by(usuario_id=current_user.id)
        .order_by(Notificacion.leida.asc(), Notificacion.fecha_creacion.desc())
        .limit(50)
        .all()
    )
    return [
        {
            'id': n.id,
            'tipo': n.tipo,
            'titulo': n.titulo,
            'mensaje': n.mensaje,
            'leida': n.leida,
            'pedido_id': n.pedido_id,
            'fecha': n.fecha_creacion.replace(tzinfo=timezone.utc).astimezone(GT_TZ).isoformat(),
        }
        for n in notifs
    ]


# Contador de notificaciones sin leer; el frontend lo usa para mostrar el badge en la campana
@router.get('/unread-count')
def unread_count(
    current_user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    count = (
        db.query(func.count(Notificacion.id))
        .filter_by(usuario_id=current_user.id, leida=False)
        .scalar() or 0
    )
    return {'count': count}


# Marca en bulk todas las notificaciones del usuario como leídas en una sola query UPDATE
@router.patch('/read-all', status_code=200)
def marcar_todas_leidas(
    current_user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    db.query(Notificacion).filter_by(usuario_id=current_user.id, leida=False).update({'leida': True})
    db.commit()
    return {'ok': True}


# Marca una notificación individual como leída; devuelve ok=False si no pertenece al usuario
@router.patch('/{notif_id}/read', status_code=200)
def marcar_leida(
    notif_id: int,
    current_user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    n = db.get(Notificacion, notif_id)
    if not n or n.usuario_id != current_user.id:
        return {'ok': False}
    n.leida = True
    db.commit()
    return {'ok': True}
