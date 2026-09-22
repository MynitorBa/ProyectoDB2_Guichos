"""Servicio de reseñas sobre Neo4j."""
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from neo4j import Session

def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()

# ── Merge de nodos base ────────────────────────────────────────────────────────

def ensure_usuario(s: Session, user_id: int, nombre: str, email: str) -> None:
    s.run(
        "MERGE (u:Usuario {id: $id}) SET u.nombre = $nombre, u.email = $email",
        id=user_id, nombre=nombre, email=email,
    )

def ensure_producto(s: Session, producto_ref: str, nombre: str) -> None:
    s.run(
        "MERGE (p:Producto {ref: $ref}) SET p.nombre = $nombre",
        ref=producto_ref, nombre=nombre,
    )

def ensure_vendedor(s: Session, vendedor_id: int, nombre: str) -> None:
    s.run(
        "MERGE (v:Vendedor {id: $id}) SET v.nombre = $nombre",
        id=vendedor_id, nombre=nombre,
    )

def registrar_compra(s: Session, user_id: int, producto_ref: str,
                     pedido_id: int, oferta_id: int, fecha: str) -> None:
    """Crea/actualiza la relación COMPRO entre usuario y producto."""
    s.run("""
        MATCH (u:Usuario {id: $uid}), (p:Producto {ref: $ref})
        MERGE (u)-[c:COMPRO {pedido_id: $pedido_id}]->(p)
        SET c.oferta_id = $oferta_id, c.fecha = $fecha
    """, uid=user_id, ref=producto_ref, pedido_id=pedido_id,
         oferta_id=oferta_id, fecha=fecha)

# ── Detección de fraude pre-creación ─────────────────────────────────────────

UMBRAL_BOMBARDEO  = 5   # reseñas en 24h sobre el mismo producto
UMBRAL_UNICO_PREV = 2   # reseñas previas del mismo vendedor para disparar la alerta

def _check_bombardeo(s: Session, producto_ref: str) -> bool:
    """True si el producto ya acumula >= UMBRAL reseñas en las últimas 24 horas."""
    row = s.run("""
        MATCH (r:Reseña)-[:SOBRE]->(p:Producto {ref: $ref})
        WHERE r.fecha IS NOT NULL
          AND datetime(r.fecha) >= datetime() - duration({hours: 24})
        RETURN count(r) AS cnt
    """, ref=producto_ref).single()
    return bool(row and row["cnt"] >= UMBRAL_BOMBARDEO)


def _check_reviewer_unico(s: Session, user_id: int, vendedor_id: int) -> bool:
    """True si el usuario ya tiene >= UMBRAL reseñas y todas son del mismo vendedor."""
    row = s.run("""
        MATCH (u:Usuario {id: $uid})-[:ESCRIBIO]->(r:Reseña)-[:PARA_VENDEDOR]->(v:Vendedor)
        WITH count(DISTINCT r) AS total, count(DISTINCT v) AS n_vendors,
             collect(DISTINCT v.id) AS vendor_ids
        WHERE total >= $umbral AND n_vendors = 1 AND $vid IN vendor_ids
        RETURN total
    """, uid=user_id, umbral=UMBRAL_UNICO_PREV, vid=vendedor_id).single()
    return row is not None


def detectar_fraude_creacion(s: Session, user_id: int,
                              producto_ref: str, vendedor_id: int) -> str | None:
    """
    Evalúa si la reseña en curso activa algún patrón de fraude.
    Devuelve la razón como string si hay fraude, None si está limpia.
    """
    if _check_bombardeo(s, producto_ref):
        return "bombardeo"
    if _check_reviewer_unico(s, user_id, vendedor_id):
        return "reviewer_unico_vendedor"
    return None


# ── CRUD de reseñas ────────────────────────────────────────────────────────────

def crear_resena(
    s: Session, *,
    user_id: int, nombre_usuario: str, email_usuario: str,
    producto_ref: str, nombre_producto: str,
    vendedor_id: int, nombre_vendedor: str,
    calificacion: int, texto: str,
) -> dict:
    """Crea una reseña. Verifica compra previa. Retorna el nodo creado."""
    compro = s.run("""
        MATCH (u:Usuario {id: $uid})-[:COMPRO]->(p:Producto {ref: $ref})
        RETURN count(*) AS cnt
    """, uid=user_id, ref=producto_ref).single()["cnt"]

    razon_fraude = detectar_fraude_creacion(s, user_id, producto_ref, vendedor_id)
    estado = "pendiente" if razon_fraude else "aprobada"

    resena_id = str(uuid.uuid4())
    fecha = _utc()

    s.run("""
        MERGE (u:Usuario {id: $uid})
          SET u.nombre = $nombre_u, u.email = $email_u
        MERGE (p:Producto {ref: $ref})
          SET p.nombre = $nombre_p
        MERGE (v:Vendedor {id: $vid})
          SET v.nombre = $nombre_v
        CREATE (r:Reseña {
            id: $rid, calificacion: $cal, texto: $texto,
            fecha: $fecha, estado: $estado, verificada: $verificada,
            imagenes: []
        })
        CREATE (u)-[:ESCRIBIO]->(r)
        CREATE (r)-[:SOBRE]->(p)
        CREATE (r)-[:PARA_VENDEDOR]->(v)
    """,
        uid=user_id, nombre_u=nombre_usuario, email_u=email_usuario,
        ref=producto_ref, nombre_p=nombre_producto,
        vid=vendedor_id, nombre_v=nombre_vendedor,
        rid=resena_id, cal=calificacion, texto=texto,
        fecha=fecha, estado=estado, verificada=bool(compro > 0),
    )
    return {
        "id": resena_id, "calificacion": calificacion, "texto": texto,
        "fecha": fecha, "estado": estado, "verificada": bool(compro > 0),
        "usuario_nombre": nombre_usuario,
        "razon_pendiente": razon_fraude,
    }


