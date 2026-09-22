"""Detección de fraude en reseñas usando patrones de grafo Neo4j."""
from __future__ import annotations
from neo4j import Session


def detectar_bombardeo(s: Session, ventana_horas: int = 24, umbral: int = 5) -> list[dict]:
    """Productos con más de `umbral` reseñas en las últimas `ventana_horas` horas."""
    return s.run("""
        MATCH (r:Reseña)-[:SOBRE]->(p:Producto)
        WHERE r.fecha IS NOT NULL
          AND datetime(r.fecha) >= datetime() - duration({hours: $horas})
        WITH p, count(r) AS cnt
        WHERE cnt >= $umbral
        RETURN p.ref AS producto_ref, p.nombre AS producto_nombre, cnt AS total_resenas
        ORDER BY cnt DESC
    """, horas=ventana_horas, umbral=umbral).data()


def detectar_sin_compra(s: Session) -> list[dict]:
    """Reseñas de usuarios que nunca compraron el producto."""
    return s.run("""
        MATCH (u:Usuario)-[:ESCRIBIO]->(r:Reseña)-[:SOBRE]->(p:Producto)
        WHERE r.verificada = false AND r.estado IN ['pendiente', 'aprobada']
        RETURN
            u.id   AS usuario_id,
            u.nombre AS usuario_nombre,
            p.ref  AS producto_ref,
            p.nombre AS producto_nombre,
            r.id   AS resena_id,
            r.calificacion AS calificacion,
            r.fecha AS fecha
        ORDER BY r.fecha DESC
        LIMIT 50
    """).data()


def detectar_reviewer_unico_vendedor(s: Session, min_resenas: int = 3) -> list[dict]:
    """Usuarios que solo reseñan productos de un mismo vendedor (posible patrón coordinado)."""
    return s.run("""
        MATCH (u:Usuario)-[:ESCRIBIO]->(r:Reseña)-[:PARA_VENDEDOR]->(v:Vendedor)
        WITH u, count(DISTINCT v) AS vendedores_distintos, count(r) AS total_resenas
        WHERE total_resenas >= $min_resenas AND vendedores_distintos = 1
        MATCH (u)-[:ESCRIBIO]->(r2:Reseña)-[:PARA_VENDEDOR]->(v2:Vendedor)
        RETURN
            u.id   AS usuario_id,
            u.nombre AS usuario_nombre,
            v2.id  AS vendedor_id,
            v2.nombre AS vendedor_nombre,
            total_resenas,
            vendedores_distintos
        ORDER BY total_resenas DESC
        LIMIT 30
    """, min_resenas=min_resenas).data()


def detectar_cluster_coordinado(s: Session, min_comun: int = 3) -> list[dict]:
    """Pares de usuarios que han reseñado los mismos productos múltiples veces."""
    return s.run("""
        MATCH (u1:Usuario)-[:ESCRIBIO]->(:Reseña)-[:SOBRE]->(p:Producto)<-[:SOBRE]-(:Reseña)<-[:ESCRIBIO]-(u2:Usuario)
        WHERE u1.id < u2.id
        WITH u1, u2, count(DISTINCT p) AS productos_comunes
        WHERE productos_comunes >= $min_comun
        RETURN
            u1.id   AS usuario1_id,
            u1.nombre AS usuario1_nombre,
            u2.id   AS usuario2_id,
            u2.nombre AS usuario2_nombre,
            productos_comunes
        ORDER BY productos_comunes DESC
        LIMIT 20
    """, min_comun=min_comun).data()


def resumen_fraude(s: Session) -> dict:
    """Resumen ejecutivo de señales de fraude activas."""
    bombardeo   = detectar_bombardeo(s)
    sin_compra  = detectar_sin_compra(s)
    unico_vend  = detectar_reviewer_unico_vendedor(s)
    cluster     = detectar_cluster_coordinado(s)
    return {
        "bombardeo":            {"count": len(bombardeo),  "items": bombardeo[:5]},
        "sin_compra_verificada":{"count": len(sin_compra), "items": sin_compra[:5]},
        "reviewer_unico_vendedor": {"count": len(unico_vend), "items": unico_vend[:5]},
        "cluster_coordinado":   {"count": len(cluster),    "items": cluster[:5]},
    }
