"""Recomendaciones de grafo validadas contra las autoridades comerciales."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session
from pymongo.database import Database

from app.services import catalog_service


logger = logging.getLogger(__name__)


def referencias_relacionadas(
    neo4j, producto_ref: str, *, usuario_id: int | None = None, limite: int = 8,
) -> list[dict]:
    """Productos comprados por compradores distintos del producto base."""
    return neo4j.run("""
        MATCH (:Producto {ref:$ref})<-[:DE_PRODUCTO]-(:Compra)<-[:REALIZO]-(u:Usuario)
        MATCH (u)-[:REALIZO]->(:Compra)-[:DE_PRODUCTO]->(otro:Producto)
        WHERE otro.ref <> $ref
          AND ($uid IS NULL OR NOT EXISTS {
              MATCH (:Usuario {id:$uid})-[:REALIZO]->(:Compra)-[:DE_PRODUCTO]->(otro)
          })
        WITH otro, count(DISTINCT u) AS compradores_comunes
        ORDER BY compradores_comunes DESC, otro.ref
        LIMIT $limite
        RETURN otro.ref AS producto_ref, compradores_comunes
    """, ref=producto_ref, uid=usuario_id, limite=limite * 3).data()


def recomendar(
    mysql: Session, mongo: Database, *, producto_ref: str,
    usuario_id: int | None = None, limite: int = 8,
) -> list[dict]:
    """Devuelve solo productos actualmente comprables; Neo4j no decide stock/precio."""
    try:
        from app.core.db_neo4j import get_driver
        with get_driver().session() as neo4j:
            candidates = referencias_relacionadas(
                neo4j, producto_ref, usuario_id=usuario_id, limite=limite,
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