def agregar_imagenes_resena(s: Session, resena_id: str, user_id: int, urls: list) -> None:
    s.run("""
        MATCH (u:Usuario {id: $uid})-[:ESCRIBIO]->(r:Reseña {id: $rid})
        SET r.imagenes = coalesce(r.imagenes, []) + $urls
    """, uid=user_id, rid=resena_id, urls=urls)

def listar_resenas(
    s: Session, producto_ref: str,
    solo_aprobadas: bool = True,
    user_id: int | None = None,
) -> list[dict]:
    # Si solo_aprobadas: muestra aprobadas + las propias del usuario (cualquier estado)
    # $uid IS NOT NULL AND u.id = $uid se evalúa como false cuando uid es null → solo aprobadas
    estado_filter = (
        "AND (r.estado = 'aprobada' OR ($uid IS NOT NULL AND u.id = $uid))"
        if solo_aprobadas else ""
    )
    rows = s.run(f"""
        MATCH (u:Usuario)-[:ESCRIBIO]->(r:Reseña)-[:SOBRE]->(p:Producto {{ref: $ref}})
        WHERE 1=1 {estado_filter}
        OPTIONAL MATCH (r)-[:PARA_VENDEDOR]->(v:Vendedor)
        OPTIONAL MATCH (resp:Respuesta)-[:A_RESENA]->(r)
        WITH r, u, v, collect(resp) AS reply_list
        RETURN r.id AS id, r.calificacion AS calificacion, r.texto AS texto,
               r.fecha AS fecha, r.verificada AS verificada, r.estado AS estado,
               u.nombre AS usuario_nombre, u.id AS usuario_id,
               coalesce(r.imagenes, []) AS imagenes,
               v.nombre AS vendedor_nombre, v.id AS vendedor_id,
               [rep IN reply_list WHERE rep IS NOT NULL | {{
                   id: rep.id, texto: rep.texto, fecha: rep.fecha,
                   es_vendedor: rep.es_vendedor, autor_nombre: rep.autor_nombre
               }}] AS respuestas
        ORDER BY r.fecha DESC
    """, ref=producto_ref, uid=user_id).data()
    return rows


def crear_respuesta(
    s: Session, *,
    user_id: int, nombre_usuario: str,
    resena_id: str, texto: str, vendedor_id: int,
) -> dict:
    check = s.run("""
        MATCH (r:Reseña {id: $rid})-[:PARA_VENDEDOR]->(v:Vendedor {id: $vid})
        RETURN v.id AS ok
    """, rid=resena_id, vid=vendedor_id).single()
    if not check:
        raise PermissionError("Solo el vendedor de esta reseña puede responder.")
    resp_id = str(uuid.uuid4())
    fecha = _utc()
    result = s.run("""
        MATCH (u:Usuario {id: $uid}), (r:Reseña {id: $rid})
        CREATE (resp:Respuesta {
            id: $resp_id, texto: $texto, fecha: $fecha,
            es_vendedor: true, autor_nombre: $autor_nombre
        })
        CREATE (u)-[:RESPONDIO]->(resp)-[:A_RESENA]->(r)
        RETURN resp.id AS id
    """, uid=user_id, rid=resena_id, resp_id=resp_id,
         texto=texto, fecha=fecha,
         autor_nombre=nombre_usuario).single()
    if not result:
        raise ValueError("Reseña no encontrada")
    return {
        "id": resp_id, "texto": texto, "fecha": fecha,
        "es_vendedor": True, "autor_nombre": nombre_usuario,
    }

def resumen_calificaciones(s: Session, producto_ref: str) -> dict:
    row = s.run("""
        MATCH (r:Reseña)-[:SOBRE]->(p:Producto {ref: $ref})
        WHERE r.estado = 'aprobada'
        RETURN
            count(r)            AS total,
            avg(r.calificacion) AS promedio,
            collect(r.calificacion) AS todas
    """, ref=producto_ref).single()
    if not row or row["total"] == 0:
        return {"total": 0, "promedio": 0.0, "distribucion": {str(i): 0 for i in range(1, 6)}}
    dist = {str(i): 0 for i in range(1, 6)}
    for c in row["todas"]:
        dist[str(c)] = dist.get(str(c), 0) + 1
    return {
        "total": row["total"],
        "promedio": round(row["promedio"] or 0.0, 2),
        "distribucion": dist,
    }

def moderar_resena(s: Session, resena_id: str, nuevo_estado: str) -> bool:
    result = s.run("""
        MATCH (r:Reseña {id: $rid})
        SET r.estado = $estado
        RETURN r.id AS id
    """, rid=resena_id, estado=nuevo_estado).single()
    return result is not None

def verificar_compra(s: Session, user_id: int, producto_ref: str) -> bool:
    """Retorna True si el usuario tiene al menos una relación :COMPRO con el producto."""
    row = s.run("""
        MATCH (u:Usuario {id: $uid})-[:COMPRO]->(p:Producto {ref: $ref})
        RETURN count(*) AS cnt
    """, uid=user_id, ref=producto_ref).single()
    return (row["cnt"] > 0) if row else False

def ya_reseno(s: Session, user_id: int, producto_ref: str) -> bool:
    row = s.run("""
        MATCH (u:Usuario {id: $uid})-[:ESCRIBIO]->(r:Reseña)-[:SOBRE]->(p:Producto {ref: $ref})
        RETURN count(r) AS cnt
    """, uid=user_id, ref=producto_ref).single()
    return (row["cnt"] > 0) if row else False
