#!/usr/bin/env python3
"""
simulate_fraud.py — Inyecta 4 patrones de fraude pasando por el servicio real.

Patrones:
  1. Bombardeo        — primero 5 reseñas normales; luego 3 más disparan el umbral → pendiente
  2. Sin compra       — 5 cuentas sin :COMPRO (inserción directa, bypasea API igual que un hack)
  3. Reviewer único   — primero 2 reseñas al mismo vendedor; la 3ª+ dispara el umbral → pendiente
  4. Cluster          — 2 grupos de 3 bots reseñan los mismos 4 productos (detección post-hoc)

Uso (desde backend/):
    .\\venv\\Scripts\\python.exe scripts\\simulate_fraud.py
    .\\venv\\Scripts\\python.exe scripts\\simulate_fraud.py --limpiar
"""
import sys, uuid, argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from neo4j import GraphDatabase
from app.core.config import settings
from app.services import review_service as svc

# ── IDs de usuarios falsos (solo Neo4j) ─────────────────────────────────────
BOMBARDEO_BASE_IDS = list(range(9001, 9006))   # 5 reseñas normales (bajo umbral)
BOMBARDEO_FRAUD_IDS = list(range(9006, 9009))  # 3 reseñas → superan umbral → pendiente
SIN_COMPRA_IDS     = list(range(9011, 9016))
UNICO_BASE_IDS     = list(range(9021, 9023))   # 2 reseñas normales (patrón aún no activo)
UNICO_FRAUD_IDS    = list(range(9023, 9026))   # 3 reseñas → reviewer único → pendiente
CLUSTER_A_IDS      = list(range(9031, 9034))
CLUSTER_B_IDS      = list(range(9041, 9044))

ALL_FRAUD_IDS = (
    BOMBARDEO_BASE_IDS + BOMBARDEO_FRAUD_IDS +
    SIN_COMPRA_IDS +
    UNICO_BASE_IDS + UNICO_FRAUD_IDS +
    CLUSTER_A_IDS + CLUSTER_B_IDS
)

# Productos reales de NoseStore (vendedor_id=1)
NOSE_REFS = [
    '6a8dafce3afc5183e9e7ac47',  # Casco ciclismo MTB
    '6a8dafce3afc5183e9e7ac43',  # Balon futbol Nike
    '6a8dafce3afc5183e9e7ac44',  # Mancuernas
    '6a8dafce3afc5183e9e7ac45',  # Colchoneta yoga
    '6a8dafce3afc5183e9e7ac46',  # Gafas natacion
]
NOSE_NOMBRES = [
    'Casco ciclismo MTB Giro Fixture',
    'Balon de futbol Nike Premier League',
    'Mancuernas hexagonales 10kg par',
    'Colchoneta yoga 6mm',
    'Gafas de natacion Speedo Vanquisher',
]

BOMB_REF   = NOSE_REFS[0]
BOMB_VID   = 1
BOMB_VNAME = 'NoseStore'
BOMB_PNAME = NOSE_NOMBRES[0]

CLUSTER_REFS   = NOSE_REFS[:4]
CLUSTER_NOMBRES = NOSE_NOMBRES[:4]

TEXTOS = [
    "Excelente producto, lo recomiendo totalmente, muy buena calidad.",
    "Increible calidad, llego rapido, muy satisfecho con la compra.",
    "Perfecto, exactamente lo que busque, supero expectativas.",
    "Muy buen producto, lo recomiendo a todos, calidad excepcional.",
    "Llego en perfecto estado, funciona genial, 100% recomendado.",
    "Increible relacion calidad-precio, lo mejor del mercado.",
    "Excelente vendedor, producto de primera, ya quiero comprar mas.",
    "Muy satisfecho, producto tal como se describe, envio rapido.",
]


def ts(delta_minutes=0):
    return (datetime.now(timezone.utc) - timedelta(minutes=delta_minutes)).isoformat()


def driver():
    return GraphDatabase.driver(
        settings.NEO4J_URI, auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
    )


# ── Helpers directos (bypasean servicio) ─────────────────────────────────────

def _merge_user(s, uid, nombre, email):
    s.run("MERGE (u:Usuario {id:$id}) SET u.nombre=$n, u.email=$e, u.fraude_sim=true",
          id=uid, n=nombre, e=email)


