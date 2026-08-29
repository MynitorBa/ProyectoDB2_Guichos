"""
Servicio para operaciones sobre el catálogo de productos en MongoDB.
Toda escritura en la colección 'productos' genera su evento correspondiente.
"""
from datetime import datetime
import re
from typing import Any

from pymongo.database import Database
from bson import ObjectId
from bson.decimal128 import Decimal128
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.services.product_history_service import registrar_evento
from app.services.offer_service import listar_ofertas_por_referencias, oferta_principal


def _to_json(value):
    """Convierte recursivamente valores BSON a tipos JSON sin tocar Pydantic global."""
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, Decimal128):
        return float(value.to_decimal())
    if isinstance(value, dict):
        return {key: _to_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_to_json(item) for item in value]
    if isinstance(value, tuple):
        return [_to_json(item) for item in value]
    return value


def _serialize(doc: dict) -> dict:
    """Serializa un documento del catálogo y normaliza sus imágenes públicas."""
    doc = _to_json(doc)
    if 'imagenes' in doc:
        doc['imagenes'] = [
            img.get('url') if isinstance(img, dict) else img
            for img in doc['imagenes']
            if img and (not isinstance(img, dict) or img.get('url'))
        ]
    if 'categorias' not in doc and 'categoria' in doc:
        doc['categorias'] = [doc['categoria']]
    return doc


