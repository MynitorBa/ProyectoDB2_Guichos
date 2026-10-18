"""Proyección reconstruible de compras, ofertas y reseñas hacia Neo4j."""
from __future__ import annotations
from neo4j import Session

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

    Los valores son snapshots históricos de MySQL. El modelo definitivo usa
    exclusivamente ``REALIZO -> Compra -> DE_PRODUCTO/A_VENDEDOR``.
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
