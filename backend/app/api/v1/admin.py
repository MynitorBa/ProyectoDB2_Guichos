import uuid
from datetime import datetime, timezone, timedelta
from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import Response
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from pydantic import BaseModel
from pymongo.database import Database
from sqlalchemy import func, distinct
from sqlalchemy.orm import Session

GT_TZ = timezone(timedelta(hours=-6))

UPLOAD_DIR = Path("static/products")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.gif'}

from bson import ObjectId

from app.core.db_mongo import get_mongo_db
from app.core.db_mysql import get_db
from app.core.deps import get_admin_user
from app.models.categoria import Categoria
from app.models.inventario import Inventario
from app.models.pago import Pago
from app.models.pedido import Pedido, PedidoLinea
from app.models.producto import Producto as ProductoSQL
from app.models.usuario import Rol, Usuario, UsuarioRol
from app.models.vendedor import Vendedor
from app.schemas.producto import ProductoCreate, ProductoUpdate
from app.services import catalog_service
from app.services.product_history_service import reconstruir_estado, obtener_historial

router = APIRouter(prefix='/admin', tags=['Admin'])


class RolesUpdate(BaseModel):
    roles: list[str]


class StatusUpdate(BaseModel):
    estado: str

class VendorProfilePayload(BaseModel):
    nombre_comercial: str
    nit: str


class AtributoEsquema(BaseModel):
    nombre: str
    etiqueta: str
    tipo: str = 'string'        # string | number | boolean
    requerido: bool = False
    placeholder: str | None = None


class CategoriaCreate(BaseModel):
    nombre: str
    slug: str
    descripcion: str | None = None
    padre_id: int | None = None
    atributos: list[AtributoEsquema] = []


class EsquemaUpdate(BaseModel):
    atributos: list[AtributoEsquema]
    categoria_nombre: str | None = None


# ── Gestión de usuarios ───────────────────────────────────────────────────────

