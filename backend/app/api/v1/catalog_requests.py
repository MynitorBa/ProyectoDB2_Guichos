from decimal import Decimal

from bson import ObjectId
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from pymongo.database import Database
from sqlalchemy.orm import Session

from app.core.db_mongo import get_mongo_db
from app.core.db_mysql import get_db
from app.core.deps import get_admin_user, require_role
from app.core.time import utc_now
from app.models.categoria import Categoria
from app.models.inventario import Inventario
from app.models.notificacion import Notificacion
from app.models.oferta import Oferta, OfertaPrecioHistorial
from app.models.producto_imagen import ProductoImagen
from app.models.producto_referencia import ProductoReferencia
from app.models.producto_referencia_categoria import ProductoReferenciaCategoria
from app.models.solicitud_catalogo import (
    SolicitudCatalogo,
    SolicitudCatalogoCategoria,
    SolicitudCatalogoImagen,
)
from app.models.usuario import Rol, Usuario, UsuarioRol
from app.models.vendedor import Vendedor
from app.services import catalog_service
from app.services.image_service import read_valid_image
from app.services.category_attribute_service import (
    AttributeValidationError,
    validate_category_attributes,
)
from app.services.offer_service import (
    actualizar_precio_oferta,
    enqueue_primary_offer_projection,
)
from app.services.sku_service import generate_offer_sku, generate_product_sku


vendor_router = APIRouter(prefix='/vendor/catalog-requests', tags=['Solicitudes vendedor'])
admin_router = APIRouter(prefix='/admin/catalog-requests', tags=['Solicitudes admin'])
get_vendor_user = require_role('vendedor')


class ProductProposalCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    nombre: str = Field(min_length=2, max_length=200)
    descripcion: str | None = Field(default=None, max_length=5000)
    categoria_slugs: list[str] = Field(min_length=1, max_length=10)
    atributos: dict = Field(default_factory=dict)
    imagen_ids: list[int] = Field(default_factory=list, max_length=8)
    precio: Decimal = Field(gt=0)
    stock: int = Field(ge=0)
    observaciones: str | None = Field(default=None, max_length=2000)


class OfferProposalCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    producto_ref: str = Field(min_length=24, max_length=24)
    precio: Decimal = Field(gt=0)
    stock: int = Field(ge=0)
    observaciones: str | None = Field(default=None, max_length=2000)


class ReviewPayload(BaseModel):
    model_config = ConfigDict(extra='forbid')
    observaciones: str | None = Field(default=None, max_length=2000)


def _get_vendor(db: Session, user: Usuario) -> Vendedor:
    vendor = db.query(Vendedor).filter_by(usuario_id=user.id).first()
    if not vendor:
        raise HTTPException(403, 'No tienes un perfil de vendedor configurado.')
    if vendor.estado_verificacion != 'verificado':
        raise HTTPException(403, 'Tu perfil de vendedor debe estar verificado.')
    return vendor


def _notify_admins(db: Session, request_id: int, vendor: Vendedor) -> None:
    admin_role = db.query(Rol).filter_by(nombre='administrador').first()
    if not admin_role:
        return
    user_ids = [row.usuario_id for row in db.query(UsuarioRol).filter_by(
        rol_id=admin_role.id
    ).all()]
    for user_id in user_ids:
        db.add(Notificacion(
            usuario_id=user_id,
            tipo='solicitud_catalogo',
            titulo='Nueva solicitud de catálogo',
            mensaje=(
                f'{vendor.nombre_comercial} envió la solicitud #{request_id} '
                'para revisión.'
            ),
        ))


def _notify_vendor(
    db: Session, request: SolicitudCatalogo, vendor: Vendedor
) -> None:
    approved = request.estado == 'aprobada'
    db.add(Notificacion(
        usuario_id=vendor.usuario_id,
        tipo='solicitud_catalogo',
        titulo=f'Solicitud #{request.id} {"aprobada" if approved else "rechazada"}',
        mensaje=request.observaciones_admin or (
            'La solicitud fue publicada correctamente.' if approved
            else 'La solicitud no fue aprobada por el administrador.'
        ),
    ))


def _category_rows(db: Session, request_id: int):
    return (
        db.query(SolicitudCatalogoCategoria, Categoria)
        .join(Categoria, Categoria.id == SolicitudCatalogoCategoria.categoria_id)
        .filter(SolicitudCatalogoCategoria.solicitud_id == request_id)
        .order_by(SolicitudCatalogoCategoria.orden)
        .all()
    )


