#!/usr/bin/env python3
"""
Verifica que el setup esté completo y que no haya referencias huérfanas
entre MySQL y MongoDB (pedido_lineas → productos).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import pymysql
from pymongo import MongoClient
from bson import ObjectId
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

MYSQL_HOST  = os.getenv('MYSQL_HOST', 'localhost')
MYSQL_PORT  = int(os.getenv('MYSQL_PORT', 3306))
MYSQL_DB    = os.getenv('MYSQL_DB', 'tiendaya')
MYSQL_USER  = os.getenv('MYSQL_USER', 'tiendaya')
MYSQL_PASS  = os.getenv('MYSQL_PASSWORD', 'tiendaya123')
MONGO_URI   = os.getenv('MONGO_URI', 'mongodb://admin:adminpassword@localhost:27017/tiendaya?authSource=admin')
MONGO_DB    = os.getenv('MONGO_DB', 'tiendaya')


def main():
    ok = True

    # ── MySQL ─────────────────────────────────────────────────────────────────
    try:
        conn = pymysql.connect(host=MYSQL_HOST, port=MYSQL_PORT, db=MYSQL_DB,
                               user=MYSQL_USER, password=MYSQL_PASS,
                               charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor)
        with conn.cursor() as cur:
            cur.execute('SELECT COUNT(*) AS n FROM usuarios')
            print(f'MySQL usuarios: {cur.fetchone()["n"]}')
            cur.execute('SELECT COUNT(*) AS n FROM productos')
            n_productos_mysql = cur.fetchone()['n']
            print(f'MySQL productos: {n_productos_mysql}')
            cur.execute('SELECT COUNT(*) AS n FROM pedidos')
            print(f'MySQL pedidos:   {cur.fetchone()["n"]}')

            # Referencias huérfanas: pedido_lineas con producto_ref que no existe en Mongo
            cur.execute("SELECT id, producto_ref FROM pedido_lineas WHERE producto_ref IS NOT NULL")
            refs = cur.fetchall()
        conn.close()
        print(f'MySQL: OK')
    except Exception as e:
        print(f'MySQL: ERROR — {e}')
        ok = False
        refs = []

    # ── MongoDB ───────────────────────────────────────────────────────────────
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        client.server_info()
        mongo = client[MONGO_DB]
        n_mongo = mongo.productos.count_documents({})
        n_eventos = mongo.producto_eventos.count_documents({})
        print(f'MongoDB productos: {n_mongo}')
        print(f'MongoDB eventos:   {n_eventos}')

        # Verificar referencias huérfanas
        huerfanas = []
        for ref in refs:
            ref_id = ref['producto_ref']
            try:
                if not mongo.productos.find_one({'_id': ObjectId(ref_id)}):
                    huerfanas.append(ref)
            except Exception:
                huerfanas.append(ref)

        if huerfanas:
            print(f'\n⚠ Referencias huérfanas en pedido_lineas ({len(huerfanas)}):')
            for h in huerfanas:
                print(f'  linea_id={h["id"]} producto_ref={h["producto_ref"]}')
            ok = False
        else:
            print(f'Integridad referencial MySQL<->MongoDB: OK (0 huerfanas)')

        client.close()
    except Exception as e:
        print(f'MongoDB: ERROR - {e}')
        ok = False

    print(f'\n{"[OK] Setup completo." if ok else "[ERROR] Hay problemas que corregir."}')
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