@router.get('/users')
def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    _: Usuario = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    total = db.query(func.count(Usuario.id)).scalar()
    usuarios = (
        db.query(Usuario)
        .order_by(Usuario.fecha_alta.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        'items': [
            {
                'id': u.id,
                'nombre': u.nombre,
                'apellido': u.apellido,
                'email': u.email,
                'estado': u.estado,
                'roles': [r.nombre for r in u.roles],
                'fecha_alta': u.fecha_alta.isoformat() if u.fecha_alta else None,
            }
            for u in usuarios
        ],
        'total': total,
        'page': page,
        'page_size': page_size,
        'total_pages': max(1, -(-total // page_size)),
    }


@router.get('/vendors')
def list_vendors(
    _: Usuario = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    rol_vendedor = db.query(Rol).filter_by(nombre='vendedor').first()
    if not rol_vendedor:
        return []
    usuario_ids = [ur.usuario_id for ur in db.query(UsuarioRol).filter_by(rol_id=rol_vendedor.id).all()]
    if not usuario_ids:
        return []
    usuarios = db.query(Usuario).filter(Usuario.id.in_(usuario_ids)).all()
    vendedores = {v.usuario_id: v for v in db.query(Vendedor).filter(Vendedor.usuario_id.in_(usuario_ids)).all()}
    return [
        {
            'usuario_id': u.id,
            'nombre_completo': f'{u.nombre} {u.apellido}',
            'email': u.email,
            'nombre_comercial': vendedores[u.id].nombre_comercial if u.id in vendedores else None,
        }
        for u in usuarios
    ]


@router.patch('/users/{user_id}/roles')
def update_user_roles(
    user_id: int,
    payload: RolesUpdate,
    current_user: Usuario = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    if user_id == current_user.id and 'administrador' not in payload.roles:
        raise HTTPException(400, 'No puedes quitarte el rol de administrador a ti mismo.')

    usuario = db.get(Usuario, user_id)
    if not usuario:
        raise HTTPException(404, 'Usuario no encontrado.')

    roles_objs = db.query(Rol).filter(Rol.nombre.in_(payload.roles)).all()
    nombres_encontrados = {r.nombre for r in roles_objs}
    invalidos = set(payload.roles) - nombres_encontrados
    if invalidos:
        raise HTTPException(400, f'Roles no reconocidos: {", ".join(invalidos)}')

    db.query(UsuarioRol).filter(UsuarioRol.usuario_id == user_id).delete()
    db.flush()
    for rol in roles_objs:
        db.add(UsuarioRol(usuario_id=user_id, rol_id=rol.id))

    db.commit()
    db.refresh(usuario)
    return {'id': usuario.id, 'roles': [r.nombre for r in usuario.roles]}


# ── Estadísticas del catálogo ─────────────────────────────────────────────────

@router.get('/stats/catalog')
def stats_catalog(
    _: Usuario = Depends(get_admin_user),
    db: Database = Depends(get_mongo_db),
):
    return catalog_service.stats_catalogo(db)


# ── CRUD de productos (escribe en Mongo + genera eventos) ─────────────────────

@router.post('/products', status_code=201)
def crear_producto(
    payload: ProductoCreate,
    current_user: Usuario = Depends(get_admin_user),
    db: Database = Depends(get_mongo_db),
    mysql_db: Session = Depends(get_db),
):
    esquema = db.categoria_esquemas.find_one({'categoria_slug': payload.categoria_slug})
    categoria_nombre = esquema['categoria_nombre'] if esquema else payload.categoria_slug

    if payload.vendedor_usuario_id:
        v_user = mysql_db.get(Usuario, payload.vendedor_usuario_id)
        v_nombre = f'{v_user.nombre} {v_user.apellido}' if v_user else f'Usuario #{payload.vendedor_usuario_id}'
        v_mongo_id = str(payload.vendedor_usuario_id)
        v_rec = mysql_db.query(Vendedor).filter_by(usuario_id=payload.vendedor_usuario_id).first()
    else:
        v_nombre = f'{current_user.nombre} {current_user.apellido}'
        v_mongo_id = str(current_user.id)
        v_rec = mysql_db.query(Vendedor).filter_by(usuario_id=current_user.id).first()

    doc = {
        'sku': payload.sku,
        'nombre': payload.nombre,
        'descripcion': payload.descripcion,
        'precio': float(payload.precio),
        'moneda': 'GTQ',
        'categoria': {'slug': payload.categoria_slug, 'nombre': categoria_nombre},
        'atributos': payload.atributos,
        'imagenes': [{'url': u, 'orden': i} for i, u in enumerate(payload.imagenes)],
        'vendedor_id': v_mongo_id,
        'vendedor_nombre': v_nombre,
        'resumen_resenas': {'promedio': 0.0, 'total': 0},
        'stock': payload.stock,
        'disponible': payload.stock > 0,
    }
    producto_mongo = catalog_service.crear_producto(db, doc, usuario_id=str(current_user.id))

    # Persist to MySQL (productos + inventario) and back-link mysql_id into MongoDB
    cat = mysql_db.query(Categoria).filter_by(slug=payload.categoria_slug).first()
    categoria_id = cat.id if cat else 1

    vendedor_id = v_rec.id if v_rec else 1

    prod_sql = ProductoSQL(
        sku=payload.sku,
        nombre=payload.nombre,
        descripcion=payload.descripcion,
        precio=payload.precio,
        categoria_id=categoria_id,
        vendedor_id=vendedor_id,
        producto_ref=producto_mongo['_id'],
        estado='activo',
    )
    mysql_db.add(prod_sql)
    mysql_db.flush()

    inv = Inventario(
        producto_id=prod_sql.id,
        cantidad_disponible=payload.stock,
        bodega='principal',
    )
    mysql_db.add(inv)
    mysql_db.commit()

    db.productos.update_one(
        {'_id': ObjectId(producto_mongo['_id'])},
        {'$set': {'mysql_id': prod_sql.id}},
    )
    producto_mongo['mysql_id'] = prod_sql.id

    return producto_mongo


@router.post('/upload')
async def upload_image(
    file: UploadFile = File(...),
    _: Usuario = Depends(get_admin_user),
):
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f'Tipo de archivo no permitido. Usa: {", ".join(ALLOWED_EXTENSIONS)}')
    filename = f"{uuid.uuid4()}{ext}"
    dest = UPLOAD_DIR / filename
    content = await file.read()
    dest.write_bytes(content)
    return {'url': f'/static/products/{filename}'}


@router.put('/products/{producto_id}')
def actualizar_producto(
    producto_id: str,
    payload: ProductoUpdate,
    current_user: Usuario = Depends(get_admin_user),
    db: Database = Depends(get_mongo_db),
    mysql_db: Session = Depends(get_db),
):
    cambios = payload.model_dump(exclude_none=True)
    if 'precio' in cambios:
        cambios['precio'] = float(cambios['precio'])
    if 'imagenes' in cambios:
        cambios['imagenes'] = [{'url': u, 'orden': i} for i, u in enumerate(cambios['imagenes'])]

    nuevo_stock = None
    if 'stock' in cambios:
        nuevo_stock = cambios['stock']
        if nuevo_stock <= 0:
            cambios['disponible'] = False

    nuevo_vendedor_id_sql = None
    if 'vendedor_usuario_id' in cambios:
        v_uid = cambios.pop('vendedor_usuario_id')
        if v_uid:
            v_user = mysql_db.get(Usuario, v_uid)
            cambios['vendedor_id'] = str(v_uid)
            cambios['vendedor_nombre'] = f'{v_user.nombre} {v_user.apellido}' if v_user else f'Usuario #{v_uid}'
            v_rec = mysql_db.query(Vendedor).filter_by(usuario_id=v_uid).first()
            nuevo_vendedor_id_sql = v_rec.id if v_rec else None

    producto = catalog_service.actualizar_producto(
        db, producto_id, cambios, usuario_id=str(current_user.id)
    )
    if not producto:
        raise HTTPException(status_code=404, detail='Producto no encontrado.')

    if producto.get('mysql_id'):
        needs_commit = False
        prod_sql = mysql_db.get(ProductoSQL, producto['mysql_id'])
        if nuevo_stock is not None:
            inv = mysql_db.query(Inventario).filter_by(
                producto_id=producto['mysql_id'], bodega='principal'
            ).first()
            if inv:
                inv.cantidad_disponible = nuevo_stock
                needs_commit = True
        if nuevo_vendedor_id_sql is not None and prod_sql:
            prod_sql.vendedor_id = nuevo_vendedor_id_sql
            needs_commit = True
        if needs_commit:
            mysql_db.commit()

    return producto


@router.delete('/products/{producto_id}', status_code=204)
def eliminar_producto(
    producto_id: str,
    current_user: Usuario = Depends(get_admin_user),
    db: Database = Depends(get_mongo_db),
):
    eliminado = catalog_service.eliminar_producto(db, producto_id, usuario_id=str(current_user.id))
    if not eliminado:
        raise HTTPException(status_code=404, detail='Producto no encontrado.')


# ── Historial de eventos ───────────────────────────────────────────────────────

@router.get('/products/{producto_id}/history')
def historial_producto(
    producto_id: str,
    _: Usuario = Depends(get_admin_user),
    db: Database = Depends(get_mongo_db),
):
    eventos = obtener_historial(db, producto_id)
    if not eventos:
        raise HTTPException(status_code=404, detail='No hay historial para este producto.')
    return {'producto_id': producto_id, 'eventos': eventos}


@router.get('/products/{producto_id}/state-at')
def estado_en_fecha(
    producto_id: str,
    fecha: str = Query(..., description='Fecha en formato YYYY-MM-DD o YYYY-MM-DDTHH:MM:SS'),
    _: Usuario = Depends(get_admin_user),
    db: Database = Depends(get_mongo_db),
):
    try:
        if 'T' in fecha:
            # Acepta HH:MM o HH:MM:SS — fromisoformat maneja ambos
            naive_gt = datetime.fromisoformat(fecha)
        else:
            naive_gt = datetime.strptime(fecha, '%Y-%m-%d').replace(
                hour=23, minute=59, second=59
            )
        # El usuario ingresa hora en horario de Guatemala → convertir a UTC para consultar Mongo
        fecha_utc = naive_gt.replace(tzinfo=GT_TZ).astimezone(timezone.utc).replace(tzinfo=None)
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail='Formato de fecha inválido. Usa YYYY-MM-DD o YYYY-MM-DDTHH:MM'
        )

    estado = reconstruir_estado(db, producto_id, fecha_utc)
    if estado is None:
        raise HTTPException(
            status_code=404,
            detail=f'El producto no existía o no tiene eventos hasta {fecha}.'
        )
    return estado


# ── Migración de stock ────────────────────────────────────────────────────────

@router.post('/migrate-stock', status_code=200)
def migrar_stock(
    _: Usuario = Depends(get_admin_user),
    db: Database = Depends(get_mongo_db),
    mysql_db: Session = Depends(get_db),
):
    """Sincroniza stock de MySQL inventario → MongoDB para productos existentes."""
    actualizados = 0
    productos = list(db.productos.find({'mysql_id': {'$exists': True}}, {'_id': 1, 'mysql_id': 1, 'disponible': 1}))
    for prod in productos:
        mysql_id = prod.get('mysql_id')
        if not mysql_id:
            continue
        inv = mysql_db.query(Inventario).filter_by(producto_id=mysql_id, bodega='principal').first()
        if inv:
            set_data = {'stock': inv.cantidad_disponible}
            if inv.cantidad_disponible <= 0:
                set_data['disponible'] = False
            db.productos.update_one({'_id': prod['_id']}, {'$set': set_data})
            actualizados += 1
    return {'actualizados': actualizados}


# ── Gestión de categorías ─────────────────────────────────────────────────────

@router.get('/categories')
def listar_categorias_admin(
    _: Usuario = Depends(get_admin_user),
    db: Session = Depends(get_db),
    mongo: Database = Depends(get_mongo_db),
):
    """Lista categorías de MySQL enriquecidas con su esquema de MongoDB."""
    categorias = db.query(Categoria).order_by(Categoria.orden, Categoria.nombre).all()
    esquemas = {
        e['categoria_slug']: e.get('atributos', [])
        for e in mongo.categoria_esquemas.find({}, {'categoria_slug': 1, 'atributos': 1})
    }
    return [
        {
            'id': c.id,
            'nombre': c.nombre,
            'slug': c.slug,
            'descripcion': c.descripcion,
            'padre_id': c.categoria_padre_id,
            'activa': c.activa,
            'atributos': esquemas.get(c.slug, []),  # schema desde Mongo
        }
        for c in categorias
    ]


@router.post('/categories', status_code=201)
def crear_categoria(
    payload: CategoriaCreate,
    _: Usuario = Depends(get_admin_user),
    db: Session = Depends(get_db),
    mongo: Database = Depends(get_mongo_db),
):
    """
    Crea la categoría en MySQL (nombre, slug, jerarquía) y su definición
    de campos en MongoDB (categoria_esquemas). Cada BD almacena lo que le
    corresponde según su naturaleza.
    """
    if db.query(Categoria).filter_by(slug=payload.slug).first():
        raise HTTPException(400, f'Ya existe una categoría con slug "{payload.slug}".')

    # 1. Guardar estructura relacional en MySQL
    cat = Categoria(
        nombre=payload.nombre,
        slug=payload.slug,
        descripcion=payload.descripcion,
        categoria_padre_id=payload.padre_id,
        activa=True,
    )
    db.add(cat)
    db.commit()
    db.refresh(cat)

    # 2. Guardar definición de atributos en MongoDB (upsert por slug)
    mongo.categoria_esquemas.update_one(
        {'categoria_slug': payload.slug},
        {'$set': {
            'categoria_slug': payload.slug,
            'categoria_nombre': payload.nombre,
            'atributos': [a.model_dump() for a in payload.atributos],
        }},
        upsert=True,
    )

    return {'id': cat.id, 'slug': cat.slug, 'nombre': cat.nombre}


@router.put('/categories/{slug}/schema')
def actualizar_esquema(
    slug: str,
    payload: EsquemaUpdate,
    _: Usuario = Depends(get_admin_user),
    db: Session = Depends(get_db),
    mongo: Database = Depends(get_mongo_db),
):
    """Actualiza los campos del esquema en MongoDB sin tocar MySQL."""
    cat = db.query(Categoria).filter_by(slug=slug).first()
    if not cat:
        raise HTTPException(404, 'Categoría no encontrada.')

    mongo.categoria_esquemas.update_one(
        {'categoria_slug': slug},
        {'$set': {
            'categoria_nombre': payload.categoria_nombre or cat.nombre,
            'atributos': [a.model_dump() for a in payload.atributos],
        }},
        upsert=True,
    )
    return {'slug': slug, 'atributos': len(payload.atributos)}


@router.delete('/categories/{slug}', status_code=204)
def eliminar_categoria(
    slug: str,
    _: Usuario = Depends(get_admin_user),
    db: Session = Depends(get_db),
    mongo: Database = Depends(get_mongo_db),
):
    """Elimina la categoría de MySQL y su esquema de MongoDB."""
    cat = db.query(Categoria).filter_by(slug=slug).first()
    if not cat:
        raise HTTPException(404, 'Categoría no encontrada.')

    db.delete(cat)
    db.commit()
    mongo.categoria_esquemas.delete_one({'categoria_slug': slug})


# ── Panel de ventas ───────────────────────────────────────────────────────────

@router.get('/sales/stats')
def sales_stats(
    _: Usuario = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    total_pedidos = db.query(func.count(Pedido.id)).scalar() or 0

    agg = db.query(
        func.sum(Pedido.total),
        func.avg(Pedido.total),
    ).filter(Pedido.estado.notin_(['cancelado', 'reembolsado'])).first()
    total_ingresos = float(agg[0] or 0)
    promedio_pedido = float(agg[1] or 0)

    pendientes = db.query(func.count(Pedido.id)).filter(Pedido.estado == 'pendiente').scalar() or 0

    por_estado = [
        {'estado': e, 'cantidad': c}
        for e, c in db.query(Pedido.estado, func.count(Pedido.id)).group_by(Pedido.estado).all()
    ]

    hoy_gt = datetime.now(GT_TZ).date()
    hace_30 = hoy_gt - timedelta(days=29)
    cutoff = datetime(hace_30.year, hace_30.month, hace_30.day)

    dia_rows = db.query(
        func.date(Pedido.fecha_creacion).label('dia'),
        func.sum(Pedido.total).label('total'),
    ).filter(
        Pedido.fecha_creacion >= cutoff,
        Pedido.estado.notin_(['cancelado', 'reembolsado']),
    ).group_by('dia').all()

    dias_map = {str(r.dia): float(r.total) for r in dia_rows}
    ingresos_por_dia = [
        {
            'fecha': str(hace_30 + timedelta(days=i)),
            'total': dias_map.get(str(hace_30 + timedelta(days=i)), 0.0),
        }
        for i in range(30)
    ]

    top_rows = (
        db.query(
            Vendedor.nombre_comercial,
            func.sum(PedidoLinea.subtotal_linea).label('ingresos'),
            func.count(distinct(PedidoLinea.pedido_id)).label('pedidos'),
        )
        .join(ProductoSQL, ProductoSQL.vendedor_id == Vendedor.id)
        .join(PedidoLinea, PedidoLinea.producto_id == ProductoSQL.id)
        .join(Pedido, Pedido.id == PedidoLinea.pedido_id)
        .filter(Pedido.estado.notin_(['cancelado', 'reembolsado']))
        .group_by(Vendedor.id, Vendedor.nombre_comercial)
        .order_by(func.sum(PedidoLinea.subtotal_linea).desc())
        .limit(5)
        .all()
    )
    top_vendedores = [
        {'nombre': r.nombre_comercial, 'ingresos': float(r.ingresos), 'pedidos': r.pedidos}
        for r in top_rows
    ]

    return {
        'total_pedidos': total_pedidos,
        'total_ingresos': total_ingresos,
        'promedio_pedido': promedio_pedido,
        'pendientes': pendientes,
        'por_estado': por_estado,
        'ingresos_por_dia': ingresos_por_dia,
        'top_vendedores': top_vendedores,
    }


@router.get('/sales')
def list_sales(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    _: Usuario = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    total = db.query(func.count(Pedido.id)).scalar() or 0
    pedidos = (
        db.query(Pedido)
        .order_by(Pedido.fecha_creacion.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    all_ids = [l.producto_id for p in pedidos for l in p.lineas if l.producto_id]
    vendedor_map = {}
    if all_ids:
        rows = (
            db.query(ProductoSQL.id, Vendedor.nombre_comercial)
            .join(Vendedor, Vendedor.id == ProductoSQL.vendedor_id)
            .filter(ProductoSQL.id.in_(all_ids))
            .all()
        )
        vendedor_map = {r[0]: r[1] for r in rows}

    items = []
    for p in pedidos:
        u = p.usuario
        pago = p.pagos[0] if p.pagos else None
        items.append({
            'id': p.id,
            'fecha': p.fecha_creacion.replace(tzinfo=timezone.utc).astimezone(GT_TZ).isoformat(),
            'estado': p.estado,
            'subtotal': float(p.subtotal),
            'impuestos': float(p.impuestos),
            'total': float(p.total),
            'comprador': {
                'id': u.id,
                'nombre': f'{u.nombre} {u.apellido}',
                'email': u.email,
            } if u else None,
            'pago': {
                'metodo': pago.metodo.nombre if pago and pago.metodo else None,
                'estado': pago.estado,
                'referencia': pago.referencia_transaccion,
                'monto': float(pago.monto),
            } if pago else None,
            'lineas': [
                {
                    'producto_nombre': l.producto_nombre,
                    'precio_unitario': float(l.precio_unitario),
                    'cantidad': l.cantidad,
                    'subtotal_linea': float(l.subtotal_linea),
                    'vendedor': vendedor_map.get(l.producto_id) if l.producto_id else None,
                }
                for l in p.lineas
            ],
        })

    return {
        'items': items,
        'total': total,
        'page': page,
        'page_size': page_size,
        'total_pages': max(1, -(-total // page_size)),
    }


@router.get('/sales/export')
def export_sales_excel(
    _: Usuario = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    pedidos = db.query(Pedido).order_by(Pedido.fecha_creacion.desc()).all()

    all_ids = [l.producto_id for p in pedidos for l in p.lineas if l.producto_id]
    vendedor_map = {}
    if all_ids:
        rows = (
            db.query(ProductoSQL.id, Vendedor.nombre_comercial)
            .join(Vendedor, Vendedor.id == ProductoSQL.vendedor_id)
            .filter(ProductoSQL.id.in_(all_ids))
            .all()
        )
        vendedor_map = {r[0]: r[1] for r in rows}

    wb = Workbook()
    ws = wb.active
    ws.title = 'Ventas'

    hdr_fill = PatternFill('solid', fgColor='2563EB')
    hdr_font = Font(color='FFFFFF', bold=True, size=10)
    hdr_align = Alignment(horizontal='center', vertical='center')

    COLS = [
        'Pedido #', 'Fecha (GT)', 'Estado', 'Comprador', 'Email',
        'Producto', 'Vendedor', 'Precio Unit.', 'Cantidad', 'Subtotal línea',
        'Impuestos', 'Total pedido', 'Método pago', 'Estado pago',
    ]
    for col, h in enumerate(COLS, 1):
        c = ws.cell(row=1, column=col, value=h)
        c.fill = hdr_fill
        c.font = hdr_font
        c.alignment = hdr_align
    ws.row_dimensions[1].height = 18

    for p in pedidos:
        u = p.usuario
        pago = p.pagos[0] if p.pagos else None
        fecha_gt = p.fecha_creacion.replace(tzinfo=timezone.utc).astimezone(GT_TZ).strftime('%Y-%m-%d %H:%M')
        for l in p.lineas:
            ws.append([
                p.id,
                fecha_gt,
                p.estado,
                f'{u.nombre} {u.apellido}' if u else '—',
                u.email if u else '—',
                l.producto_nombre,
                vendedor_map.get(l.producto_id, '—') if l.producto_id else '—',
                float(l.precio_unitario),
                l.cantidad,
                float(l.subtotal_linea),
                float(p.impuestos),
                float(p.total),
                pago.metodo.nombre if pago and pago.metodo else '—',
                pago.estado if pago else '—',
            ])

    for col in ws.columns:
        max_len = max((len(str(c.value or '')) for c in col), default=8)
        ws.column_dimensions[col[0].column_letter].width = min(max_len + 3, 45)

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)

    return Response(
        content=buf.read(),
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': 'attachment; filename="ventas-TiendaYa.xlsx"'},
    )


# ── Pedidos (admin) ───────────────────────────────────────────────────────────

ESTADOS_VALIDOS = set(Pedido.__table__.c['estado'].type.enums)

@router.get('/orders')
def list_admin_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    estado: str | None = Query(None),
    _: Usuario = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    q = db.query(Pedido)
    if estado:
        q = q.filter(Pedido.estado == estado)
    total = q.count()
    pedidos = (
        q.order_by(Pedido.fecha_creacion.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        'items': [
            {
                'id': p.id,
                'fecha': p.fecha_creacion.replace(tzinfo=timezone.utc).astimezone(GT_TZ).isoformat(),
                'estado': p.estado,
                'total': float(p.total),
                'comprador': {
                    'nombre': f'{p.usuario.nombre} {p.usuario.apellido}' if p.usuario else '—',
                    'email': p.usuario.email if p.usuario else '—',
                },
            }
            for p in pedidos
        ],
        'total': total,
        'page': page,
        'page_size': page_size,
        'total_pages': max(1, -(-total // page_size)),
    }


@router.patch('/orders/{pedido_id}/status')
def update_admin_order_status(
    pedido_id: int,
    payload: StatusUpdate,
    _: Usuario = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    if payload.estado not in ESTADOS_VALIDOS:
        raise HTTPException(400, 'Estado no válido.')
    pedido = db.get(Pedido, pedido_id)
    if not pedido:
        raise HTTPException(404, 'Pedido no encontrado.')
    pedido.estado = payload.estado
    db.commit()
    return {'id': pedido_id, 'estado': payload.estado}


# ── Perfil de vendedor ────────────────────────────────────────────────────────

@router.post('/users/{user_id}/vendor-profile')
def set_vendor_profile(
    user_id: int,
    payload: VendorProfilePayload,
    _: Usuario = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    user = db.get(Usuario, user_id)
    if not user:
        raise HTTPException(404, 'Usuario no encontrado.')
    v = db.query(Vendedor).filter_by(usuario_id=user_id).first()
    if v:
        v.nombre_comercial = payload.nombre_comercial.strip()
        v.nit = payload.nit.strip()
    else:
        v = Vendedor(
            usuario_id=user_id,
            nombre_comercial=payload.nombre_comercial.strip(),
            nit=payload.nit.strip(),
        )
        db.add(v)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(400, 'El NIT ya está en uso por otro vendedor.')
    return {'usuario_id': user_id, 'nombre_comercial': v.nombre_comercial}
