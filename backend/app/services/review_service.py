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
                     pedido_id: int, oferta_id: int, fecha: str,
                     *, linea_id: int, vendedor_id: int,
                     cantidad: int | None = None,
                     precio_unitario: float | None = None,
                     sku: str | None = None,
                     promocion_flash_id: int | None = None) -> None:
    """Proyecta una línea pagada como nodo ``Compra`` idempotente.

    Los valores son snapshots históricos de MySQL. ``COMPRO`` se mantiene
    temporalmente durante la transición, pero las consultas nuevas usan
    ``REALIZO -> Compra -> DE_PRODUCTO/A_VENDEDOR``.
    """
    s.run("""
        MATCH (u:Usuario {id: $uid}), (p:Producto {ref: $ref}),
              (v:Vendedor {id: $vendedor_id})
        MERGE (c:Compra {linea_id: $linea_id})
        SET c.pedido_id = $pedido_id, c.oferta_id = $oferta_id,
            c.producto_ref = $ref, c.vendedor_id = $vendedor_id,
            c.fecha = $fecha, c.cantidad = $cantidad,
            c.precio_unitario = $precio_unitario, c.sku = $sku,
            c.promocion_flash_id = $promocion_flash_id,
            c.pagada = true
        MERGE (u)-[:REALIZO]->(c)
        MERGE (c)-[:DE_PRODUCTO]->(p)
        MERGE (c)-[:A_VENDEDOR]->(v)
        MERGE (u)-[legacy:COMPRO {linea_id: $linea_id}]->(p)
        SET legacy.pedido_id = $pedido_id, legacy.oferta_id = $oferta_id,
            legacy.vendedor_id = $vendedor_id, legacy.fecha = $fecha
    """, uid=user_id, ref=producto_ref, pedido_id=pedido_id,
         oferta_id=oferta_id, fecha=fecha, linea_id=linea_id,
         vendedor_id=vendedor_id, cantidad=cantidad,
         precio_unitario=precio_unitario, sku=sku,
         promocion_flash_id=promocion_flash_id)


def proyectar_oferta(
    s: Session, *, vendedor_id: int, vendedor_nombre: str,
    vendedor_usuario_id: int, producto_ref: str, oferta_id: int,
    producto_variante_id: int, variante_ref: str, sku: str, estado: str,
) -> None:
    """Representa la oferta como relación, no como réplica de MySQL."""
    # Si la oferta cambió de vendedor, elimina únicamente su relación de
    # proyección anterior. MySQL continúa siendo la autoridad del cambio.
    s.run(
        "MATCH ()-[o:OFRECE {oferta_id:$oferta_id}]->() DELETE o",
        oferta_id=oferta_id,
    )
    s.run("""
        MERGE (u:Usuario {id:$usuario_id})
        MERGE (v:Vendedor {id:$vendedor_id}) SET v.nombre=$vendedor_nombre
        MERGE (p:Producto {ref:$producto_ref})
        MERGE (u)-[:GESTIONA]->(v)
        CREATE (v)-[o:OFRECE {oferta_id:$oferta_id}]->(p)
        SET o.producto_variante_id=$producto_variante_id,
            o.variante_ref=$variante_ref, o.sku=$sku, o.estado=$estado
    """, usuario_id=vendedor_usuario_id, vendedor_id=vendedor_id,
         vendedor_nombre=vendedor_nombre, producto_ref=producto_ref,
         oferta_id=oferta_id, producto_variante_id=producto_variante_id,
         variante_ref=variante_ref, sku=sku, estado=estado)


