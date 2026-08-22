import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import Response
from pymongo.database import Database
from sqlalchemy.orm import Session

from app.core.db_mongo import get_mongo_db
from app.core.db_mysql import get_db
from app.core.deps import get_current_user
from app.models.direccion import Direccion
from app.models.usuario import Usuario
from app.models.pedido import Pedido
from app.models.producto import Producto as ProductoSQL
from app.models.vendedor import Vendedor
from app.models.notificacion import Notificacion
from app.schemas.checkout import CheckoutRequest, CheckoutResponse
from app.services.checkout_service import procesar_checkout, CheckoutError
from app.services.invoice_service import generar_factura_pdf
from app.services.email_service import enviar_factura_por_correo

logger = logging.getLogger(__name__)
router = APIRouter(prefix='/orders', tags=['Pedidos'])


def _background_invoice(pedido_id: int, usuario_email: str, usuario_nombre: str,
                         usuario_apellido: str, usuario_telefono, total: float,
                         pedido_snapshot: dict, direccion_snapshot: dict):
    """Genera y envía la factura en background. No debe lanzar excepciones."""
    try:
        from types import SimpleNamespace

        usuario_ns = SimpleNamespace(
            nombre=usuario_nombre, apellido=usuario_apellido,
            email=usuario_email, telefono=usuario_telefono,
        )
        direccion_ns = SimpleNamespace(**direccion_snapshot)

        class LineaNS:
            def __init__(self, d):
                self.__dict__.update(d)

        pedido_ns = SimpleNamespace(
            id=pedido_snapshot['id'],
            estado=pedido_snapshot['estado'],
            subtotal=pedido_snapshot['subtotal'],
            impuestos=pedido_snapshot['impuestos'],
            total=pedido_snapshot['total'],
            lineas=[LineaNS(l) for l in pedido_snapshot['lineas']],
            pagos=[SimpleNamespace(**p) for p in pedido_snapshot['pagos']],
        )

        pdf = generar_factura_pdf(pedido_ns, usuario_ns, direccion_ns)
        enviar_factura_por_correo(
            email_destino=usuario_email,
            nombre=usuario_nombre,
            pedido_id=pedido_id,
            total=total,
            pdf_bytes=pdf,
        )
    except Exception as exc:
        logger.error('Error al generar/enviar factura pedido #%d: %s', pedido_id, exc)


def _crear_notificaciones_vendedores(db: Session, pedido: Pedido, comprador: Usuario) -> None:
    """Creates one notification per vendor with products in this order."""
    try:
        vendedor_lineas: dict[int, list] = {}
        for linea in pedido.lineas:
            if not linea.producto_id:
                continue
            prod = db.get(ProductoSQL, linea.producto_id)
            if not prod or not prod.vendedor_id:
                continue
            v = db.get(Vendedor, prod.vendedor_id)
            if not v or v.usuario_id == comprador.id:
                continue
            vendedor_lineas.setdefault(v.usuario_id, []).append(linea)

        for uid, lineas in vendedor_lineas.items():
            prods_str = ', '.join(l.producto_nombre for l in lineas[:3])
            if len(lineas) > 3:
                prods_str += f' y {len(lineas) - 3} más'
            subtotal = sum(float(l.subtotal_linea) for l in lineas)
            db.add(Notificacion(
                usuario_id=uid,
                tipo='venta_realizada',
                titulo=f'¡Nueva venta! Pedido #{pedido.id}',
                mensaje=(
                    f'Productos vendidos: {prods_str}. '
                    f'Subtotal: Q{subtotal:.2f}. '
                    f'Comprador: {comprador.nombre} {comprador.apellido}.'
                ),
                pedido_id=pedido.id,
            ))

        if vendedor_lineas:
            db.commit()
    except Exception as exc:
        logger.error('Error al crear notificaciones de vendedores pedido #%d: %s', pedido.id, exc)


@router.post('/checkout', response_model=CheckoutResponse, status_code=201)
def checkout(
    payload: CheckoutRequest,
    background_tasks: BackgroundTasks,
    current_user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
    mongo_db: Database = Depends(get_mongo_db),
):
    try:
        pedido = procesar_checkout(
            db,
            mongo_db,
            usuario_id=current_user.id,
            direccion_id=payload.direccion_id,
            metodo_pago_id=payload.metodo_pago_id,
            items=payload.items,
        )
    except CheckoutError as e:
        raise HTTPException(status_code=422, detail={'detail': e.message, 'code': e.code})

    # Notify vendors (synchronous, exceptions are caught internally)
    _crear_notificaciones_vendedores(db, pedido, current_user)

    # Serializar antes de salir de la sesión SQLAlchemy
    direccion = db.get(Direccion, payload.direccion_id)
    pedido_snapshot = {
        'id': pedido.id,
        'estado': pedido.estado,
        'subtotal': pedido.subtotal,
        'impuestos': pedido.impuestos,
        'total': pedido.total,
        'lineas': [
            {
                'producto_nombre': l.producto_nombre,
                'precio_unitario': l.precio_unitario,
                'cantidad': l.cantidad,
                'subtotal_linea': l.subtotal_linea,
            }
            for l in pedido.lineas
        ],
        'pagos': [
            {'referencia_transaccion': p.referencia_transaccion}
            for p in pedido.pagos
        ],
    }
    direccion_snapshot = {
        'linea1': direccion.linea1,
        'linea2': direccion.linea2,
        'municipio': direccion.municipio,
        'departamento': direccion.departamento,
        'pais': direccion.pais,
    }

    background_tasks.add_task(
        _background_invoice,
        pedido_id=pedido.id,
        usuario_email=current_user.email,
        usuario_nombre=current_user.nombre,
        usuario_apellido=current_user.apellido,
        usuario_telefono=current_user.telefono,
        total=float(pedido.total),
        pedido_snapshot=pedido_snapshot,
        direccion_snapshot=direccion_snapshot,
    )

    return CheckoutResponse(
        pedido_id=pedido.id,
        total=pedido.total,
        estado=pedido.estado,
        mensaje='Pedido creado exitosamente.',
    )


@router.get('/')
def listar_pedidos(
    current_user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    pedidos = (
        db.query(Pedido)
        .filter_by(usuario_id=current_user.id)
        .order_by(Pedido.fecha_creacion.desc())
        .all()
    )
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


@router.get('/{pedido_id}/invoice')
def descargar_factura(
    pedido_id: int,
    current_user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    pedido = db.get(Pedido, pedido_id)
    if not pedido or pedido.usuario_id != current_user.id:
        raise HTTPException(status_code=404, detail='Pedido no encontrado.')

    direccion = db.get(Direccion, pedido.direccion_id)
    usuario = db.get(Usuario, pedido.usuario_id)

    pdf_bytes = generar_factura_pdf(pedido, usuario, direccion)
    return Response(
        content=pdf_bytes,
        media_type='application/pdf',
        headers={
            'Content-Disposition': f'attachment; filename="factura-TiendaYa-{pedido_id:06d}.pdf"'
        },
    )


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
