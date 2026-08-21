from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.db_mysql import get_db
from app.core.deps import get_current_user
from app.models.usuario import Usuario
from app.models.pedido import Pedido
from app.schemas.checkout import CheckoutRequest, CheckoutResponse
from app.services.checkout_service import procesar_checkout, CheckoutError

router = APIRouter(prefix='/orders', tags=['Pedidos'])


@router.post('/checkout', response_model=CheckoutResponse, status_code=201)
def checkout(
    payload: CheckoutRequest,
    current_user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        pedido = procesar_checkout(
            db,
            usuario_id=current_user.id,
            direccion_id=payload.direccion_id,
            metodo_pago_id=payload.metodo_pago_id,
            items=payload.items,
        )
        return CheckoutResponse(
            pedido_id=pedido.id,
            total=pedido.total,
            estado=pedido.estado,
            mensaje='Pedido creado exitosamente.',
        )
    except CheckoutError as e:
        raise HTTPException(status_code=422, detail={'detail': e.message, 'code': e.code})


@router.get('/')
def listar_pedidos(
    current_user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    pedidos = db.query(Pedido).filter_by(usuario_id=current_user.id).order_by(Pedido.fecha_creacion.desc()).all()
    return [
        {
            'id': p.id,
            'estado': p.estado,
            'total': float(p.total),
            'fecha': p.fecha_creacion.isoformat(),
            'num_lineas': len(p.lineas),
        }
        for p in pedidos
    ]


@router.get('/{pedido_id}')
def detalle_pedido(
    pedido_id: int,
    current_user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    pedido = db.get(Pedido, pedido_id)
    if not pedido or pedido.usuario_id != current_user.id:
        raise HTTPException(status_code=404, detail='Pedido no encontrado.')

    return {
        'id': pedido.id,
        'estado': pedido.estado,
        'subtotal': float(pedido.subtotal),
        'impuestos': float(pedido.impuestos),
        'total': float(pedido.total),
        'fecha': pedido.fecha_creacion.isoformat(),
        'lineas': [
            {
                'producto_nombre': l.producto_nombre,
                'precio_unitario': float(l.precio_unitario),
                'cantidad': l.cantidad,
                'subtotal': float(l.subtotal_linea),
                'producto_ref': l.producto_ref,
            }
            for l in pedido.lineas
        ],
        'pagos': [
            {
                'monto': float(p.monto),
                'estado': p.estado,
                'referencia': p.referencia_transaccion,
                'fecha': p.fecha.isoformat(),
            }
            for p in pedido.pagos
        ],
    }
