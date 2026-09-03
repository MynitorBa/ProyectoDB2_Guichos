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
from app.models.producto_variante_referencia import ProductoVarianteReferencia
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
from app.services.offer_history_service import (
    registrar_estado_oferta,
    registrar_saldo_inventario,
)
from app.services.sku_service import generate_offer_sku, generate_product_sku
from app.services.variant_service import create_variant, list_variants, normalize_variant_attributes, variant_key


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
    producto_variante_id: int
    precio: Decimal = Field(gt=0)
    stock: int = Field(ge=0)
    observaciones: str | None = Field(default=None, max_length=2000)


class ReviewPayload(BaseModel):
    model_config = ConfigDict(extra='forbid')
    observaciones: str | None = Field(default=None, max_length=2000)


class VariantProposalCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    producto_ref: str = Field(min_length=24, max_length=24)
    atributos: dict
    precio: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    stock: int = Field(ge=0, le=2147483647)
    observaciones: str | None = Field(default=None, max_length=2000)


# Verifica que el usuario tenga perfil de vendedor Y esté verificado antes de operar
def _get_vendor(db: Session, user: Usuario) -> Vendedor:
    vendor = db.query(Vendedor).filter_by(usuario_id=user.id).first()
    if not vendor:
        raise HTTPException(403, 'No tienes un perfil de vendedor configurado.')
    if vendor.estado_verificacion != 'verificado':
        raise HTTPException(403, 'Tu perfil de vendedor debe estar verificado.')
    return vendor


