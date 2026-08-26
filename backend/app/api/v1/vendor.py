from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.db_mysql import get_db
from app.core.deps import require_role
from app.models.pedido import Pedido, PedidoLinea
from app.models.pedido_vendedor import PedidoVendedor
from app.models.usuario import Usuario
from app.models.vendedor import Vendedor

GT_TZ = timezone(timedelta(hours=-6))
router = APIRouter(prefix='/vendor', tags=['Vendedor'])

get_vendor_user = require_role('vendedor', 'administrador')

# pendiente lo asigna el sistema; cancelado y reembolsado son exclusivos del admin
_ESTADOS_ADMIN_ONLY = {'pendiente', 'cancelado', 'reembolsado'}

def _estados_vendedor() -> list[str]:
    """Devuelve los estados válidos del subpedido que controla el vendedor."""
    all_estados: list[str] = list(
        PedidoVendedor.__table__.c['estado'].type.enums
    )
    return [e for e in all_estados if e not in _ESTADOS_ADMIN_ONLY]


class StatusUpdate(BaseModel):
    estado: str


@router.get('/estados')
def vendor_estados():
    return _estados_vendedor()


def _get_vendedor(db: Session, user: Usuario) -> Vendedor:
    v = db.query(Vendedor).filter_by(usuario_id=user.id).first()
    if not v:
        raise HTTPException(403, 'No tienes perfil de vendedor configurado. Pide al admin que configure tu perfil.')
    return v


@router.get('/stats')
def vendor_stats(
    current_user: Usuario = Depends(get_vendor_user),
    db: Session = Depends(get_db),
):
    v = _get_vendedor(db, current_user)

    total_pedidos = (
        db.query(func.count(PedidoVendedor.id))
        .filter(PedidoVendedor.vendedor_id == v.id)
        .scalar() or 0
    )

    ingresos = (
        db.query(func.sum(PedidoVendedor.subtotal))
        .join(Pedido, Pedido.id == PedidoVendedor.pedido_id)
        .filter(
            PedidoVendedor.vendedor_id == v.id,
            Pedido.estado.notin_(['cancelado', 'reembolsado']),
            PedidoVendedor.estado.notin_(['cancelado', 'reembolsado']),
        )
        .scalar() or 0
    )

    pendientes = (
        db.query(func.count(PedidoVendedor.id))
        .filter(
            PedidoVendedor.vendedor_id == v.id,
            PedidoVendedor.estado == 'confirmado',
        )
        .scalar() or 0
    )

    return {
        'nombre_comercial': v.nombre_comercial,
        'total_pedidos': total_pedidos,
        'ingresos_totales': float(ingresos),
        'pendientes': pendientes,
    }


@router.get('/orders')
def vendor_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: Usuario = Depends(get_vendor_user),
    db: Session = Depends(get_db),
):
    v = _get_vendedor(db, current_user)

    total = db.query(func.count(PedidoVendedor.id)).filter(
        PedidoVendedor.vendedor_id == v.id
    ).scalar() or 0

    rows = (
        db.query(PedidoVendedor, Pedido)
        .join(Pedido, Pedido.id == PedidoVendedor.pedido_id)
        .filter(PedidoVendedor.vendedor_id == v.id)
        .order_by(Pedido.fecha_creacion.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    items = []
    for part, p in rows:
        u = p.usuario
        mis_lineas = (
            db.query(PedidoLinea)
            .filter(PedidoLinea.pedido_vendedor_id == part.id)
            .all()
        )
        items.append({
            'id': p.id,
            'pedido_vendedor_id': part.id,
            'fecha': p.fecha_creacion.replace(tzinfo=timezone.utc).astimezone(GT_TZ).isoformat(),
            'estado': part.estado,
            'estado_pedido': p.estado,
            'total': float(part.subtotal + part.costo_envio),
            'comprador': {
                'nombre': f'{u.nombre} {u.apellido}' if u else '—',
                'email': u.email if u else '—',
            },
            'mis_lineas': [
                {
                    'producto_nombre': l.producto_nombre,
                    'precio_unitario': float(l.precio_unitario),
                    'cantidad': l.cantidad,
                    'subtotal_linea': float(l.subtotal_linea),
                }
                for l in mis_lineas
            ],
            'subtotal_mis_productos': float(sum(l.subtotal_linea for l in mis_lineas)),
        })

    return {
        'items': items,
        'total': total,
        'page': page,
        'page_size': page_size,
        'total_pages': max(1, -(-total // page_size)),
    }


@router.patch('/orders/{pedido_id}/status')
def update_vendor_order_status(
    pedido_id: int,
    payload: StatusUpdate,
    current_user: Usuario = Depends(get_vendor_user),
    db: Session = Depends(get_db),
):
    estados_validos = _estados_vendedor()
    if payload.estado not in estados_validos:
        raise HTTPException(400, f'Solo puedes establecer: {", ".join(sorted(estados_validos))}.')

    v = _get_vendedor(db, current_user)

    part = (
        db.query(PedidoVendedor)
        .filter(
            PedidoVendedor.pedido_id == pedido_id,
            PedidoVendedor.vendedor_id == v.id,
        )
        .first()
    )
    if not part:
        raise HTTPException(403, 'No tienes permiso para modificar este pedido.')

    pedido = db.get(Pedido, pedido_id)
    if not pedido:
        raise HTTPException(404, 'Pedido no encontrado.')

    part.estado = payload.estado
    db.commit()
    return {
        'id': pedido_id,
        'pedido_vendedor_id': part.id,
        'estado': payload.estado,
    }