def _image_rows(db: Session, request_id: int):
    return (
        db.query(SolicitudCatalogoImagen, ProductoImagen)
        .join(ProductoImagen, ProductoImagen.id == SolicitudCatalogoImagen.producto_imagen_id)
        .filter(SolicitudCatalogoImagen.solicitud_id == request_id)
        .order_by(SolicitudCatalogoImagen.orden)
        .all()
    )


def _serialize_request(
    db: Session, request: SolicitudCatalogo, mongo: Database
) -> dict:
    vendor = db.get(Vendedor, request.vendedor_id)
    categories = [
        {'id': category.id, 'slug': category.slug, 'nombre': category.nombre}
        for _, category in _category_rows(db, request.id)
    ]
    images = [
        {'id': image.id, 'url': f'/api/v1/products/images/{image.id}', 'orden': link.orden}
        for link, image in _image_rows(db, request.id)
    ]
    requested_name = request.nombre
    if request.producto_ref_solicitado:
        try:
            doc = mongo.productos.find_one(
                {'_id': ObjectId(request.producto_ref_solicitado)}, {'nombre': 1, 'sku': 1}
            )
        except Exception:
            doc = None
        requested_name = (doc or {}).get('nombre', 'Producto no disponible')
    return {
        'id': request.id,
        'tipo': request.tipo,
        'estado': request.estado,
        'vendedor_id': request.vendedor_id,
        'vendedor_nombre': vendor.nombre_comercial if vendor else None,
        'producto_ref_solicitado': request.producto_ref_solicitado,
        'producto_nombre': requested_name,
        'nombre': request.nombre,
        'descripcion': request.descripcion,
        'categorias': categories,
        'atributos': request.atributos or {},
        'imagenes': images,
        'sku_propuesto': request.sku_propuesto,
        'precio_propuesto': float(request.precio_propuesto),
        'stock_propuesto': request.stock_propuesto,
        'observaciones_vendedor': request.observaciones_vendedor,
        'observaciones_admin': request.observaciones_admin,
        'producto_ref_resultado': request.producto_ref_resultado,
        'oferta_id_resultado': request.oferta_id_resultado,
        'fecha_creacion': request.fecha_creacion.isoformat(),
        'fecha_revision': request.fecha_revision.isoformat() if request.fecha_revision else None,
    }


@vendor_router.post('/images', status_code=201)
async def upload_request_image(
    file: UploadFile = File(...),
    current_user: Usuario = Depends(get_vendor_user),
    db: Session = Depends(get_db),
):
    _get_vendor(db, current_user)
    content, mime = await read_valid_image(file)
    image = ProductoImagen(datos=content, mime_type=mime, subida_por=current_user.id)
    db.add(image)
    db.commit()
    db.refresh(image)
    return {'id': image.id, 'url': f'/api/v1/products/images/{image.id}'}


@vendor_router.delete('/images/{image_id}', status_code=204)
def delete_pending_image(
    image_id: int,
    current_user: Usuario = Depends(get_vendor_user),
    db: Session = Depends(get_db),
):
    image = db.get(ProductoImagen, image_id)
    linked = db.query(SolicitudCatalogoImagen).filter_by(
        producto_imagen_id=image_id
    ).first()
    if (
        not image or image.subida_por != current_user.id
        or image.producto_referencia_id is not None or linked
    ):
        raise HTTPException(409, 'La imagen no puede eliminarse.')
    db.delete(image)
    db.commit()