def proyectar_resena_mysql(s: Session, db, resena_id: int) -> None:
    """Reconstruye una reseña y sus hijos desde la autoridad MySQL."""
    from app.models.producto_referencia import ProductoReferencia
    from app.models.resena import Resena, ResenaImagen, ResenaRespuesta
    from app.models.usuario import Usuario
    from app.models.vendedor import Vendedor

    review = db.get(Resena, resena_id)
    if not review:
        return
    user = db.get(Usuario, review.usuario_id)
    product = db.get(ProductoReferencia, review.producto_referencia_id)
    seller = db.get(Vendedor, review.vendedor_id) if review.vendedor_id else None
    images = db.query(ResenaImagen).filter(
        ResenaImagen.resena_id == review.id
    ).order_by(ResenaImagen.orden, ResenaImagen.id).all()
    replies = db.query(ResenaRespuesta).filter(
        ResenaRespuesta.resena_id == review.id,
        ResenaRespuesta.activa.is_(True),
    ).all()
    s.run("""
        MERGE (u:Usuario {id: $uid})
          SET u.nombre=$usuario_nombre, u.email=$email
        MERGE (p:Producto {ref: $ref})
        MERGE (r:Reseña {id: $rid})
          SET r.mysql_id=$mysql_id, r.calificacion=$calificacion,
              r.texto=$texto, r.fecha=$fecha, r.estado=$estado,
              r.verificada=$verificada, r.imagenes=$imagenes,
              r.version=$version
        MERGE (u)-[:ESCRIBIO]->(r)
        MERGE (r)-[:SOBRE]->(p)
    """, uid=user.id, usuario_nombre=f'{user.nombre} {user.apellido}'.strip(),
         email=user.email, ref=product.producto_ref, rid=review.public_id,
         mysql_id=review.id, calificacion=review.calificacion,
         texto=review.comentario or '', fecha=review.fecha.isoformat(),
         estado=review.estado_moderacion, verificada=bool(review.verificada_compra),
         imagenes=[img.url for img in images], version=review.version)
    s.run("MATCH (r:Reseña {id:$rid})-[x:PARA_VENDEDOR|CALIFICA_A]->() DELETE x", rid=review.public_id)
    if seller:
        s.run("""
            MATCH (r:Reseña {id:$rid})
            MERGE (v:Vendedor {id:$vid}) SET v.nombre=$nombre
            MERGE (r)-[:CALIFICA_A]->(v)
        """, rid=review.public_id, vid=seller.id, nombre=seller.nombre_comercial)
    s.run("MATCH (r:Reseña {id:$rid})-[x:BASADA_EN]->() DELETE x", rid=review.public_id)
    if review.verificada_compra and review.pedido_linea_id:
        s.run("""
            MATCH (r:Reseña {id:$rid}), (c:Compra {linea_id:$linea_id})
            MERGE (r)-[:BASADA_EN]->(c)
        """, rid=review.public_id, linea_id=review.pedido_linea_id)
    # Las respuestas son hijas reconstruibles de la reseña. Limpiar solamente
    # esta proyección evita dejar respuestas desactivadas como si siguieran
    # públicas y no afecta el registro durable de MySQL.
    s.run("""
        MATCH (resp:Respuesta)-[:A_RESENA]->(:Reseña {id:$rid})
        DETACH DELETE resp
    """, rid=review.public_id)
    for reply in replies:
        author = db.get(Usuario, reply.usuario_id)
        s.run("""
            MATCH (r:Reseña {id:$rid})
            MERGE (u:Usuario {id:$uid})
              SET u.nombre=$nombre, u.email=$email
            MERGE (resp:Respuesta {id:$reply_id})
              SET resp.texto=$texto, resp.fecha=$fecha,
                  resp.es_vendedor=true, resp.autor_nombre=$nombre
            MERGE (u)-[:RESPONDIO]->(resp)
            MERGE (resp)-[:A_RESENA]->(r)
        """, rid=review.public_id, uid=author.id,
             nombre=f'{author.nombre} {author.apellido}'.strip(), email=author.email,
             reply_id=reply.public_id, texto=reply.texto,
             fecha=reply.fecha_creacion.isoformat())

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
        MATCH (u:Usuario {id: $uid})-[:ESCRIBIO]->(r:Reseña)-[:CALIFICA_A]->(v:Vendedor)
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
        CREATE (r)-[:CALIFICA_A]->(v)
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
        OPTIONAL MATCH (r)-[:CALIFICA_A]->(v:Vendedor)
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
        MATCH (r:Reseña {id: $rid})-[:CALIFICA_A]->(v:Vendedor {id: $vid})
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

def producto_de_resena(s: Session, resena_id: str) -> str | None:
    row = s.run(
        "MATCH (:Reseña {id: $rid})-[:SOBRE]->(p:Producto) RETURN p.ref AS ref",
        rid=resena_id,
    ).single()
    return row["ref"] if row else None

def verificar_compra(s: Session, user_id: int, producto_ref: str) -> bool:
    """Retorna True si el usuario tiene al menos una relación :COMPRO con el producto."""
    row = s.run("""
        MATCH (u:Usuario {id: $uid})-[:COMPRO]->(p:Producto {ref: $ref})
        RETURN count(*) AS cnt
    """, uid=user_id, ref=producto_ref).single()
    return (row["cnt"] > 0) if row else False


def verificar_compra_vendedor(
    s: Session, user_id: int, producto_ref: str, vendedor_id: int,
) -> bool:
    """Comprueba que el usuario compró ese producto a ese vendedor concreto."""
    row = s.run("""
        MATCH (u:Usuario {id: $uid})-[c:COMPRO]->(p:Producto {ref: $ref})
        WHERE c.vendedor_id = $vid
        RETURN count(c) AS cnt
    """, uid=user_id, ref=producto_ref, vid=vendedor_id).single()
    return (row["cnt"] > 0) if row else False

def ya_reseno(s: Session, user_id: int, producto_ref: str) -> bool:
    row = s.run("""
        MATCH (u:Usuario {id: $uid})-[:ESCRIBIO]->(r:Reseña)-[:SOBRE]->(p:Producto {ref: $ref})
        RETURN count(r) AS cnt
    """, uid=user_id, ref=producto_ref).single()
    return (row["cnt"] > 0) if row else False