# Con mysql_db: enriquece cada doc con la oferta principal de MySQL y filtra/ordena en Python (dual-read)
# Sin mysql_db: ejecuta filtros y paginación directamente en MongoDB (modo legado)
def listar_productos(
    db: Database,
    mysql_db: Session | None = None,
    categoria_slug: str | None = None,
    precio_min: float | None = None,
    precio_max: float | None = None,
    disponible: bool | None = None,
    q: str | None = None,
    page: int = 1,
    page_size: int = 20,
    orden: str = 'precio_asc',
    estado: str | None = 'activo',
) -> dict:
    filtro: dict[str, Any] = {}
    if estado:
        filtro['estado'] = estado

    clauses = []
    if categoria_slug:
        # Los documentos nuevos pueden pertenecer a varias categorías. La
        # condición también funciona para el arreglo de subdocumentos y el
        # fallback conserva compatibilidad con documentos heredados.
        clauses.append({'$or': [
            {'categorias.slug': categoria_slug},
            {'categoria.slug': categoria_slug},
        ]})
    if q:
        # El panel promete buscar también por SKU. Para el volumen actual,
        # una expresión escapada evita limitar la consulta al índice textual.
        pattern = re.escape(q.strip())
        clauses.append({'$or': [
            {'nombre': {'$regex': pattern, '$options': 'i'}},
            {'sku': {'$regex': pattern, '$options': 'i'}},
        ]})
    if clauses:
        filtro['$and'] = clauses

    if mysql_db is not None:
        docs = list(db.productos.find(filtro))
        offers_by_ref = listar_ofertas_por_referencias(
            mysql_db, [str(doc['_id']) for doc in docs]
        )
        mismatches = 0
        enriched = []
        for doc in docs:
            item = _serialize(doc)
            if 'categorias' not in item and 'categoria' in item:
                item['categorias'] = [item['categoria']]
            legacy = {
                'precio': item.get('precio'),
                'stock': item.get('stock'),
                'vendedor_nombre': item.get('vendedor_nombre'),
            }
            offers = offers_by_ref.get(item['_id'], [])
            primary = oferta_principal(offers)
            if primary:
                item.update({
                    'oferta_id': primary['oferta_id'],
                    'precio': primary['precio'],
                    'moneda': primary['moneda'],
                    'stock': primary['stock'],
                    'disponible': primary['disponible'],
                    'vendedor_id': primary['vendedor_id'],
                    'vendedor_usuario_id': primary['vendedor_usuario_id'],
                    'vendedor_nombre': primary['vendedor_nombre'],
                    'ofertas_count': len(offers),
                })
                if (
                    float(legacy['precio'] or 0) != primary['precio']
                    or int(legacy['stock'] or 0) != primary['stock']
                    or legacy['vendedor_nombre'] != primary['vendedor_nombre']
                ):
                    mismatches += 1
            else:
                item.update({
                    'oferta_id': None,
                    'disponible': False,
                    'stock': 0,
                    'ofertas_count': 0,
                })

            if disponible is not None and item['disponible'] != disponible:
                continue
            if precio_min is not None and item.get('precio', 0) < precio_min:
                continue
            if precio_max is not None and item.get('precio', 0) > precio_max:
                continue
            enriched.append(item)

        sort_key = {
            'precio_asc': lambda item: (item.get('precio', 0), item.get('nombre', '')),
            'precio_desc': lambda item: (-item.get('precio', 0), item.get('nombre', '')),
            'nombre_asc': lambda item: item.get('nombre', ''),
            'reciente': lambda item: item.get('fecha_creacion', datetime.min),
        }.get(orden)
        enriched.sort(key=sort_key, reverse=orden == 'reciente')
        total = len(enriched)
        skip = (page - 1) * page_size
        return {
            'items': enriched[skip:skip + page_size],
            'total': total,
            'page': page,
            'page_size': page_size,
            'total_pages': max(1, -(-total // page_size)),
            'dual_read': {
                'source': 'mongodb+mysql',
                'checked': len(docs),
                'legacy_mismatches': mismatches,
            },
        }

    if disponible is not None:
        filtro['disponible'] = disponible
    if precio_min is not None or precio_max is not None:
        filtro['precio'] = {}
        if precio_min is not None:
            filtro['precio']['$gte'] = precio_min
        if precio_max is not None:
            filtro['precio']['$lte'] = precio_max

    sort_map = {
        'precio_asc':  [('precio', 1)],
        'precio_desc': [('precio', -1)],
        'nombre_asc':  [('nombre', 1)],
        'reciente':    [('fecha_creacion', -1)],
    }
    sort_order = sort_map.get(orden, [('precio', 1)])

    total = db.productos.count_documents(filtro)
    skip = (page - 1) * page_size
    docs = list(db.productos.find(filtro).sort(sort_order).skip(skip).limit(page_size))

    def _serialize_with_cats(d):
        item = _serialize(d)
        if 'categorias' not in item and 'categoria' in item:
            item['categorias'] = [item['categoria']]
        return item

    return {
        'items': [_serialize_with_cats(d) for d in docs],
        'total': total,
        'page': page,
        'page_size': page_size,
        'total_pages': max(1, -(-total // page_size)),
    }


# Busca por ObjectId o por SKU como fallback; si hay mysql_db, adjunta todas las ofertas activas
def obtener_producto(
    db: Database,
    producto_id: str,
    mysql_db: Session | None = None,
) -> dict | None:
    try:
        doc = db.productos.find_one({'_id': ObjectId(producto_id)})
    except Exception:
        doc = db.productos.find_one({'sku': producto_id})
    if not doc:
        return None
    item = _serialize(doc)
    if 'categorias' not in item and 'categoria' in item:
        item['categorias'] = [item['categoria']]
    if mysql_db is not None:
        from app.services.variant_service import list_variants

        variants = list_variants(db, mysql_db, item['_id'])
        variants_by_id = {variant['variante_id']: variant for variant in variants}
        offers = listar_ofertas_por_referencias(mysql_db, [item['_id']]).get(
            item['_id'], []
        )
        for offer in offers:
            variant = variants_by_id.get(offer['producto_variante_id'], {})
            offer['variante_atributos'] = variant.get('atributos', {})
            offer['variante_sku'] = variant.get('sku_catalogo')
        for variant in variants:
            variant['ofertas'] = [
                offer for offer in offers
                if offer['producto_variante_id'] == variant['variante_id']
            ]
            variant['disponible'] = any(
                offer['disponible'] for offer in variant['ofertas']
            )
        item['variantes'] = variants
        primary = oferta_principal(offers)
        item['ofertas'] = offers
        item['ofertas_count'] = len(offers)
        if primary:
            item.update({
                'oferta_id': primary['oferta_id'],
                'precio': primary['precio'],
                'moneda': primary['moneda'],
                'stock': primary['stock'],
                'disponible': primary['disponible'],
                'vendedor_id': primary['vendedor_id'],
                'vendedor_usuario_id': primary['vendedor_usuario_id'],
                'vendedor_nombre': primary['vendedor_nombre'],
            })
        else:
            item.update({'oferta_id': None, 'stock': 0, 'disponible': False})
        item['dual_read'] = {'source': 'mongodb+mysql'}
    return item


def crear_producto(
    db: Database,
    datos: dict,
    usuario_id: str | None = None,
) -> dict:
    ahora = utc_now()
    datos.setdefault('fecha_creacion', ahora)
    datos.setdefault('fecha_actualizacion', ahora)
    datos.setdefault('disponible', True)
    datos.setdefault('estado', 'activo')
    datos.setdefault('resumen_resenas', {'promedio': 0.0, 'total': 0})

    resultado = db.productos.insert_one(datos)
    producto_id = str(resultado.inserted_id)

    registrar_evento(
        db,
        producto_id=producto_id,
        tipo_evento='PRODUCTO_CREADO',
        datos_anteriores={},
        datos_nuevos={
            'nombre': datos.get('nombre'),
            'precio': datos.get('precio'),
            'descripcion': datos.get('descripcion'),
            'disponible': datos.get('disponible'),
            'atributos': datos.get('atributos', {}),
            'estado': datos.get('estado'),
        },
        usuario_id=usuario_id,
    )

    doc = db.productos.find_one({'_id': ObjectId(producto_id)})
    return _serialize(doc)


def actualizar_producto(
    db: Database,
    producto_id: str,
    cambios: dict,
    usuario_id: str | None = None,
) -> dict | None:
    doc_anterior = db.productos.find_one({'_id': ObjectId(producto_id)})
    if not doc_anterior:
        return None

    cambios['fecha_actualizacion'] = utc_now()

    # Determinar qué tipo de eventos generar
    if 'precio' in cambios and cambios['precio'] != doc_anterior.get('precio'):
        registrar_evento(
            db,
            producto_id=producto_id,
            tipo_evento='PRECIO_ACTUALIZADO',
            datos_anteriores={'precio': doc_anterior.get('precio')},
            datos_nuevos={'precio': cambios['precio']},
            usuario_id=usuario_id,
        )

    if 'descripcion' in cambios and cambios['descripcion'] != doc_anterior.get('descripcion'):
        registrar_evento(
            db,
            producto_id=producto_id,
            tipo_evento='DESCRIPCION_ACTUALIZADA',
            datos_anteriores={'descripcion': doc_anterior.get('descripcion')},
            datos_nuevos={'descripcion': cambios['descripcion']},
            usuario_id=usuario_id,
        )

    if 'disponible' in cambios and cambios['disponible'] != doc_anterior.get('disponible'):
        registrar_evento(
            db,
            producto_id=producto_id,
            tipo_evento='DISPONIBILIDAD_CAMBIADA',
            datos_anteriores={'disponible': doc_anterior.get('disponible')},
            datos_nuevos={'disponible': cambios['disponible']},
            usuario_id=usuario_id,
        )

    if 'atributos' in cambios:
        registrar_evento(
            db,
            producto_id=producto_id,
            tipo_evento='ATRIBUTOS_ACTUALIZADOS',
            datos_anteriores={'atributos': doc_anterior.get('atributos', {})},
            datos_nuevos={'atributos': cambios['atributos']},
            usuario_id=usuario_id,
        )

    if 'estado' in cambios and cambios['estado'] != doc_anterior.get('estado'):
        tipo_estado = (
            'PRODUCTO_DESCONTINUADO'
            if cambios['estado'] == 'descontinuado'
            else 'ESTADO_PRODUCTO_CAMBIADO'
        )
        registrar_evento(
            db,
            producto_id=producto_id,
            tipo_evento=tipo_estado,
            datos_anteriores={'estado': doc_anterior.get('estado')},
            datos_nuevos={'estado': cambios['estado']},
            usuario_id=usuario_id,
        )

    db.productos.update_one({'_id': ObjectId(producto_id)}, {'$set': cambios})
    doc = db.productos.find_one({'_id': ObjectId(producto_id)})
    return _serialize(doc) if doc else None


# Borrado lógico vía actualizar_producto; nunca elimina el documento para preservar el historial de eventos
def eliminar_producto(db: Database, producto_id: str, usuario_id: str | None = None) -> bool:
    doc = db.productos.find_one({'_id': ObjectId(producto_id)})
    if not doc:
        return False
    # Marcar como descontinuado en lugar de borrar (preserva historial)
    actualizar_producto(
        db, producto_id,
        {'estado': 'descontinuado', 'disponible': False},
        usuario_id=usuario_id,
    )
    return True


# Usa un pipeline $facet de MongoDB para obtener estadísticas globales y por categoría en una sola consulta
def stats_catalogo(db: Database) -> list[dict]:
    pipeline = [
        {
            '$facet': {
                'estadisticas_por_categoria': [
                    {'$match': {'estado': 'activo'}},
                    {
                        '$group': {
                            '_id': '$categoria.slug',
                            'categoria_nombre': {'$first': '$categoria.nombre'},
                            'total_productos': {'$sum': 1},
                            'disponibles': {'$sum': {'$cond': ['$disponible', 1, 0]}},
                            'precio_promedio': {'$avg': '$precio'},
                            'precio_minimo': {'$min': '$precio'},
                            'precio_maximo': {'$max': '$precio'},
                        }
                    },
                    {'$sort': {'total_productos': -1}},
                ],
                'top_productos_precio': [
                    {'$match': {'estado': 'activo'}},
                    {'$sort': {'precio': -1}},
                    {'$limit': 5},
                    {'$project': {
                        '_id': {'$toString': '$_id'},
                        'nombre': 1, 'precio': 1,
                        'categoria': '$categoria.nombre',
                    }},
                ],
                'resumen_global': [
                    {
                        '$group': {
                            '_id': None,
                            'total_productos': {'$sum': 1},
                            'total_activos': {'$sum': {'$cond': [
                                {'$eq': ['$estado', 'activo']}, 1, 0
                            ]}},
                            'total_inactivos': {'$sum': {'$cond': [
                                {'$eq': ['$estado', 'inactivo']}, 1, 0
                            ]}},
                            'total_descontinuados': {'$sum': {'$cond': [
                                {'$eq': ['$estado', 'descontinuado']}, 1, 0
                            ]}},
                            'total_disponibles': {'$sum': {'$cond': [
                                {'$and': [
                                    {'$eq': ['$estado', 'activo']},
                                    '$disponible',
                                ]}, 1, 0
                            ]}},
                            'precio_promedio_global': {'$avg': {'$cond': [
                                {'$eq': ['$estado', 'activo']}, '$precio', None
                            ]}},
                        }
                    },
                ],
                'productos_por_estado': [
                    {'$group': {'_id': '$estado', 'cantidad': {'$sum': 1}}},
                    {'$sort': {'_id': 1}},
                ],
            }
        }
    ]
    return list(db.productos.aggregate(pipeline))