@vendor_router.post('/products', status_code=201)
def propose_product(
    payload: ProductProposalCreate,
    current_user: Usuario = Depends(get_vendor_user),
    db: Session = Depends(get_db),
    mongo: Database = Depends(get_mongo_db),
):
    vendor = _get_vendor(db, current_user)
    slugs = list(dict.fromkeys(payload.categoria_slugs))
    categories = db.query(Categoria).filter(
        Categoria.slug.in_(slugs), Categoria.activa.is_(True)
    ).all()
    by_slug = {category.slug: category for category in categories}
    missing = [slug for slug in slugs if slug not in by_slug]
    if missing:
        raise HTTPException(400, f'Categorías inválidas: {", ".join(missing)}')
    images = db.query(ProductoImagen).filter(
        ProductoImagen.id.in_(payload.imagen_ids)
    ).all() if payload.imagen_ids else []
    if len(images) != len(set(payload.imagen_ids)) or any(
        image.subida_por != current_user.id
        or image.producto_referencia_id is not None
        for image in images
    ):
        raise HTTPException(400, 'Una o más imágenes no pertenecen a esta solicitud.')
    already_linked = db.query(SolicitudCatalogoImagen).filter(
        SolicitudCatalogoImagen.producto_imagen_id.in_(payload.imagen_ids)
    ).count() if payload.imagen_ids else 0
    if already_linked:
        raise HTTPException(409, 'Una imagen ya pertenece a otra solicitud.')
    try:
        attributes = validate_category_attributes(
            mongo, slugs, payload.atributos
        )
    except AttributeValidationError as exc:
        raise HTTPException(422, str(exc)) from exc

    request = SolicitudCatalogo(
        vendedor_id=vendor.id, tipo='producto_nuevo', estado='pendiente',
        nombre=payload.nombre, descripcion=payload.descripcion,
        atributos=attributes,
        precio_propuesto=payload.precio, stock_propuesto=payload.stock,
        observaciones_vendedor=payload.observaciones,
    )
    db.add(request)
    db.flush()
    for order, slug in enumerate(slugs):
        db.add(SolicitudCatalogoCategoria(
            solicitud_id=request.id, categoria_id=by_slug[slug].id, orden=order
        ))
    for order, image_id in enumerate(payload.imagen_ids):
        db.add(SolicitudCatalogoImagen(
            solicitud_id=request.id, producto_imagen_id=image_id, orden=order
        ))
    _notify_admins(db, request.id, vendor)
    db.commit()
    db.refresh(request)
    return _serialize_request(db, request, mongo)


@vendor_router.post('/offers', status_code=201)
def propose_offer(
    payload: OfferProposalCreate,
    current_user: Usuario = Depends(get_vendor_user),
    db: Session = Depends(get_db),
    mongo: Database = Depends(get_mongo_db),
):
    vendor = _get_vendor(db, current_user)
    try:
        doc = mongo.productos.find_one({'_id': ObjectId(payload.producto_ref)}, {'nombre': 1})
    except Exception:
        doc = None
    reference = db.query(ProductoReferencia).filter_by(
        producto_ref=payload.producto_ref
    ).first()
    if not doc or not reference:
        raise HTTPException(404, 'El producto solicitado no existe.')
    existing_offer = db.query(Oferta).filter(
        Oferta.producto_ref == payload.producto_ref,
        Oferta.vendedor_id == vendor.id,
        Oferta.estado != 'descontinuada',
    ).first()
    if existing_offer:
        raise HTTPException(409, 'Ya tienes una oferta vigente para este producto.')
    pending = db.query(SolicitudCatalogo).filter_by(
        vendedor_id=vendor.id, tipo='oferta_existente', estado='pendiente',
        producto_ref_solicitado=payload.producto_ref,
    ).first()
    if pending:
        raise HTTPException(409, 'Ya existe una solicitud pendiente para este producto.')
    request = SolicitudCatalogo(
        vendedor_id=vendor.id, tipo='oferta_existente', estado='pendiente',
        producto_ref_solicitado=payload.producto_ref,
        precio_propuesto=payload.precio,
        stock_propuesto=payload.stock,
        observaciones_vendedor=payload.observaciones,
    )
    db.add(request)
    db.flush()
    _notify_admins(db, request.id, vendor)
    db.commit()
    db.refresh(request)
    return _serialize_request(db, request, mongo)


