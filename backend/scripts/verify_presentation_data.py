#!/usr/bin/env python3
"""Auditoría de solo lectura para una instalación DEMO de presentación.

Escribe únicamente un reporte JSON fuera del repositorio. Nunca repara datos.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pymysql
import redis
from cassandra.cluster import Cluster
from elasticsearch import Elasticsearch
from neo4j import GraphDatabase
from pymongo import MongoClient

sys.path.insert(0, str(Path(__file__).resolve().parent))
from seed_demo_large import load_demo_env  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--env-file', type=Path, required=True)
    parser.add_argument('--run-id', required=True)
    args = parser.parse_args()
    cfg = load_demo_env(args.env_file.resolve())
    report: dict = {
        'fecha_utc': datetime.now(timezone.utc).isoformat(),
        'run_id': args.run_id, 'conteos': {}, 'fraude': {},
        'proyecciones': {}, 'errores': [], 'advertencias': [],
    }
    conn = pymysql.connect(
        host=cfg['MYSQL_HOST'], port=int(cfg['MYSQL_PORT']),
        user=cfg['MYSQL_USER'], password=cfg['MYSQL_PASSWORD'],
        database=cfg['MYSQL_DB'], cursorclass=pymysql.cursors.DictCursor,
    )
    try:
        with conn.cursor() as cur:
            for table in ('usuarios', 'vendedores', 'producto_referencias', 'ofertas',
                          'pedidos', 'pagos', 'pedido_lineas', 'resenas',
                          'movimientos_inventario'):
                cur.execute(f'SELECT COUNT(*) n FROM `{table}`')
                report['conteos'][table] = int(cur.fetchone()['n'])
            for table, minimum in {
                'usuarios': 650, 'vendedores': 30, 'producto_referencias': 220,
                'ofertas': 320, 'pedidos': 1600, 'pagos': 1600,
                'resenas': 700, 'movimientos_inventario': 2000,
            }.items():
                if report['conteos'][table] < minimum:
                    report['errores'].append(f'{table}: {report["conteos"][table]} < {minimum}')
            for label, sql in {
                'lineas_sin_pedido': 'SELECT COUNT(*) n FROM pedido_lineas pl LEFT JOIN pedidos p ON p.id=pl.pedido_id WHERE p.id IS NULL',
                'pagos_sin_pedido': 'SELECT COUNT(*) n FROM pagos pa LEFT JOIN pedidos p ON p.id=pa.pedido_id WHERE p.id IS NULL',
                'lineas_vendedor_incorrecto': '''SELECT COUNT(*) n FROM pedido_lineas pl
                    JOIN pedido_vendedores pv ON pv.id=pl.pedido_vendedor_id
                    JOIN ofertas o ON o.id=pl.oferta_id
                    WHERE pv.pedido_id<>pl.pedido_id OR pv.vendedor_id<>o.vendedor_id''',
                'inventario_negativo': 'SELECT COUNT(*) n FROM inventario WHERE cantidad_disponible<0 OR cantidad_reservada<0',
                'ofertas_sin_inventario': 'SELECT COUNT(*) n FROM ofertas o LEFT JOIN inventario i ON i.oferta_id=o.id WHERE i.id IS NULL',
                'subtotales_inconsistentes': '''SELECT COUNT(*) n FROM pedidos p
                    JOIN (SELECT pedido_id,SUM(subtotal_linea) total FROM pedido_lineas GROUP BY pedido_id) x ON x.pedido_id=p.id
                    WHERE ABS(p.subtotal-x.total)>0.01''',
            }.items():
                cur.execute(sql)
                count = int(cur.fetchone()['n'])
                report['conteos'][label] = count
                if count: report['errores'].append(f'{label}: {count}')
            cur.execute('SELECT estado,COUNT(*) n FROM pedidos GROUP BY estado')
            report['conteos']['pedidos_por_estado'] = {r['estado']: r['n'] for r in cur.fetchall()}
            cur.execute('SELECT estado,metodo_pago_id,COUNT(*) n FROM pagos GROUP BY estado,metodo_pago_id')
            report['conteos']['pagos_por_estado_metodo'] = [dict(r) for r in cur.fetchall()]
            cur.execute('SELECT verificada_compra,COUNT(*) n FROM resenas GROUP BY verificada_compra')
            report['conteos']['resenas_por_verificacion'] = {str(r['verificada_compra']): r['n'] for r in cur.fetchall()}
            cur.execute('''SELECT COUNT(*) n FROM pedido_lineas pl JOIN pedidos p ON p.id=pl.pedido_id
                WHERE EXISTS (SELECT 1 FROM pagos pa WHERE pa.pedido_id=p.id
                  AND pa.estado IN ('aprobado','reembolsado'))
                AND (p.estado<>'cancelado' OR EXISTS (SELECT 1 FROM pagos pr
                  WHERE pr.pedido_id=p.id AND pr.estado='reembolsado'))''')
            cassandra_lines = int(cur.fetchone()['n'])
            cur.execute('''SELECT COUNT(*) n FROM pedido_lineas pl JOIN pedidos p ON p.id=pl.pedido_id
                WHERE p.estado NOT IN ('cancelado','reembolsado')
                AND EXISTS (SELECT 1 FROM pagos pa WHERE pa.pedido_id=p.id AND pa.estado='aprobado')''')
            neo4j_lines = int(cur.fetchone()['n'])
            report['conteos']['lineas_analitica_elegibles'] = cassandra_lines
            report['conteos']['lineas_compra_neo4j_elegibles'] = neo4j_lines
            cur.execute('SELECT tipo,COUNT(*) n FROM alertas_fraude WHERE activa=1 GROUP BY tipo')
            alerts = {r['tipo']: int(r['n']) for r in cur.fetchall()}
            for key, name in (('F05','autocompra'), ('F06','inventario_atipico'),
                              ('F07','coincidencia_cantidad')):
                cur.execute('SELECT id,oferta_id FROM alertas_fraude WHERE activa=1 AND tipo=%s ORDER BY id LIMIT 10', (name,))
                examples = [dict(r) for r in cur.fetchall()]
                report['fraude'][key] = {'total': alerts.get(name, 0), 'ejemplos': examples}
                if alerts.get(name, 0) < 5:
                    report['errores'].append(f'{key}: {alerts.get(name, 0)} < 5')
            cur.execute('SELECT COUNT(*) n FROM resenas WHERE verificada_compra=0 AND estado_moderacion IN (\'pendiente\',\'aprobada\')')
            f04 = int(cur.fetchone()['n'])
            report['fraude']['F04'] = {'total': f04}
            if f04 < 20: report['errores'].append(f'F04: {f04} < 20')
        with GraphDatabase.driver(cfg['NEO4J_URI'], auth=(cfg['NEO4J_USER'], cfg['NEO4J_PASSWORD'])).session() as neo:
            rules = {
                'F01': '''MATCH (u:Usuario)-[:ESCRIBIO]->(r:Reseña)-[:SOBRE]->(p:Producto)
                    WHERE r.verificada=true AND r.estado='aprobada' AND datetime(r.fecha)>=datetime()-duration({hours:24})
                    WITH p,count(DISTINCT r) n WHERE n>=5 RETURN p.ref ref,n LIMIT 10''',
                'F02': '''MATCH (u:Usuario)-[:ESCRIBIO]->(r:Reseña)-[:CALIFICA_A]->(v:Vendedor)
                    WHERE r.verificada=true AND r.estado='aprobada'
                    WITH u,count(DISTINCT r) n,count(DISTINCT v) sellers
                    WHERE n>=3 AND sellers=1 RETURN u.id ref,n LIMIT 10''',
                'F03': '''MATCH (u1:Usuario)-[:ESCRIBIO]->(r1:Reseña)-[:SOBRE]->(p:Producto)<-[:SOBRE]-(r2:Reseña)<-[:ESCRIBIO]-(u2:Usuario)
                    WHERE u1.id<u2.id AND r1.verificada=true AND r2.verificada=true
                      AND r1.estado='aprobada' AND r2.estado='aprobada'
                    WITH u1,u2,count(DISTINCT p) n WHERE n>=3
                    RETURN toString(u1.id)+'-'+toString(u2.id) ref,n LIMIT 15''',
            }
            for key, cypher in rules.items():
                rows = [dict(r) for r in neo.run(cypher)]
                report['fraude'][key] = {'total': len(rows), 'ejemplos': rows}
                if len(rows) < {'F01':5,'F02':5,'F03':10}[key]:
                    report['errores'].append(f'{key}: {len(rows)} bajo el mínimo')
            report['proyecciones']['neo4j_compras'] = neo.run('MATCH (c:Compra) RETURN count(c) n').single()['n']
            if report['proyecciones']['neo4j_compras'] != neo4j_lines:
                report['errores'].append('Neo4j Compra no coincide con líneas pagadas elegibles')
        with MongoClient(cfg['MONGO_URI'], serverSelectionTimeoutMS=5000) as mongo:
            report['proyecciones']['mongo_productos'] = mongo[cfg['MONGO_DB']].productos.count_documents({})
        with Elasticsearch(cfg['ES_URL']) as es:
            report['proyecciones']['elasticsearch_documentos'] = es.count(index=cfg['ES_INDEX_ALIAS'])['count']
        if report['proyecciones']['mongo_productos'] != report['proyecciones']['elasticsearch_documentos']:
            report['advertencias'].append('Conteos MongoDB/Elasticsearch diferentes; revisar estados e índice')
        r = redis.Redis(host=cfg['REDIS_HOST'], port=int(cfg['REDIS_PORT']), socket_timeout=3)
        report['proyecciones']['redis_ping'] = bool(r.ping())
        cluster = Cluster([cfg['CASSANDRA_HOST']], port=int(cfg['CASSANDRA_PORT']))
        try:
            cass = cluster.connect(cfg['CASSANDRA_KEYSPACE'])
            report['proyecciones']['cassandra_lineas'] = cass.execute('SELECT COUNT(*) FROM ventas_producto_semana').one()[0]
        finally:
            cluster.shutdown()
        if report['proyecciones']['cassandra_lineas'] != cassandra_lines:
            report['errores'].append('Cassandra no coincide con líneas pagadas elegibles')
    finally:
        conn.close()
    report['resultado'] = 'OK' if not report['errores'] else 'ERROR'
    output = Path(__file__).resolve().parents[3] / '_runtime' / 'tiendaya-demo' / 'reporte-presentacion.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, default=str, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(report, indent=2, default=str, ensure_ascii=False))
    print(f'Reporte local fuera de Git: {output}')
    return 0 if not report['errores'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
