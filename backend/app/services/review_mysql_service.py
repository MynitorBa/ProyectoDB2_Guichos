"""Autoridad transaccional de reseñas, imágenes y respuestas en MySQL."""

from __future__ import annotations

import uuid
from collections import defaultdict

from sqlalchemy import exists, func
from sqlalchemy.orm import Session

from app.models.pago import Pago
from app.models.pedido import Pedido, PedidoLinea
from app.models.pedido_vendedor import PedidoVendedor
from app.models.producto_referencia import ProductoReferencia
from app.models.resena import Resena, ResenaImagen, ResenaRespuesta
from app.models.usuario import Usuario
from app.models.vendedor import Vendedor


ESTADOS_PEDIDO_INVALIDOS = ('cancelado', 'reembolsado')


def compra_elegible(
    db: Session, *, usuario_id: int, producto_ref: str, vendedor_id: int,
) -> PedidoLinea | None:
    """Última línea pagada válida del producto comprada al vendedor indicado."""
    pago_aprobado = exists().where(
        Pago.pedido_id == Pedido.id,
        Pago.estado == 'aprobado',
    )
    return (
        db.query(PedidoLinea)
        .join(Pedido, Pedido.id == PedidoLinea.pedido_id)
        .join(PedidoVendedor, PedidoVendedor.id == PedidoLinea.pedido_vendedor_id)
        .filter(
            Pedido.usuario_id == usuario_id,
            PedidoLinea.producto_ref == producto_ref,
            PedidoVendedor.vendedor_id == vendedor_id,
            Pedido.estado.notin_(ESTADOS_PEDIDO_INVALIDOS),
            pago_aprobado,
        )
        .order_by(Pedido.fecha_creacion.desc(), PedidoLinea.id.desc())
        .first()
    )


def buscar_resena(
    db: Session, *, usuario_id: int, producto_ref: str, vendedor_id: int,
) -> Resena | None:
    return (
        db.query(Resena)
        .join(ProductoReferencia, ProductoReferencia.id == Resena.producto_referencia_id)
        .filter(
            Resena.usuario_id == usuario_id,
            ProductoReferencia.producto_ref == producto_ref,
            Resena.vendedor_id == vendedor_id,
        )
        .first()
    )


def elegibilidad(db: Session, *, usuario_id: int, producto_ref: str, vendedor_id: int) -> dict:
    line = compra_elegible(
        db, usuario_id=usuario_id, producto_ref=producto_ref, vendedor_id=vendedor_id,
    )
    review = buscar_resena(
        db, usuario_id=usuario_id, producto_ref=producto_ref, vendedor_id=vendedor_id,
    )
    return {
        'puede': line is not None,
        'compro': line is not None,
        'ya_reseno': review is not None,
        'puede_editar': line is not None and review is not None,
        'resena': serializar(db, review) if review else None,
    }


def crear(
    db: Session, *, usuario_id: int, producto_ref: str, vendedor_id: int,
    calificacion: int, texto: str,
) -> Resena:
    line = compra_elegible(
        db, usuario_id=usuario_id, producto_ref=producto_ref, vendedor_id=vendedor_id,
    )
    if not line:
        raise PermissionError('No existe una compra pagada válida para ese producto y vendedor.')
    ref = db.query(ProductoReferencia).filter(
        ProductoReferencia.producto_ref == producto_ref
    ).first()
    if not ref:
        raise LookupError('Producto no encontrado.')
    if buscar_resena(db, usuario_id=usuario_id, producto_ref=producto_ref, vendedor_id=vendedor_id):
        raise FileExistsError('Ya existe una reseña para ese producto y vendedor.')
    review = Resena(
        public_id=str(uuid.uuid4()), usuario_id=usuario_id,
        producto_referencia_id=ref.id, vendedor_id=vendedor_id,
        pedido_linea_id=line.id, calificacion=calificacion, comentario=texto,
        estado_moderacion='aprobada', verificada_compra=True,
        motivo_no_verificada=None, version=1, aprobada=True,
    )
    db.add(review)
    db.flush()
    return review