# Notifica a todos los usuarios con rol 'administrador' sobre una nueva solicitud
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
    variant_attributes = request.atributos if request.tipo == 'variante_nueva' else {}
    if request.producto_ref_solicitado:
        try:
            doc = mongo.productos.find_one(
                {'_id': ObjectId(request.producto_ref_solicitado)}, {'nombre': 1, 'sku': 1}
            )
        except Exception:
            doc = None
        requested_name = (doc or {}).get('nombre', 'Producto no disponible')
    if request.producto_variante_id_solicitado:
        variant = db.get(
            ProductoVarianteReferencia,
            request.producto_variante_id_solicitado,
        )
        if variant:
            variant_doc = mongo.producto_variantes.find_one(
                {'_id': ObjectId(variant.variante_ref)}, {'atributos': 1}
            )
            variant_attributes = (variant_doc or {}).get('atributos', {})
    return {
        'id': request.id,
        'tipo': request.tipo,
        'estado': request.estado,
        'vendedor_id': request.vendedor_id,
        'vendedor_nombre': vendor.nombre_comercial if vendor else None,
        'producto_ref_solicitado': request.producto_ref_solicitado,
        'producto_variante_id_solicitado': request.producto_variante_id_solicitado,
        'variante_atributos': variant_attributes,
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


# El vendedor propone un producto nuevo: valida categorías, imágenes y atributos antes de crear la SolicitudCatalogo
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


# El vendedor solicita unirse como oferente a un producto ya existente en el catálogo
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
    variant = db.get(ProductoVarianteReferencia, payload.producto_variante_id)
    if not variant or variant.producto_referencia_id != reference.id:
        raise HTTPException(400, 'La variante no pertenece al producto seleccionado.')
    existing_offer = db.query(Oferta).filter(
        Oferta.producto_variante_id == variant.id,
        Oferta.vendedor_id == vendor.id,
        Oferta.estado != 'descontinuada',
    ).first()
    if existing_offer:
        raise HTTPException(409, 'Ya tienes una oferta vigente para esta variante.')
    pending = db.query(SolicitudCatalogo).filter_by(
        vendedor_id=vendor.id, tipo='oferta_existente', estado='pendiente',
        producto_ref_solicitado=payload.producto_ref,
        producto_variante_id_solicitado=variant.id,
    ).first()
    if pending:
        raise HTTPException(409, 'Ya existe una solicitud pendiente para este producto.')
    request = SolicitudCatalogo(
        vendedor_id=vendor.id, tipo='oferta_existente', estado='pendiente',
        producto_ref_solicitado=payload.producto_ref,
        producto_variante_id_solicitado=variant.id,
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


@vendor_router.get('')
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


@vendor_router.post('/variants', status_code=201)
def propose_variant(payload: VariantProposalCreate,
    current_user: Usuario = Depends(get_vendor_user), db: Session = Depends(get_db),
    mongo: Database = Depends(get_mongo_db)):
    vendor = _get_vendor(db, current_user)
    reference = db.query(ProductoReferencia).filter_by(producto_ref=payload.producto_ref).with_for_update().first()
    if not ObjectId.is_valid(payload.producto_ref) or not reference:
        raise HTTPException(404, 'Producto no encontrado.')
    product = mongo.productos.find_one({'_id': ObjectId(payload.producto_ref), 'estado': 'activo'})
    if not product:
        raise HTTPException(409, 'El producto no está activo.')
    try:
        attrs = normalize_variant_attributes(payload.atributos)
        if not attrs:
            raise ValueError('Indica los atributos que identifican la nueva variante.')
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if mongo.producto_variantes.find_one({'producto_ref': payload.producto_ref, 'clave_variante': variant_key(attrs)}):
        raise HTTPException(409, 'Esa variante ya existe. Utiliza Solicitar oferta.')
    pending = db.query(SolicitudCatalogo).filter_by(vendedor_id=vendor.id,
        producto_ref_solicitado=payload.producto_ref, tipo='variante_nueva', estado='pendiente').all()
    if any(variant_key(row.atributos) == variant_key(attrs) for row in pending):
        raise HTTPException(409, 'Ya tienes una solicitud pendiente para esa variante.')
    request = SolicitudCatalogo(vendedor_id=vendor.id, tipo='variante_nueva', estado='pendiente',
        producto_ref_solicitado=payload.producto_ref, atributos=attrs,
        precio_propuesto=payload.precio, stock_propuesto=payload.stock,
        observaciones_vendedor=payload.observaciones)
    db.add(request)
    db.flush()
    _notify_admins(db, request.id, vendor)
    db.commit()
    return _serialize_request(db, request, mongo)


@vendor_router.get('/{request_id}')
def own_request_detail(request_id: int, current_user: Usuario = Depends(get_vendor_user),
    db: Session = Depends(get_db), mongo: Database = Depends(get_mongo_db)):
    vendor = _get_vendor(db, current_user)
    request = db.query(SolicitudCatalogo).filter_by(id=request_id, vendedor_id=vendor.id).first()
    if not request:
        raise HTTPException(404, 'Solicitud no encontrada.')
    return _serialize_request(db, request, mongo)


@admin_router.get('/{request_id}')
def admin_request_detail(request_id: int, _: Usuario = Depends(get_admin_user),
    db: Session = Depends(get_db), mongo: Database = Depends(get_mongo_db)):
    request = db.get(SolicitudCatalogo, request_id)
    if not request:
        raise HTTPException(404, 'Solicitud no encontrada.')
    return _serialize_request(db, request, mongo)


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


@admin_router.get('')
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


# Aprueba un producto nuevo: genera SKU, inserta en Mongo y crea todas las entidades SQL (con compensación si falla)
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
        variant_registry, _ = create_variant(
            mongo,
            db,
            producto_ref=product['_id'],
            attributes={},
            product_sku=sku,
            default=True,
        )
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
            producto_ref=product['_id'],
            producto_variante_id=variant_registry.id,
            vendedor_id=vendor.id, sku=sku,
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
        inventory = Inventario(
            oferta_id=offer.id, cantidad_disponible=request.stock_propuesto,
            bodega='principal',
        )
        db.add(inventory)
        db.flush()
        registrar_estado_oferta(
            db, oferta=offer, usuario_id=admin.id,
            motivo=f'Estado inicial por aprobación de solicitud #{request.id}',
            forzar=True,
        )
        registrar_saldo_inventario(
            db, inventario=inventory, usuario_id=admin.id,
            motivo=f'Saldo inicial por aprobación de solicitud #{request.id}',
            forzar=True,
        )
        enqueue_primary_offer_projection(db, product['_id'], offer.id)
        return product['_id'], offer.id
    except Exception:
        mongo.productos.delete_one({'_id': ObjectId(product['_id'])})
        mongo.producto_eventos.delete_many({'producto_id': product['_id']})
        mongo.producto_variantes.delete_many({'producto_ref': product['_id']})
        raise


# Aprueba una solicitud de oferta: reactiva o crea la Oferta en MySQL y actualiza su inventario
def _approve_offer(
    db: Session, request: SolicitudCatalogo,
    vendor: Vendedor, admin: Usuario, mongo: Database,
) -> tuple[str, int]:
    product_ref = request.producto_ref_solicitado
    try:
        doc = mongo.productos.find_one({'_id': ObjectId(product_ref)}, {'sku': 1})
    except Exception:
        doc = None
    product_reference = db.query(ProductoReferencia).filter_by(
        producto_ref=product_ref
    ).first()
    variant = db.get(
        ProductoVarianteReferencia, request.producto_variante_id_solicitado
    )
    if (
        not doc or not product_reference or not variant
        or variant.producto_referencia_id != product_reference.id
    ):
        raise HTTPException(409, 'El producto dejó de estar disponible.')
    variant_doc = mongo.producto_variantes.find_one(
        {'_id': ObjectId(variant.variante_ref)}
    )
    if not variant_doc or variant_doc.get('estado') != 'activa':
        raise HTTPException(409, 'La variante dejó de estar disponible.')
    offer = db.query(Oferta).filter_by(
        producto_variante_id=variant.id, vendedor_id=vendor.id
    ).first()
    if offer and offer.estado != 'descontinuada':
        raise HTTPException(409, 'El vendedor ya tiene una oferta vigente para esta variante.')
    try:
        sku = generate_offer_sku(
            db,
            product_sku=variant_doc.get(
                'sku_catalogo', doc.get('sku', product_ref[:8])
            ),
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
            producto_ref=product_ref,
            producto_variante_id=variant.id,
            vendedor_id=vendor.id, sku=sku,
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
        inventory = Inventario(
            oferta_id=offer.id, cantidad_disponible=request.stock_propuesto,
            bodega='principal',
        )
        db.add(inventory)
    db.flush()
    registrar_estado_oferta(
        db, oferta=offer, usuario_id=admin.id,
        motivo=f'Oferta aprobada mediante solicitud #{request.id}',
    )
    registrar_saldo_inventario(
        db, inventario=inventory, usuario_id=admin.id,
        motivo=f'Stock aprobado mediante solicitud #{request.id}',
    )
    enqueue_primary_offer_projection(db, product_ref, offer.id)
    return product_ref, offer.id


# Aprueba la solicitud con bloqueo optimista (with_for_update); despacha a _approve_new_product o _approve_offer según el tipo
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
    created_variant = None
    try:
        if request.tipo == 'producto_nuevo':
            product_ref, offer_id = _approve_new_product(db, mongo, request, vendor, admin)
        else:
            if request.tipo == 'variante_nueva':
                # Serializa aprobaciones distintas del mismo producto.
                reference = db.query(ProductoReferencia).filter_by(
                    producto_ref=request.producto_ref_solicitado).with_for_update().first()
                product = mongo.productos.find_one({'_id': ObjectId(request.producto_ref_solicitado), 'estado': 'activo'})
                if not reference or not product:
                    raise HTTPException(409, 'El producto ya no está activo.')
                attrs = normalize_variant_attributes(request.atributos)
                existing = mongo.producto_variantes.find_one({
                    'producto_ref': request.producto_ref_solicitado, 'clave_variante': variant_key(attrs)})
                registry, document = create_variant(mongo, db,
                    producto_ref=request.producto_ref_solicitado, attributes=attrs,
                    product_sku=product.get('sku', request.producto_ref_solicitado[:8]))
                if not existing:
                    created_variant = document['_id']
                request.producto_variante_id_solicitado = registry.id
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
        if created_variant is not None:
            mongo.producto_variantes.delete_one({'_id': created_variant})
        raise
    except Exception:
        db.rollback()
        if created_variant is not None:
            mongo.producto_variantes.delete_one({'_id': created_variant})
        raise
    db.refresh(request)
    return _serialize_request(db, request, mongo)


# Rechaza la solicitud; requiere observaciones obligatorias que se notifican al vendedor
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
