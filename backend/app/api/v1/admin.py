from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from pymongo.database import Database
from sqlalchemy import func
from sqlalchemy.orm import Session

from bson import ObjectId

from app.core.db_mongo import get_mongo_db
from app.core.db_mysql import get_db
from app.core.deps import get_admin_user
from app.models.categoria import Categoria
from app.models.inventario import Inventario
from app.models.producto import Producto as ProductoSQL
from app.models.usuario import Rol, Usuario, UsuarioRol
from app.models.vendedor import Vendedor
from app.schemas.producto import ProductoCreate, ProductoUpdate
from app.services import catalog_service
from app.services.product_history_service import reconstruir_estado, obtener_historial

router = APIRouter(prefix='/admin', tags=['Admin'])


class RolesUpdate(BaseModel):
    roles: list[str]


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

    doc = {
        'sku': payload.sku,
        'nombre': payload.nombre,
        'descripcion': payload.descripcion,
        'precio': float(payload.precio),
        'moneda': 'GTQ',
        'categoria': {'slug': payload.categoria_slug, 'nombre': categoria_nombre},
        'atributos': payload.atributos,
        'imagenes': [{'url': u, 'orden': i} for i, u in enumerate(payload.imagenes)],
        'vendedor_id': str(current_user.id),
        'vendedor_nombre': f'{current_user.nombre} {current_user.apellido}',
        'resumen_resenas': {'promedio': 0.0, 'total': 0},
        'stock': payload.stock,
        'disponible': payload.stock > 0,
    }
    producto_mongo = catalog_service.crear_producto(db, doc, usuario_id=str(current_user.id))

    # Persist to MySQL (productos + inventario) and back-link mysql_id into MongoDB
    cat = mysql_db.query(Categoria).filter_by(slug=payload.categoria_slug).first()
    categoria_id = cat.id if cat else 1

    vendedor = mysql_db.query(Vendedor).filter_by(usuario_id=current_user.id).first()
    vendedor_id = vendedor.id if vendedor else 1

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

    nuevo_stock = None
    if 'stock' in cambios:
        nuevo_stock = cambios['stock']
        if nuevo_stock <= 0:
            cambios['disponible'] = False

    producto = catalog_service.actualizar_producto(
        db, producto_id, cambios, usuario_id=str(current_user.id)
    )
    if not producto:
        raise HTTPException(status_code=404, detail='Producto no encontrado.')

    if nuevo_stock is not None and producto.get('mysql_id'):
        inv = mysql_db.query(Inventario).filter_by(
            producto_id=producto['mysql_id'], bodega='principal'
        ).first()
        if inv:
            inv.cantidad_disponible = nuevo_stock
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
            fecha_dt = datetime.fromisoformat(fecha)
        else:
            fecha_dt = datetime.strptime(fecha, '%Y-%m-%d').replace(
                hour=23, minute=59, second=59
            )
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail='Formato de fecha inválido. Usa YYYY-MM-DD o YYYY-MM-DDTHH:MM:SS'
        )

    estado = reconstruir_estado(db, producto_id, fecha_dt)
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
