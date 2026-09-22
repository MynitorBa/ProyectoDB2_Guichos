#!/usr/bin/env python3
"""
seed_reviews.py — Genera compras y reseñas realistas en Neo4j.

Uso (desde backend/):
    .\\venv\\Scripts\\python.exe scripts\\seed_reviews.py
"""
import sys, os, random, uuid
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Permite importar app.core sin instalar el paquete
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, text
from pymongo import MongoClient
from bson import ObjectId
from neo4j import GraphDatabase

from app.core.config import settings

# ── Banco de textos de reseñas ────────────────────────────────────────────────

TEXTOS = {
    5: [
        "Producto excelente, superó todas mis expectativas. La calidad es increíble y llegó perfectamente empacado.",
        "¡Simplemente perfecto! Exactamente lo que buscaba. Calidad de primera y precio muy justo. Volvería a comprar.",
        "Extraordinaria calidad, se nota la fabricación cuidadosa. El vendedor fue muy atento y el envío llegó rápido.",
        "Muy satisfecho con esta compra. El producto es tal como se describe, robusto y de excelente acabado.",
        "Uno de los mejores productos que he comprado en línea. Llegó en perfectas condiciones y funciona de maravilla.",
        "Calidad excepcional, se nota la diferencia respecto a otras marcas. Vale cada centavo que pagué.",
        "Me encantó el producto. Entrega rapidísima y empaque muy cuidado. Sin duda volvería a comprar.",
        "Producto de alta calidad, resistente y con excelente acabado. El servicio del vendedor fue impecable.",
        "Todo perfecto desde el primer momento. El producto llegó antes de lo esperado y funcionó a la primera.",
        "Superó mis expectativas en cada aspecto. Lo recomiendo a cualquiera que esté buscando calidad real.",
    ],
    4: [
        "Muy buen producto en general. Cumple con lo que promete y tiene buena calidad. Recomendado.",
        "Buena compra, estoy satisfecho. La calidad es muy buena para el precio que tiene.",
        "El producto llegó en buenas condiciones y funciona perfectamente. Pequeña diferencia con las fotos pero nada importante.",
        "Buen producto, la calidad es la esperada. El envío tardó un día más pero el resultado valió la espera.",
        "Bastante bueno para el precio. La construcción es sólida y cumple su función a la perfección.",
        "Muy buena relación calidad-precio. Algún detalle de acabado mejorable pero en general muy satisfecho.",
        "Producto como se describe, buena calidad. El vendedor respondió mis dudas rápidamente.",
        "Me gustó mucho. Está bien hecho, los materiales son de calidad. Llegó antes de lo esperado.",
        "Gran producto por el precio. Fácil de usar y muy bien construido. Se lo recomendaré a mi familia.",
        "Muy contento con la compra. El producto cumple exactamente lo que promete y la atención fue excelente.",
    ],
    3: [
        "Producto correcto, hace lo que se necesita. Nada espectacular pero cumple su función.",
        "Aceptable para el precio. Esperaba un poco más de calidad pero en general funciona bien.",
        "El producto es lo que se muestra, sin sorpresas. La entrega fue puntual. Podría mejorar el acabado.",
        "Cumple su función básica. Para uso ocasional es suficiente, para uso intensivo buscaría algo mejor.",
        "Producto estándar. No es lo más sofisticado pero hace lo que dice que hace. Precio justo.",
    ],
}

WEIGHTS = [5, 5, 4, 4, 4, 3]  # distribución: predominan 4 y 5 estrellas


def rand_rating() -> int:
    return random.choice(WEIGHTS)


def rand_text(rating: int) -> str:
    return random.choice(TEXTOS[rating])


def rand_fecha() -> str:
    """Fecha aleatoria en los últimos 5 meses."""
    delta = timedelta(days=random.randint(1, 150))
    dt = datetime.now(timezone.utc) - delta
    return dt.isoformat()


# ── Conexiones ────────────────────────────────────────────────────────────────

def get_engine():
    return create_engine(settings.mysql_url, pool_pre_ping=True)


def get_mongo():
    client = MongoClient(settings.MONGO_URI)
    return client[settings.MONGO_DB]


def get_driver():
    return GraphDatabase.driver(
        settings.NEO4J_URI,
        auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
    )


# ── Lógica Neo4j ──────────────────────────────────────────────────────────────

def ya_reseno(s, user_id: int, producto_ref: str) -> bool:
    row = s.run(
        "MATCH (u:Usuario {id:$uid})-[:ESCRIBIO]->(r:Reseña)-[:SOBRE]->(p:Producto {ref:$ref}) "
        "RETURN count(r) AS cnt",
        uid=user_id, ref=producto_ref,
    ).single()
    return bool(row and row["cnt"] > 0)


def registrar_compra(s, user_id, producto_ref, pedido_id, oferta_id, fecha):
    s.run(
        "MATCH (u:Usuario {id:$uid}), (p:Producto {ref:$ref}) "
        "MERGE (u)-[c:COMPRO {pedido_id:$pid}]->(p) "
        "SET c.oferta_id=$oid, c.fecha=$fecha",
        uid=user_id, ref=producto_ref, pid=pedido_id, oid=oferta_id, fecha=fecha,
    )


