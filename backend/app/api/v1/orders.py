import logging
import re
import time
from datetime import timezone
from decimal import Decimal, InvalidOperation

import redis as redis_lib
from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException
from fastapi.responses import JSONResponse, Response
from pymongo.database import Database
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.db_mongo import get_mongo_db
from app.core.db_mysql import get_db
from app.core.db_redis import get_redis
from app.core.deps import get_current_user
from app.models.direccion import Direccion
from app.models.usuario import Usuario
from app.models.pedido import Pedido
from app.models.pedido_vendedor import PedidoVendedor
from app.models.vendedor import Vendedor
from app.models.notificacion import Notificacion
from app.schemas.checkout import CheckoutItem, CheckoutRequest, CheckoutResponse
from app.models.pago import Pago
from app.services.checkout_service import procesar_checkout, CheckoutError, huella_solicitud
from app.services.invoice_service import generar_factura_pdf
from app.services.email_service import enviar_factura_por_correo
from app.services import redis_cart_service as rcs
from app.services import flash_sale_service as flash

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


CLAVE_VALIDA = re.compile(r'^[A-Za-z0-9-]{8,36}$')

# Código de error de la saga → estado HTTP
ESTADOS_ERROR = {
    'PRICE_CHANGED': 409,
    'PAYMENT_DECLINED': 402,
    'PAYMENT_UNAVAILABLE': 503,
    'ORDER_NOT_FULFILLABLE': 409,
}


def _respuesta_pendiente(pedido: Pedido, mensaje: str, codigo: str = 'PAYMENT_PENDING') -> JSONResponse:
    # 202: la solicitud se aceptó, pero el resultado se conocerá después.
    return JSONResponse(status_code=202, content={
        'pedido_id': pedido.id,
        'total': str(pedido.total),
        'estado': pedido.estado,
        'mensaje': mensaje,
        'codigo': codigo,
        'requiere_seguimiento': True,
    })


def _respuesta_existente(db: Session, pedido: Pedido, huella: str | None, response: Response):
    """Respuesta a un reintento con una clave de idempotencia ya usada.

    ``huella`` es None cuando el carrito ya está vacío (el intento original lo
    vació al confirmar): es un reintento legítimo y no hay contenido que comparar.
    """
    if huella and pedido.huella_solicitud and pedido.huella_solicitud != huella:
        raise HTTPException(422, detail={
            'detail': 'Esta clave de idempotencia ya se usó para otra compra distinta.',
            'code': 'IDEMPOTENCY_KEY_MISMATCH',
        })
    if pedido.estado == 'pendiente':
        pago = db.query(Pago).filter_by(pedido_id=pedido.id).first()
        if pago and pago.estado == 'en_verificacion':
            return _respuesta_pendiente(pedido, 'Estamos verificando tu pago con la pasarela.')
        raise HTTPException(409, detail={
            'detail': 'Esta compra todavía se está procesando.',
            'code': 'CHECKOUT_IN_PROGRESS', 'pedido_id': pedido.id,
        })
    if pedido.estado == 'cancelado':
        raise HTTPException(409, detail={
            'detail': 'Esta compra ya se intentó y fue cancelada. Inicia una nueva compra.',
            'code': 'ORDER_CANCELLED', 'pedido_id': pedido.id,
            'motivo': pedido.motivo_cancelacion,
        })
    response.status_code = 200
    response.headers['Idempotent-Replayed'] = 'true'
    return CheckoutResponse(
        pedido_id=pedido.id, total=pedido.total, estado=pedido.estado,
        mensaje='Este pedido ya había sido creado con esta solicitud.',
        codigo='IDEMPOTENT_REPLAY',
    )


