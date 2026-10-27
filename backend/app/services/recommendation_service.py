"""Recomendaciones de grafo validadas contra las autoridades comerciales."""

from __future__ import annotations

import logging

from bson import ObjectId
from sqlalchemy.orm import Session
from pymongo.database import Database

from app.services import catalog_service
from app.services import catalogo_respaldo_service as catalogo_respaldo


logger = logging.getLogger(__name__)


def categoria_principal(doc: dict | None) -> str | None:
    """Slug de la categoría principal: ``categoria`` o, si falta, la primera de ``categorias``."""
    if not doc:
        return None
    principal = doc.get('categoria')
    if isinstance(principal, dict) and principal.get('slug'):
        return principal['slug']
    categorias = doc.get('categorias') or []
    if categorias and isinstance(categorias[0], dict):
        return categorias[0].get('slug')
    return None


def refs_misma_categoria(mongo: Database, producto_ref: str) -> list[str]:
    """Productos activos con la misma categoría principal que el producto base.

    Neo4j no guarda categorías: el catálogo (MongoDB) es quien sabe a qué
    categoría pertenece cada producto. Sin categoría no hay con qué comparar y
    se devuelve una lista vacía.
    """
    if not ObjectId.is_valid(producto_ref):
        return []
    # Con MongoDB caído, el catálogo se lee de su copia en MySQL.
    base, _ = catalogo_respaldo.producto(mongo, producto_ref)
    slug = categoria_principal(base)
    if not slug:
        return []
    filtro = {
        'estado': 'activo',
        '_id': {'$ne': base['_id']},
        '$or': [
            {'categoria.slug': slug},
            {'categoria': {'$exists': False}, 'categorias.0.slug': slug},
        ],
    }
    docs, _ = catalogo_respaldo.productos(mongo, filtro, estado='activo', categoria_slug=slug, q=None)
    return [
        str(doc['_id']) for doc in docs
        if doc['_id'] != base['_id'] and categoria_principal(doc) == slug
    ]


def referencias_relacionadas(
    neo4j, producto_ref: str, *, usuario_id: int | None = None, limite: int = 8,
    permitidos: list[str] | None = None,
) -> list[dict]:
    """Productos comprados por compradores distintos del producto base.

    Con ``permitidos`` solo se consideran esas referencias (misma categoría).
    """
    return neo4j.run("""
        MATCH (:Producto {ref:$ref})<-[:DE_PRODUCTO]-(:Compra)<-[:REALIZO]-(u:Usuario)
        MATCH (u)-[:REALIZO]->(:Compra)-[:DE_PRODUCTO]->(otro:Producto)
        WHERE otro.ref <> $ref
          AND ($permitidos IS NULL OR otro.ref IN $permitidos)
          AND ($uid IS NULL OR NOT EXISTS {
              MATCH (:Usuario {id:$uid})-[:REALIZO]->(:Compra)-[:DE_PRODUCTO]->(otro)
          })
        WITH otro, count(DISTINCT u) AS compradores_comunes
        ORDER BY compradores_comunes DESC, otro.ref
        LIMIT $limite
        RETURN otro.ref AS producto_ref, compradores_comunes
    """, ref=producto_ref, uid=usuario_id, limite=limite * 3, permitidos=permitidos).data()


def recomendar(
    mysql: Session, mongo: Database, *, producto_ref: str,
    usuario_id: int | None = None, limite: int = 8,
) -> list[dict]:
    """Devuelve solo productos comprables de la misma categoría; Neo4j no decide stock/precio."""
    permitidos = refs_misma_categoria(mongo, producto_ref)
    if not permitidos:
        return []
    try:
        from app.core.db_neo4j import get_driver
        with get_driver().session() as neo4j:
            candidates = referencias_relacionadas(
                neo4j, producto_ref, usuario_id=usuario_id, limite=limite,
                permitidos=permitidos,
            )
    except Exception as exc:
        logger.warning('Recomendaciones no disponibles: %s', exc)
        return []

    result = []
    for candidate in candidates:
        product = catalog_service.obtener_producto(
            mongo, candidate['producto_ref'], mysql,
        )
        if not product or not product.get('disponible'):
            continue
        product['compradores_comunes'] = candidate['compradores_comunes']
        result.append(product)
        if len(result) >= limite:
            break
    return result