def crear_resena(s, user_id, producto_ref, vendedor_id, rating, texto, fecha):
    rid = str(uuid.uuid4())
    s.run(
        "MATCH (u:Usuario {id:$uid}), (p:Producto {ref:$ref}), (v:Vendedor {id:$vid}) "
        "CREATE (r:Reseña {id:$rid, calificacion:$cal, texto:$txt, fecha:$fecha, "
        "               estado:'aprobada', verificada:true, imagenes:[]}) "
        "CREATE (u)-[:ESCRIBIO]->(r) "
        "CREATE (r)-[:SOBRE]->(p) "
        "CREATE (r)-[:PARA_VENDEDOR]->(v)",
        uid=user_id, ref=producto_ref, vid=vendedor_id,
        rid=rid, cal=rating, txt=texto, fecha=fecha,
    )
    return rid


def merge_nodes(s, users, productos_map, vendors_map):
    for u in users:
        s.run(
            "MERGE (u:Usuario {id:$id}) SET u.nombre=$nombre, u.email=$email",
            id=u["id"], nombre=u["nombre"], email=u["email"],
        )
    for ref, nombre in productos_map.items():
        s.run(
            "MERGE (p:Producto {ref:$ref}) SET p.nombre=$nombre",
            ref=ref, nombre=nombre,
        )
    for vid, nombre in vendors_map.items():
        s.run(
            "MERGE (v:Vendedor {id:$id}) SET v.nombre=$nombre",
            id=vid, nombre=nombre,
        )


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("🔗 Conectando a MySQL...")
    engine = get_engine()

    with engine.connect() as conn:
        # Todos los usuarios activos (cualquier rol)
        rows = conn.execute(text(
            "SELECT id, nombre, apellido, email FROM usuarios WHERE estado='activo' LIMIT 20"
        )).fetchall()
        users = [{"id": r[0], "nombre": f"{r[1]} {r[2]}".strip(), "email": r[3]} for r in rows]

        # Ofertas activas con producto_ref (una por producto+vendedor)
        rows = conn.execute(text(
            "SELECT MIN(o.id), o.producto_ref, o.vendedor_id, MIN(o.sku), MIN(v.nombre_comercial) "
            "FROM ofertas o "
            "JOIN vendedores v ON o.vendedor_id = v.id "
            "WHERE o.estado='activa' AND o.producto_ref IS NOT NULL "
            "GROUP BY o.producto_ref, o.vendedor_id "
            "LIMIT 50"
        )).fetchall()
        ofertas = [
            {"id": r[0], "ref": r[1], "vid": r[2], "sku": r[3], "vendedor": r[4]}
            for r in rows
        ]

    if not users:
        print("❌  No hay usuarios activos en MySQL. Ejecuta primero el seed base.")
        return 1
    if not ofertas:
        print("❌  No hay ofertas activas con producto_ref.")
        return 1

    print(f"   👤 {len(users)} usuarios  |  📦 {len(ofertas)} ofertas")

    # Nombres de producto desde MongoDB
    print("🔗 Conectando a MongoDB...")
    mongo_db = get_mongo()
    productos_map: dict[str, str] = {}
    vendors_map: dict[int, str] = {}

    for o in ofertas:
        if o["ref"] not in productos_map:
            try:
                doc = mongo_db.productos.find_one({"_id": ObjectId(o["ref"])}, {"nombre": 1})
                productos_map[o["ref"]] = (doc["nombre"] if doc and doc.get("nombre") else o["sku"])
            except Exception:
                productos_map[o["ref"]] = o["sku"]
        vendors_map[o["vid"]] = o["vendedor"]

    print(f"   🏷  {len(productos_map)} productos distintos")

    # Neo4j
    print("🔗 Conectando a Neo4j...")
    driver = get_driver()
    total = 0
    skipped = 0

    with driver.session() as s:
        print("   ⚙️  Sincronizando nodos base...")
        merge_nodes(s, users, productos_map, vendors_map)

        for oferta in ofertas:
            ref   = oferta["ref"]
            vid   = oferta["vid"]
            nombre_prod = productos_map[ref]
            # 3 a 5 usuarios distintos por producto
            n_rev = random.randint(3, min(5, len(users)))
            reviewers = random.sample(users, n_rev)
            pid_base = 80000 + random.randint(100, 9999)

            for i, user in enumerate(reviewers):
                if ya_reseno(s, user["id"], ref):
                    skipped += 1
                    continue

                fecha = rand_fecha()
                registrar_compra(s, user["id"], ref, pid_base + i, oferta["id"], fecha)

                rating = rand_rating()
                texto  = rand_text(rating)
                crear_resena(s, user["id"], ref, vid, rating, texto, fecha)

                stars = "★" * rating + "☆" * (5 - rating)
                print(f"   {stars}  {user['nombre'][:22]:<22} → {nombre_prod[:38]}")
                total += 1

    driver.close()

    print()
    print(f"✅  {total} reseñas creadas  |  {skipped} ya existían — ¡listo!")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