def editar(
    db: Session, *, public_id: str, usuario_id: int,
    calificacion: int, texto: str,
) -> Resena:
    review = db.query(Resena).filter(
        Resena.public_id == public_id, Resena.usuario_id == usuario_id,
    ).first()
    if not review:
        raise LookupError('Reseña no encontrada.')
    ref = db.get(ProductoReferencia, review.producto_referencia_id)
    line = compra_elegible(
        db, usuario_id=usuario_id, producto_ref=ref.producto_ref,
        vendedor_id=review.vendedor_id,
    )
    if not line:
        raise PermissionError('La reseña ya no posee una compra pagada válida.')
    review.pedido_linea_id = line.id
    review.calificacion = calificacion
    review.comentario = texto
    review.verificada_compra = True
    review.motivo_no_verificada = None
    review.version += 1
    return review


def agregar_imagenes(
    db: Session, *, public_id: str, usuario_id: int, urls: list[str],
) -> list[str]:
    review = db.query(Resena).filter(
        Resena.public_id == public_id, Resena.usuario_id == usuario_id,
    ).first()
    if not review:
        raise LookupError('Reseña no encontrada.')
    existing = db.query(ResenaImagen).filter(ResenaImagen.resena_id == review.id).count()
    if existing + len(urls) > 4:
        raise ValueError('Máximo 4 imágenes por reseña.')
    for offset, url in enumerate(urls):
        db.add(ResenaImagen(resena_id=review.id, url=url, orden=existing + offset))
    review.version += 1
    return urls


def responder(
    db: Session, *, public_id: str, usuario_id: int, vendedor_id: int, texto: str,
) -> ResenaRespuesta:
    review = db.query(Resena).filter(Resena.public_id == public_id).first()
    if not review:
        raise LookupError('Reseña no encontrada.')
    if review.vendedor_id != vendedor_id:
        raise PermissionError('Solo el vendedor calificado puede responder.')
    reply = ResenaRespuesta(
        public_id=str(uuid.uuid4()), resena_id=review.id, usuario_id=usuario_id,
        vendedor_id=vendedor_id, texto=texto, activa=True,
    )
    db.add(reply)
    review.version += 1
    db.flush()
    return reply


def moderar(db: Session, *, public_id: str, estado: str) -> Resena | None:
    review = db.query(Resena).filter(Resena.public_id == public_id).first()
    if not review:
        return None
    review.estado_moderacion = estado
    review.aprobada = estado == 'aprobada'
    review.version += 1
    return review


def serializar(db: Session, review: Resena | None) -> dict | None:
    if not review:
        return None
    user = db.get(Usuario, review.usuario_id)
    seller = db.get(Vendedor, review.vendedor_id) if review.vendedor_id else None
    images = db.query(ResenaImagen).filter(
        ResenaImagen.resena_id == review.id
    ).order_by(ResenaImagen.orden, ResenaImagen.id).all()
    replies = db.query(ResenaRespuesta).filter(
        ResenaRespuesta.resena_id == review.id,
        ResenaRespuesta.activa.is_(True),
    ).order_by(ResenaRespuesta.fecha_creacion, ResenaRespuesta.id).all()
    reply_users = {r.usuario_id: db.get(Usuario, r.usuario_id) for r in replies}
    return {
        'id': review.public_id, 'calificacion': review.calificacion,
        'texto': review.comentario or '', 'fecha': review.fecha.isoformat(),
        'fecha_actualizacion': review.fecha_actualizacion.isoformat(),
        'verificada': bool(review.verificada_compra),
        'estado': review.estado_moderacion,
        'usuario_nombre': f'{user.nombre} {user.apellido}'.strip() if user else 'Usuario',
        'usuario_id': review.usuario_id,
        'imagenes': [img.url for img in images],
        'vendedor_nombre': seller.nombre_comercial if seller else None,
        'vendedor_id': review.vendedor_id,
        'respuestas': [{
            'id': reply.public_id, 'texto': reply.texto,
            'fecha': reply.fecha_creacion.isoformat(), 'es_vendedor': True,
            'autor_nombre': (
                f'{reply_users[reply.usuario_id].nombre} {reply_users[reply.usuario_id].apellido}'.strip()
                if reply_users.get(reply.usuario_id) else 'Vendedor'
            ),
        } for reply in replies],
    }


