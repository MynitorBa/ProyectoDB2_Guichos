"""Recomendaciones de grafo validadas contra las autoridades comerciales.

Plan B de Neo4j: si el grafo no responde, las recomendaciones salen de la
caché que se recalcula cada hora en MySQL (``recomendaciones_cache``) y, si
no hay caché para ese producto, de los más vendidos de su categoría. La
respuesta indica el ``origen`` para que la tienda lo diga con honestidad.
"""

from __future__ import annotations

import logging

from bson import ObjectId
from sqlalchemy import bindparam, func, text
from sqlalchemy.orm import Session
from pymongo.database import Database

from app.core import salud
from app.core.time import utc_now
from app.models.pedido import Pedido, PedidoLinea
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


# ── Caché horaria en MySQL (plan B de Neo4j) ─────────────────────────────────

CANDIDATOS_POR_PRODUCTO = 30
ESTADOS_VENDIDOS = ('confirmado', 'preparando', 'enviado_parcial', 'enviado', 'entregado_parcial', 'entregado')


def recalcular_cache(neo4j, mysql: Session) -> int:
    """Copia a MySQL el recorrido de co-compra de todos los productos.

    Se reemplaza la tabla completa en una transacción: quien lee ve la versión
    anterior o la nueva, nunca una mezcla. Devuelve las filas guardadas.
    """
    filas = neo4j.run("""
        MATCH (p:Producto)<-[:DE_PRODUCTO]-(:Compra)<-[:REALIZO]-(u:Usuario)
        MATCH (u)-[:REALIZO]->(:Compra)-[:DE_PRODUCTO]->(otro:Producto)
        WHERE otro.ref <> p.ref
        WITH p.ref AS producto_ref, otro.ref AS recomendado_ref, count(DISTINCT u) AS compradores
        ORDER BY producto_ref, compradores DESC, recomendado_ref
        WITH producto_ref, collect({ref: recomendado_ref, compradores: compradores})[..$maximo] AS top
        UNWIND top AS t
        RETURN producto_ref, t.ref AS recomendado_ref, t.compradores AS compradores_comunes
    """, maximo=CANDIDATOS_POR_PRODUCTO).data()
    ahora = utc_now()
    mysql.execute(text('DELETE FROM recomendaciones_cache'))
    if filas:
        mysql.execute(text("""
            INSERT INTO recomendaciones_cache
              (producto_ref, recomendado_ref, compradores_comunes, calculado_en)
            VALUES (:producto_ref, :recomendado_ref, :compradores_comunes, :calculado_en)
        """), [{**fila, 'calculado_en': ahora} for fila in filas])
    mysql.commit()
    return len(filas)


def _comprados_por(mysql: Session, usuario_id: int) -> set[str]:
    return {
        ref for (ref,) in mysql.query(PedidoLinea.producto_ref)
        .join(Pedido, Pedido.id == PedidoLinea.pedido_id)
        .filter(Pedido.usuario_id == usuario_id, Pedido.estado.in_(ESTADOS_VENDIDOS))
        .distinct() if ref
    }


def _desde_cache(mysql: Session, producto_ref: str, permitidos: list[str],
                 usuario_id: int | None) -> list[dict]:
    filas = mysql.execute(text("""
        SELECT recomendado_ref, compradores_comunes FROM recomendaciones_cache
        WHERE producto_ref = :ref AND recomendado_ref IN :permitidos
        ORDER BY compradores_comunes DESC, recomendado_ref
    """).bindparams(bindparam('permitidos', expanding=True)),
        {'ref': producto_ref, 'permitidos': permitidos}).all()
    excluir = _comprados_por(mysql, usuario_id) if usuario_id else set()
    return [
        {'producto_ref': ref, 'compradores_comunes': compradores}
        for ref, compradores in filas if ref not in excluir
    ]


def _mas_vendidos(mysql: Session, permitidos: list[str]) -> list[dict]:
    """Último recurso: los productos de la categoría con más unidades vendidas."""
    filas = mysql.query(PedidoLinea.producto_ref, func.sum(PedidoLinea.cantidad).label('unidades')) \
        .join(Pedido, Pedido.id == PedidoLinea.pedido_id) \
        .filter(PedidoLinea.producto_ref.in_(permitidos), Pedido.estado.in_(ESTADOS_VENDIDOS)) \
        .group_by(PedidoLinea.producto_ref) \
        .order_by(func.sum(PedidoLinea.cantidad).desc(), PedidoLinea.producto_ref).all()
    return [{'producto_ref': ref, 'unidades_vendidas': int(unidades)} for ref, unidades in filas]


def _candidatos(mysql: Session, producto_ref: str, permitidos: list[str],
                usuario_id: int | None, limite: int) -> tuple[list[dict], str]:
    """Neo4j si responde; si no, la caché de MySQL; si no hay caché, los más vendidos."""
    if salud.disponible('neo4j'):
        try:
            from app.core.db_neo4j import get_driver
            with get_driver().session() as neo4j:
                candidatos = referencias_relacionadas(
                    neo4j, producto_ref, usuario_id=usuario_id, limite=limite,
                    permitidos=permitidos,
                )
            salud.registrar_exito('neo4j')
            return candidatos, 'grafo'
        except Exception as exc:  # noqa: BLE001 - cualquier falla del grafo activa el respaldo
            salud.registrar_falla('neo4j', exc, confirmada=True)
            logger.warning('Neo4j no respondió; las recomendaciones usan su caché en MySQL: %s', exc)
    candidatos = _desde_cache(mysql, producto_ref, permitidos, usuario_id)
    if candidatos:
        return candidatos, 'cache'
    return _mas_vendidos(mysql, permitidos), 'mas_vendidos'


def recomendar(
    mysql: Session, mongo: Database, *, producto_ref: str,
    usuario_id: int | None = None, limite: int = 8,
) -> list[dict]:
    """Devuelve solo productos comprables de la misma categoría; Neo4j no decide stock/precio."""
    return recomendar_con_origen(
        mysql, mongo, producto_ref=producto_ref, usuario_id=usuario_id, limite=limite,
    )[0]


def recomendar_con_origen(
    mysql: Session, mongo: Database, *, producto_ref: str,
    usuario_id: int | None = None, limite: int = 8,
) -> tuple[list[dict], str | None]:
    """Como ``recomendar`` y además el origen: 'grafo', 'cache' o 'mas_vendidos'."""
    permitidos = refs_misma_categoria(mongo, producto_ref)
    if not permitidos:
        return [], None
    candidates, origen = _candidatos(mysql, producto_ref, permitidos, usuario_id, limite)

    result = []
    for candidate in candidates:
        product = catalog_service.obtener_producto(
            mongo, candidate['producto_ref'], mysql,
        )
        if not product or not product.get('disponible'):
            continue
        if 'compradores_comunes' in candidate:
            product['compradores_comunes'] = candidate['compradores_comunes']
        else:
            product['unidades_vendidas'] = candidate['unidades_vendidas']
        result.append(product)
        if len(result) >= limite:
            break
    return result, origen if result else None
