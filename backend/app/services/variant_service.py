"""Variantes documentales en MongoDB con una identidad mínima en MySQL."""

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from pymongo.database import Database
from sqlalchemy.orm import Session

from app.models.producto_referencia import ProductoReferencia
from app.models.producto_variante_referencia import ProductoVarianteReferencia


def normalize_variant_attributes(attributes: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(attributes, dict):
        raise ValueError('Los atributos de variante deben ser un objeto.')
    normalized = {}
    for raw_key, value in attributes.items():
        key = re.sub(r'[^a-z0-9_]+', '_', str(raw_key).strip().lower()).strip('_')
        if not key:
            raise ValueError('Cada atributo de variante necesita un nombre válido.')
        if key in normalized:
            raise ValueError(f'El atributo {key} está repetido.')
        if isinstance(value, str):
            value = value.strip()
        if value in (None, '') or isinstance(value, (dict, list)):
            raise ValueError(
                f'El atributo {key} requiere un valor simple (texto, número o booleano).'
            )
        normalized[key] = value
    return dict(sorted(normalized.items()))


def variant_key(attributes: dict[str, Any]) -> str:
    if not attributes:
        return '__default__'
    return json.dumps(attributes, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def generate_variant_sku(product_sku: str, attributes: dict[str, Any]) -> str:
    if not attributes:
        return product_sku
    digest = hashlib.sha1(variant_key(attributes).encode('utf-8')).hexdigest()[:8].upper()
    return f'{product_sku[:41]}-{digest}'


def create_variant(
    mongo: Database,
    db: Session,
    *,
    producto_ref: str,
    attributes: dict[str, Any],
    product_sku: str,
    default: bool = False,
) -> tuple[ProductoVarianteReferencia, dict]:
    reference = db.query(ProductoReferencia).filter_by(producto_ref=producto_ref).first()
    if not reference:
        raise ValueError('El producto no tiene referencia SQL registrada.')
    normalized = normalize_variant_attributes(attributes)
    key = variant_key(normalized)
    existing = mongo.producto_variantes.find_one({
        'producto_ref': producto_ref, 'clave_variante': key,
    })
    if existing:
        registry = db.query(ProductoVarianteReferencia).filter_by(
            variante_ref=str(existing['_id'])
        ).first()
        if not registry:
            registry = ProductoVarianteReferencia(
                producto_referencia_id=reference.id,
                variante_ref=str(existing['_id']),
            )
            db.add(registry)
            db.flush()
        return registry, existing

    now = datetime.now(timezone.utc)
    document = {
        '_id': ObjectId(),
        'producto_ref': producto_ref,
        'sku_catalogo': generate_variant_sku(product_sku, normalized),
        'atributos': normalized,
        'clave_variante': key,
        'estado': 'activa',
        'es_predeterminada': bool(default),
        'fecha_creacion': now,
        'fecha_actualizacion': now,
    }
    mongo.producto_variantes.insert_one(document)
    try:
        registry = ProductoVarianteReferencia(
            producto_referencia_id=reference.id,
            variante_ref=str(document['_id']),
        )
        db.add(registry)
        db.flush()
    except Exception:
        mongo.producto_variantes.delete_one({'_id': document['_id']})
        raise
    return registry, document


def delete_variant(mongo: Database, db: Session, variante_id: int) -> None:
    from app.models.oferta import Oferta  # inline to avoid circular import
    registry = db.get(ProductoVarianteReferencia, variante_id)
    if not registry:
        raise ValueError('Variante no encontrada.')
    offers = (
        db.query(Oferta)
        .filter(Oferta.producto_variante_id == variante_id)
        .count()
    )
    if offers:
        raise ValueError(
            'No se puede eliminar: la variante tiene ofertas o historial '
            'comercial relacionado.'
        )
    variants = db.query(ProductoVarianteReferencia).filter_by(
        producto_referencia_id=registry.producto_referencia_id
    ).count()
    if variants <= 1:
        raise ValueError('El producto debe conservar al menos una variante.')
    db.delete(registry)
    db.flush()
    result = mongo.producto_variantes.delete_one(
        {'_id': ObjectId(registry.variante_ref)}
    )
    if result.deleted_count != 1:
        raise ValueError('No se pudo eliminar el documento de variante.')


def update_variant_attributes(
    mongo: Database, db: Session, variante_id: int, attributes: dict
) -> dict:
    registry = db.get(ProductoVarianteReferencia, variante_id)
    if not registry:
        raise ValueError('Variante no encontrada.')
    doc = mongo.producto_variantes.find_one({'_id': ObjectId(registry.variante_ref)})
    if not doc:
        raise ValueError('Documento de variante no encontrado en MongoDB.')
    from app.models.oferta import Oferta  # inline to avoid circular import
    if db.query(Oferta).filter_by(producto_variante_id=variante_id).count():
        raise ValueError(
            'No se pueden cambiar los atributos de una variante con ofertas; '
            'crea otra variante para preservar el historial comercial.'
        )
    normalized = normalize_variant_attributes(attributes)
    key = variant_key(normalized)
    duplicate = mongo.producto_variantes.find_one({
        'producto_ref': doc['producto_ref'],
        'clave_variante': key,
        '_id': {'$ne': ObjectId(registry.variante_ref)},
    })
    if duplicate:
        raise ValueError('Ya existe una variante con esa combinación de atributos.')
    try:
        product_doc = mongo.productos.find_one({'_id': ObjectId(doc['producto_ref'])})
        product_sku = product_doc.get('sku', doc['producto_ref'][:8]) if product_doc else doc['producto_ref'][:8]
    except Exception:
        product_sku = doc['producto_ref'][:8]
    new_sku = generate_variant_sku(product_sku, normalized)
    mongo.producto_variantes.update_one(
        {'_id': ObjectId(registry.variante_ref)},
        {'$set': {
            'atributos': normalized,
            'clave_variante': key,
            'sku_catalogo': new_sku,
            'fecha_actualizacion': datetime.now(timezone.utc),
        }},
    )
    return {
        'variante_id': registry.id,
        'variante_ref': registry.variante_ref,
        'producto_ref': doc['producto_ref'],
        'sku_catalogo': new_sku,
        'atributos': normalized,
        'estado': doc.get('estado', 'activa'),
        'es_predeterminada': bool(doc.get('es_predeterminada')),
    }


def list_variants(mongo: Database, db: Session, producto_ref: str) -> list[dict]:
    reference = db.query(ProductoReferencia).filter_by(producto_ref=producto_ref).first()
    if not reference:
        return []
    rows = db.query(ProductoVarianteReferencia).filter_by(
        producto_referencia_id=reference.id
    ).order_by(ProductoVarianteReferencia.id).all()
    documents = {
        str(doc['_id']): doc for doc in mongo.producto_variantes.find({
            '_id': {'$in': [ObjectId(row.variante_ref) for row in rows]}
        })
    }
    result = []
    for row in rows:
        doc = documents.get(row.variante_ref)
        if not doc:
            continue
        result.append({
            'variante_id': row.id,
            'variante_ref': row.variante_ref,
            'producto_ref': producto_ref,
            'sku_catalogo': doc.get('sku_catalogo'),
            'atributos': doc.get('atributos', {}),
            'estado': doc.get('estado', 'activa'),
            'es_predeterminada': bool(doc.get('es_predeterminada')),
        })
    return result