def listar(
    db: Session, *, producto_ref: str, solo_publicas: bool,
    usuario_id: int | None = None,
) -> list[dict]:
    query = db.query(Resena).join(
        ProductoReferencia, ProductoReferencia.id == Resena.producto_referencia_id
    ).filter(ProductoReferencia.producto_ref == producto_ref)
    if solo_publicas:
        if usuario_id is None:
            query = query.filter(
                Resena.estado_moderacion == 'aprobada', Resena.verificada_compra.is_(True)
            )
        else:
            query = query.filter(
                (Resena.usuario_id == usuario_id) |
                ((Resena.estado_moderacion == 'aprobada') & Resena.verificada_compra.is_(True))
            )
    return [serializar(db, row) for row in query.order_by(Resena.fecha.desc()).all()]


def resumen(db: Session, producto_ref: str) -> dict:
    rows = (
        db.query(Resena.calificacion, func.count(Resena.id))
        .join(ProductoReferencia, ProductoReferencia.id == Resena.producto_referencia_id)
        .filter(
            ProductoReferencia.producto_ref == producto_ref,
            Resena.estado_moderacion == 'aprobada',
            Resena.verificada_compra.is_(True),
        )
        .group_by(Resena.calificacion).all()
    )
    dist = {str(i): 0 for i in range(1, 6)}
    total = weighted = 0
    for rating, count in rows:
        dist[str(rating)] = count
        total += count
        weighted += rating * count
    return {
        'total': total, 'promedio': round(weighted / total, 2) if total else 0.0,
        'distribucion': dist,
    }


def ratings_por_producto(db: Session, refs: list[str]) -> dict[str, tuple[float, int]]:
    if not refs:
        return {}
    rows = (
        db.query(
            ProductoReferencia.producto_ref,
            func.avg(Resena.calificacion), func.count(Resena.id),
        )
        .join(Resena, Resena.producto_referencia_id == ProductoReferencia.id)
        .filter(
            ProductoReferencia.producto_ref.in_(refs),
            Resena.estado_moderacion == 'aprobada',
            Resena.verificada_compra.is_(True),
        )
        .group_by(ProductoReferencia.producto_ref).all()
    )
    return {ref: (round(float(avg), 2), int(total)) for ref, avg, total in rows}


def revalidar_por_pedido(db: Session, pedido_id: int) -> list[Resena]:
    """Reubica o invalida reseñas respaldadas por un pedido cancelado/reembolsado."""
    line_ids = [row[0] for row in db.query(PedidoLinea.id).filter(
        PedidoLinea.pedido_id == pedido_id
    ).all()]
    if not line_ids:
        return []
    changed = []
    for review in db.query(Resena).filter(Resena.pedido_linea_id.in_(line_ids)).all():
        ref = db.get(ProductoReferencia, review.producto_referencia_id)
        replacement = compra_elegible(
            db, usuario_id=review.usuario_id, producto_ref=ref.producto_ref,
            vendedor_id=review.vendedor_id,
        )
        if replacement and replacement.id not in line_ids:
            review.pedido_linea_id = replacement.id
            review.verificada_compra = True
            review.motivo_no_verificada = None
        else:
            review.pedido_linea_id = None
            review.verificada_compra = False
            review.motivo_no_verificada = 'compra_cancelada_o_reembolsada'
            review.estado_moderacion = 'pendiente'
            review.aprobada = False
        review.version += 1
        changed.append(review)
    return changed