def _compra(s, uid, ref, pid):
    s.run("MATCH (u:Usuario {id:$uid}), (p:Producto {ref:$ref}) "
          "MERGE (u)-[c:COMPRO {pedido_id:$pid}]->(p) SET c.fecha=$f",
          uid=uid, ref=ref, pid=pid, f=ts())


def _resena_directa(s, uid, ref, vid, texto, cal=5, fecha=None, verificada=True):
    rid = str(uuid.uuid4())
    s.run(
        "MATCH (u:Usuario {id:$uid}), (p:Producto {ref:$ref}), (v:Vendedor {id:$vid}) "
        "CREATE (r:Reseña {id:$rid, calificacion:$cal, texto:$txt, fecha:$fecha, "
        "                  estado:'aprobada', verificada:$ver, imagenes:[], fraude_sim:true}) "
        "CREATE (u)-[:ESCRIBIO]->(r) CREATE (r)-[:SOBRE]->(p) CREATE (r)-[:PARA_VENDEDOR]->(v)",
        uid=uid, ref=ref, vid=vid, rid=rid, cal=cal, txt=texto,
        fecha=fecha or ts(), ver=verificada,
    )
    return rid


# ── Patrones ─────────────────────────────────────────────────────────────────

def simular_bombardeo(s):
    print("\n[1/4] BOMBARDEO")
    print("      Fase A: 5 reseñas normales (bajo umbral de 5) -> aprobadas")
    svc.ensure_producto(s, BOMB_REF, BOMB_PNAME)
    svc.ensure_vendedor(s, BOMB_VID, BOMB_VNAME)

    for i, uid in enumerate(BOMBARDEO_BASE_IDS):
        _merge_user(s, uid, f"UsuNormal{uid}", f"normal{uid}@mail.com")
        _compra(s, uid, BOMB_REF, 89000 + i)
        _resena_directa(s, uid, BOMB_REF, BOMB_VID, TEXTOS[i % len(TEXTOS)], fecha=ts(i))
        print(f"      [base]  UsuNormal{uid} -> aprobada")

    print("      Fase B: 3 reseñas mas -> superan umbral -> pendiente via servicio")
    for i, uid in enumerate(BOMBARDEO_FRAUD_IDS):
        _merge_user(s, uid, f"BotBomba{uid}", f"bot{uid}@spam.com")
        svc.ensure_usuario(s, uid, f"BotBomba{uid}", f"bot{uid}@spam.com")
        _compra(s, uid, BOMB_REF, 89100 + i)
        resultado = svc.crear_resena(
            s,
            user_id=uid,
            nombre_usuario=f"BotBomba{uid}",
            email_usuario=f"bot{uid}@spam.com",
            producto_ref=BOMB_REF,
            nombre_producto=BOMB_PNAME,
            vendedor_id=BOMB_VID,
            nombre_vendedor=BOMB_VNAME,
            calificacion=5,
            texto=TEXTOS[i % len(TEXTOS)],
        )
        estado = resultado['estado']
        razon  = resultado.get('razon_pendiente') or '-'
        marca  = "PENDIENTE" if estado == 'pendiente' else "aprobada"
        print(f"      [fraud] BotBomba{uid} -> {marca}  (razon: {razon})")


def simular_sin_compra(s):
    print("\n[2/4] SIN COMPRA (insercion directa sin :COMPRO, verificada=False)")
    svc.ensure_producto(s, NOSE_REFS[1], NOSE_NOMBRES[1])
    svc.ensure_vendedor(s, 1, 'NoseStore')
    for i, uid in enumerate(SIN_COMPRA_IDS):
        _merge_user(s, uid, f"FakeBuyer{uid}", f"fake{uid}@spam.com")
        _resena_directa(s, uid, NOSE_REFS[1], 1,
                        TEXTOS[i % len(TEXTOS)], verificada=False)
        print(f"      FakeBuyer{uid} -> aprobada (verificada=False, detectable en panel)")