@vendor_router.get('/')
def list_own_requests(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: Usuario = Depends(get_vendor_user),
    db: Session = Depends(get_db),
    mongo: Database = Depends(get_mongo_db),
):
    vendor = _get_vendor(db, current_user)
    query = db.query(SolicitudCatalogo).filter_by(vendedor_id=vendor.id)
    total = query.count()
    rows = query.order_by(SolicitudCatalogo.fecha_creacion.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size).all()
    return {
        'items': [_serialize_request(db, row, mongo) for row in rows],
        'total': total, 'page': page, 'page_size': page_size,
        'total_pages': max(1, -(-total // page_size)),
    }


@vendor_router.patch('/{request_id}/cancel')
def cancel_request(
    request_id: int,
    current_user: Usuario = Depends(get_vendor_user),
    db: Session = Depends(get_db),
):
    vendor = _get_vendor(db, current_user)
    request = db.query(SolicitudCatalogo).filter_by(
        id=request_id, vendedor_id=vendor.id
    ).first()
    if not request:
        raise HTTPException(404, 'Solicitud no encontrada.')
    if request.estado != 'pendiente':
        raise HTTPException(409, 'Solo se pueden cancelar solicitudes pendientes.')
    request.estado = 'cancelada'
    db.commit()
    return {'id': request.id, 'estado': request.estado}


@admin_router.get('/')
def list_admin_requests(
    estado: str | None = Query(None),
    tipo: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    _: Usuario = Depends(get_admin_user),
    db: Session = Depends(get_db),
    mongo: Database = Depends(get_mongo_db),
):
    query = db.query(SolicitudCatalogo)
    if estado:
        query = query.filter(SolicitudCatalogo.estado == estado)
    if tipo:
        query = query.filter(SolicitudCatalogo.tipo == tipo)
    total = query.count()
    rows = query.order_by(
        (SolicitudCatalogo.estado == 'pendiente').desc(),
        SolicitudCatalogo.fecha_creacion.desc(),
    ).offset((page - 1) * page_size).limit(page_size).all()
    return {
        'items': [_serialize_request(db, row, mongo) for row in rows],
        'total': total, 'page': page, 'page_size': page_size,
        'total_pages': max(1, -(-total // page_size)),
    }


def _approve_new_product(
    db: Session, mongo: Database, request: SolicitudCatalogo,
    vendor: Vendedor, admin: Usuario,
) -> tuple[str, int]:
    category_rows = _category_rows(db, request.id)
    if not category_rows:
        raise HTTPException(409, 'La propuesta no tiene categorías válidas.')
    image_rows = _image_rows(db, request.id)
    primary = category_rows[0][1]
    try:
        sku = generate_product_sku(
            mongo, primary.sku_prefix or primary.slug[:3]
        )
        attributes = validate_category_attributes(
            mongo,
            [category.slug for _, category in category_rows],
            request.atributos,
        )
    except (ValueError, AttributeValidationError) as exc:
        raise HTTPException(409, str(exc)) from exc
    categories = [
        {'slug': category.slug, 'nombre': category.nombre}
        for _, category in category_rows
    ]
    image_urls = [
        f'/api/v1/products/images/{image.id}' for _, image in image_rows
    ]
    doc = {
        'sku': sku, 'nombre': request.nombre,
        'descripcion': request.descripcion, 'categoria': categories[0],
        'categorias': categories, 'atributos': attributes,
        'imagenes': image_urls, 'estado': 'activo', 'moneda': 'GTQ',
        'precio': float(request.precio_propuesto),
        'stock': request.stock_propuesto,
        'disponible': request.stock_propuesto > 0,
        'vendedor_id': vendor.id, 'vendedor_usuario_id': vendor.usuario_id,
        'vendedor_nombre': vendor.nombre_comercial,
        'resumen_resenas': {'promedio': 0.0, 'total': 0},
    }
    product = catalog_service.crear_producto(
        mongo, doc, usuario_id=str(admin.id)
    )
    try:
        reference = ProductoReferencia(
            producto_ref=product['_id'], categoria_id=primary.id
        )
        db.add(reference)
        db.flush()
        for order, (_, category) in enumerate(category_rows):
            db.add(ProductoReferenciaCategoria(
                producto_referencia_id=reference.id,
                categoria_id=category.id,
                es_principal=(order == 0),
            ))
        for order, (_, image) in enumerate(image_rows):
            image.producto_referencia_id = reference.id
            image.orden = order
        offer = Oferta(
            producto_ref=product['_id'], vendedor_id=vendor.id, sku=sku,
            precio_actual=request.precio_propuesto, moneda='GTQ',
            estado='activa', version=1,
        )
        db.add(offer)
        db.flush()
        db.add(OfertaPrecioHistorial(
            oferta_id=offer.id, precio=request.precio_propuesto, moneda='GTQ',
            vigente_desde=utc_now(), cambiado_por=admin.id,
            motivo=f'Aprobación de solicitud #{request.id}',
        ))
        db.add(Inventario(
            oferta_id=offer.id, cantidad_disponible=request.stock_propuesto,
            bodega='principal',
        ))
        db.flush()
        enqueue_primary_offer_projection(db, product['_id'], offer.id)
        return product['_id'], offer.id
    except Exception:
        mongo.productos.delete_one({'_id': ObjectId(product['_id'])})
        mongo.producto_eventos.delete_many({'producto_id': product['_id']})
        raise


def _approve_offer(
    db: Session, request: SolicitudCatalogo,
    vendor: Vendedor, admin: Usuario, mongo: Database,
) -> tuple[str, int]:
    product_ref = request.producto_ref_solicitado
    try:
        doc = mongo.productos.find_one({'_id': ObjectId(product_ref)}, {'sku': 1})
    except Exception:
        doc = None
    if not doc or not db.query(ProductoReferencia).filter_by(
        producto_ref=product_ref
    ).first():
        raise HTTPException(409, 'El producto dejó de estar disponible.')
    offer = db.query(Oferta).filter_by(
        producto_ref=product_ref, vendedor_id=vendor.id
    ).first()
    if offer and offer.estado != 'descontinuada':
        raise HTTPException(409, 'El vendedor ya tiene una oferta vigente.')
    try:
        sku = generate_offer_sku(
            db,
            product_sku=doc.get('sku', product_ref[:8]),
            vendor_id=vendor.id,
            exclude_offer_id=offer.id if offer else None,
        )
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    if offer:
        offer.sku = sku
        offer.estado = 'activa'
        actualizar_precio_oferta(
            db, oferta=offer, nuevo_precio=request.precio_propuesto,
            usuario_id=admin.id, motivo=f'Aprobación de solicitud #{request.id}',
            enqueue_projection=False,
        )
    else:
        offer = Oferta(
            producto_ref=product_ref, vendedor_id=vendor.id, sku=sku,
            precio_actual=request.precio_propuesto, moneda='GTQ',
            estado='activa', version=1,
        )
        db.add(offer)
        db.flush()
        db.add(OfertaPrecioHistorial(
            oferta_id=offer.id, precio=request.precio_propuesto, moneda='GTQ',
            vigente_desde=utc_now(), cambiado_por=admin.id,
            motivo=f'Aprobación de solicitud #{request.id}',
        ))
    inventory = db.query(Inventario).filter_by(
        oferta_id=offer.id, bodega='principal'
    ).first()
    if inventory:
        inventory.cantidad_disponible = request.stock_propuesto
        inventory.cantidad_reservada = 0
    else:
        db.add(Inventario(
            oferta_id=offer.id, cantidad_disponible=request.stock_propuesto,
            bodega='principal',
        ))
    db.flush()
    enqueue_primary_offer_projection(db, product_ref, offer.id)
    return product_ref, offer.id


@admin_router.post('/{request_id}/approve')
def approve_request(
    request_id: int,
    payload: ReviewPayload,
    admin: Usuario = Depends(get_admin_user),
    db: Session = Depends(get_db),
    mongo: Database = Depends(get_mongo_db),
):
    request = db.query(SolicitudCatalogo).filter_by(id=request_id).with_for_update().first()
    if not request:
        raise HTTPException(404, 'Solicitud no encontrada.')
    if request.estado != 'pendiente':
        raise HTTPException(409, 'La solicitud ya fue revisada.')
    vendor = db.get(Vendedor, request.vendedor_id)
    if not vendor or vendor.estado_verificacion != 'verificado':
        raise HTTPException(409, 'El vendedor ya no está verificado.')
    try:
        if request.tipo == 'producto_nuevo':
            product_ref, offer_id = _approve_new_product(db, mongo, request, vendor, admin)
        else:
            product_ref, offer_id = _approve_offer(db, request, vendor, admin, mongo)
        request.estado = 'aprobada'
        request.observaciones_admin = payload.observaciones
        request.revisada_por = admin.id
        request.fecha_revision = utc_now()
        request.producto_ref_resultado = product_ref
        request.oferta_id_resultado = offer_id
        _notify_vendor(db, request, vendor)
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise
    db.refresh(request)
    return _serialize_request(db, request, mongo)


@admin_router.post('/{request_id}/reject')
def reject_request(
    request_id: int,
    payload: ReviewPayload,
    admin: Usuario = Depends(get_admin_user),
    db: Session = Depends(get_db),
    mongo: Database = Depends(get_mongo_db),
):
    request = db.query(SolicitudCatalogo).filter_by(id=request_id).with_for_update().first()
    if not request:
        raise HTTPException(404, 'Solicitud no encontrada.')
    if request.estado != 'pendiente':
        raise HTTPException(409, 'La solicitud ya fue revisada.')
    if not payload.observaciones:
        raise HTTPException(400, 'Indica el motivo del rechazo.')
    vendor = db.get(Vendedor, request.vendedor_id)
    request.estado = 'rechazada'
    request.observaciones_admin = payload.observaciones
    request.revisada_por = admin.id
    request.fecha_revision = utc_now()
    _notify_vendor(db, request, vendor)
    db.commit()
    db.refresh(request)
    return _serialize_request(db, request, mongo)