# Ejecuta el checkout como saga (reserva → cobro externo → confirmación o compensación).
# La clave Idempotency-Key hace seguro reintentar: la misma solicitud nunca crea dos pedidos.
@router.post('/checkout', response_model=CheckoutResponse, status_code=201, responses={
    202: {'description': 'Pago en verificación: el resultado se conocerá después.'},
    402: {'description': 'Pago rechazado; el pedido se compensó y el carrito se conserva.'},
})
def checkout(
    payload: CheckoutRequest,
    background_tasks: BackgroundTasks,
    response: Response,
    idempotency_key: str | None = Header(
        None, alias='Idempotency-Key',
        description='UUID generado por el cliente para cada intento de compra; reutilizarlo al reintentar.',
    ),
    current_user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
    mongo_db: Database = Depends(get_mongo_db),
    r: redis_lib.Redis = Depends(get_redis),
):
    if idempotency_key is not None and not CLAVE_VALIDA.match(idempotency_key):
        raise HTTPException(422, detail={
            'detail': 'Idempotency-Key debe tener entre 8 y 36 caracteres alfanuméricos o guiones.',
            'code': 'INVALID_IDEMPOTENCY_KEY',
        })

    # La selección comprable se obtiene del carrito del usuario autenticado.
    # Nunca se confía en una lista de ofertas enviada por el navegador.
    try:
        redis_items = rcs.obtener_carrito(r, current_user.id)
    except redis_lib.RedisError as exc:
        logger.error('Redis no disponible antes del checkout: %s', exc)
        raise HTTPException(
            status_code=503,
            detail={'detail': 'El carrito no está disponible temporalmente.', 'code': 'CART_UNAVAILABLE'},
        ) from exc

    try:
        checkout_items = [
            CheckoutItem(oferta_id=item['oferta_id'], cantidad=int(item['cantidad']))
            for item in redis_items
        ]
        precios_carrito = {
            item['oferta_id']: Decimal(str(item['precio_al_agregar']))
            for item in redis_items
        }
    except (KeyError, TypeError, ValueError, InvalidOperation) as exc:
        logger.error('Carrito Redis inválido para usuario %d: %s', current_user.id, exc)
        raise HTTPException(
            status_code=409,
            detail={'detail': 'El carrito contiene datos inválidos. Vacíalo e intenta nuevamente.', 'code': 'INVALID_CART'},
        ) from exc

    flash_context = {}
    for item in redis_items:
        promotion_id = item.get('promocion_flash_id')
        token = item.get('reserva_flash_token')
        if promotion_id is None and token is None:
            continue
        if not promotion_id or not token:
            raise HTTPException(
                status_code=409,
                detail={'detail': 'La reserva flash del carrito es inválida.', 'code': 'FLASH_RESERVATION_INVALID'},
            )
        reservation = flash.obtener_reserva(r, int(promotion_id), current_user.id)
        if (
            not reservation
            or reservation.get('token') != token
            or int(reservation.get('cantidad', 0)) != int(item['cantidad'])
            or int(reservation.get('expira_ts', 0)) <= int(time.time())
        ):
            raise HTTPException(
                status_code=409,
                detail={'detail': 'La reserva flash venció. Retira el artículo y reserva nuevamente.', 'code': 'FLASH_RESERVATION_INVALID'},
            )
        flash_context[item['oferta_id']] = {
            'promocion_id': int(promotion_id),
            'token': token,
        }

    huella = huella_solicitud(checkout_items, payload.direccion_id, payload.metodo_pago_id)
    if idempotency_key:
        existente = db.query(Pedido).filter_by(clave_idempotencia=idempotency_key).first()
        if existente:
            if existente.usuario_id != current_user.id:
                raise HTTPException(422, detail={'detail': 'Clave de idempotencia inválida.', 'code': 'IDEMPOTENCY_KEY_MISMATCH'})
            return _respuesta_existente(db, existente, huella if checkout_items else None, response)

    # Mientras un pago está en verificación no se acepta otra compra del mismo
    # usuario: si después se confirmara, el cliente pagaría dos veces lo mismo.
    en_verificacion = (
        db.query(Pedido.id)
        .join(Pago, Pago.pedido_id == Pedido.id)
        .filter(Pedido.usuario_id == current_user.id, Pedido.estado == 'pendiente',
                Pago.estado == 'en_verificacion')
        .first()
    )
    if en_verificacion:
        raise HTTPException(409, detail={
            'detail': 'Tienes un pago en verificación. Espera a que se resuelva antes de comprar de nuevo.',
            'code': 'PAYMENT_PENDING_EXISTS', 'pedido_id': en_verificacion.id,
        })

    try:
        pedido = procesar_checkout(
            db,
            mongo_db,
            usuario_id=current_user.id,
            direccion_id=payload.direccion_id,
            metodo_pago_id=payload.metodo_pago_id,
            items=checkout_items,
            precios_esperados=precios_carrito,
            confirmar_cambios_precio=payload.confirmar_cambios_precio,
            precios_confirmados=payload.precios_confirmados,
            promociones_flash=flash_context,
            clave_idempotencia=idempotency_key,
            huella=huella,
        )
    except IntegrityError:
        # Dos solicitudes simultáneas con la misma clave: solo una crea el pedido.
        db.rollback()
        existente = db.query(Pedido).filter_by(clave_idempotencia=idempotency_key).first()
        if not existente:
            raise
        return _respuesta_existente(db, existente, huella, response)
    except CheckoutError as e:
        db.rollback()
        if e.code == 'PAYMENT_PENDING':
            return _respuesta_pendiente(db.get(Pedido, e.pedido_id), e.message)
        detalle = {'detail': e.message, 'code': e.code}
        if e.pedido_id:
            detalle['pedido_id'] = e.pedido_id
        if e.code in ('PAYMENT_DECLINED', 'PAYMENT_UNAVAILABLE', 'ORDER_NOT_FULFILLABLE'):
            detalle['carrito_conservado'] = True
        raise HTTPException(status_code=ESTADOS_ERROR.get(e.code, 422), detail=detalle)

    # MySQL ya confirmó el pedido. Consumir la reserva no devuelve la unidad al
    # cupo flash; la venta durable ya quedó registrada en MySQL.
    for offer_id, context in flash_context.items():
        try:
            consumed = flash.consumir(
                r, context['promocion_id'], current_user.id, context['token']
            )
            if not consumed:
                logger.error(
                    'Pedido #%d confirmado, reserva flash %s no estaba en Redis.',
                    pedido.id, context['token'],
                )
        except redis_lib.RedisError as exc:
            logger.error('Pedido #%d confirmado; falló cierre de reserva flash: %s', pedido.id, exc)

    # MySQL ya confirmó el pedido. Una falla al limpiar Redis se registra, pero
    # nunca convierte una compra exitosa en un 500 engañoso para el usuario.
    try:
        rcs.vaciar_carrito(r, current_user.id)
    except redis_lib.RedisError as exc:
        logger.error(
            'Pedido #%d confirmado, pero no se pudo limpiar carrito Redis del usuario %d: %s',
            pedido.id, current_user.id, exc,
        )

    # Se serializa el pedido en dicts planos antes de que la sesión SQLAlchemy se cierre para la tarea en background
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


# Lista todos los pedidos del usuario autenticado ordenados del más reciente al más antiguo
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
            'fecha': p.fecha_creacion.replace(tzinfo=timezone.utc).isoformat(),
            'num_lineas': len(p.lineas),
        }
        for p in pedidos
    ]


# Genera y descarga la factura PDF de un pedido en tiempo real (solo el dueño puede descargarla)
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


# Devuelve el detalle completo de un pedido: líneas, pagos y montos desglosados
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
        'fecha': pedido.fecha_creacion.replace(tzinfo=timezone.utc).isoformat(),
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
                'fecha': p.fecha.replace(tzinfo=timezone.utc).isoformat(),
            }
            for p in pedido.pagos
        ],
    }