def simular_reviewer_unico(s):
    print("\n[3/4] REVIEWER UNICO VENDEDOR")
    for ref, nombre in zip(NOSE_REFS[:3], NOSE_NOMBRES[:3]):
        svc.ensure_producto(s, ref, nombre)
    svc.ensure_vendedor(s, 1, 'NoseStore')

    print("      Fase A: 2 reseñas al mismo vendedor (patron aun no activo) -> aprobadas")
    for i, uid in enumerate(UNICO_BASE_IDS):
        _merge_user(s, uid, f"UnicoBot{uid}", f"unico{uid}@mail.com")
        svc.ensure_usuario(s, uid, f"UnicoBot{uid}", f"unico{uid}@mail.com")
        for j in range(2):
            ref = NOSE_REFS[j]
            _compra(s, uid, ref, 78000 + i * 10 + j)
            _resena_directa(s, uid, ref, 1, TEXTOS[(i+j) % len(TEXTOS)])
        print(f"      [base]  UnicoBot{uid} -> 2 resenas a NoseStore, aprobadas")

    print("      Fase B: 3 usuarios con 2 resenas previas -> 3a resena via servicio -> pendiente")
    for i, uid in enumerate(UNICO_FRAUD_IDS):
        _merge_user(s, uid, f"UnicoFraud{uid}", f"unico_fraud{uid}@spam.com")
        svc.ensure_usuario(s, uid, f"UnicoFraud{uid}", f"unico_fraud{uid}@spam.com")
        # Crear 2 reseñas directas primero (establece el patron)
        for j in range(2):
            ref = NOSE_REFS[j]
            _compra(s, uid, ref, 78500 + i * 10 + j)
            _resena_directa(s, uid, ref, 1, TEXTOS[(i+j) % len(TEXTOS)])
        # 3a reseña via servicio -> debe detectar reviewer unico
        ref3 = NOSE_REFS[2]
        _compra(s, uid, ref3, 78590 + i)
        resultado = svc.crear_resena(
            s,
            user_id=uid,
            nombre_usuario=f"UnicoFraud{uid}",
            email_usuario=f"unico_fraud{uid}@spam.com",
            producto_ref=ref3,
            nombre_producto=NOSE_NOMBRES[2],
            vendedor_id=1,
            nombre_vendedor='NoseStore',
            calificacion=5,
            texto=TEXTOS[i % len(TEXTOS)],
        )
        estado = resultado['estado']
        razon  = resultado.get('razon_pendiente') or '-'
        marca  = "PENDIENTE" if estado == 'pendiente' else "aprobada"
        print(f"      [fraud] UnicoFraud{uid} -> {marca}  (razon: {razon})")


def simular_cluster(s):
    print("\n[4/4] CLUSTER COORDINADO (deteccion post-hoc, no bloqueada en tiempo real)")
    for ref, nombre in zip(CLUSTER_REFS, CLUSTER_NOMBRES):
        svc.ensure_producto(s, ref, nombre)
    svc.ensure_vendedor(s, 1, 'NoseStore')

    for g_num, grupo_ids in enumerate([CLUSTER_A_IDS, CLUSTER_B_IDS], 1):
        for i, uid in enumerate(grupo_ids):
            _merge_user(s, uid, f"ClusterG{g_num}_{uid}", f"cluster{g_num}{uid}@spam.com")
            for j, ref in enumerate(CLUSTER_REFS):
                _compra(s, uid, ref, 67000 + g_num * 100 + i * 10 + j)
                _resena_directa(s, uid, ref, 1, TEXTOS[(i+j+g_num) % len(TEXTOS)])
        print(f"      Grupo {g_num}: {len(grupo_ids)} bots x {len(CLUSTER_REFS)} productos -> aprobadas")
        print(f"                    (aparecera en panel de fraude como cluster coordinado)")


# ── Limpiar ───────────────────────────────────────────────────────────────────

def limpiar(s):
    print("\nLimpiando simulacion de fraude...")
    r1 = s.run("MATCH (r:Reseña {fraude_sim:true}) DETACH DELETE r RETURN count(*) AS n").single()
    r2 = s.run("MATCH (u:Usuario) WHERE u.id IN $ids DETACH DELETE u RETURN count(*) AS n",
               ids=ALL_FRAUD_IDS).single()
    s.run("MATCH ()-[c:COMPRO]->() WHERE c.pedido_id >= 66000 AND c.pedido_id < 90000 DELETE c")
    print(f"  Resenas eliminadas:       {r1['n']}")
    print(f"  Usuarios falsos borrados: {r2['n']}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--limpiar', action='store_true')
    args = parser.parse_args()

    drv = driver()
    with drv.session() as s:
        if args.limpiar:
            limpiar(s)
        else:
            print("=" * 60)
            print("  SIMULACION DE FRAUDE CON DETECCION EN TIEMPO REAL")
            print("=" * 60)
            simular_bombardeo(s)
            simular_sin_compra(s)
            simular_reviewer_unico(s)
            simular_cluster(s)
            print("\n" + "=" * 60)

    drv.close()


if __name__ == '__main__':
    raise SystemExit(main())
