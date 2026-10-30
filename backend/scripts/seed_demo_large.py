#!/usr/bin/env python3
"""Generador reproducible de carga para el entorno aislado TiendaYa DEMO.

Nunca usa ``backend/.env``. Exige un archivo DEMO explícito, valida nombres y
puertos, y rechaza los endpoints de la instancia principal antes de abrir una
conexión. La carga por lotes crea datos coherentes en MySQL y documentos de
catálogo en MongoDB; las demás proyecciones se reconstruyen con los scripts
oficiales usando el mismo entorno DEMO.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import subprocess
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pymysql
from bson import ObjectId
from dotenv import dotenv_values
from pymongo import MongoClient, ReplaceOne


BACKEND_DIR = Path(__file__).resolve().parents[1]
ROOT = BACKEND_DIR.parent
PASSWORD_HASH = '$2b$12$m4eWOlabkSnzoaioHQMc0Oa/pzArcAD.Mn0O1sq2L5DaoYqF7IZru'
NAMESPACE = uuid.UUID('ba93f2bd-841e-4dfc-83fc-c7f9330c51fe')
PRODUCT_KINDS = (
    'Laptop', 'Teléfono', 'Audífonos', 'Camisa', 'Pantalón', 'Zapatos',
    'Lámpara', 'Libro', 'Balón', 'Café', 'Juego', 'Taladro',
)


def demo_product_name(index: int) -> str:
    return f'{PRODUCT_KINDS[index % len(PRODUCT_KINDS)]} DEMO modelo {index:04d}'


@dataclass(frozen=True)
class Scale:
    users: int
    sellers: int
    products: int
    offers: int
    orders: int
    lines: int
    reviews: int


SCALES = {
    'small': Scale(80, 8, 40, 60, 180, 270, 80),
    'medium': Scale(650, 30, 220, 320, 1600, 2400, 700),
    'full': Scale(3000, 100, 800, 1000, 8000, 12000, 3000),
}


def load_demo_env(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise SystemExit(f'No existe el archivo DEMO: {path}')
    values = {k: str(v) for k, v in dotenv_values(path).items() if v is not None}
    # El instalador corre la carga con la cuenta de administración de MongoDB de la DEMO
    # (control de acceso). Variable propia del instalador: un MONGO_URI cualquiera del entorno
    # podría ser el de PRINCIPAL. Las comprobaciones de abajo se aplican igual.
    if os.environ.get('DEMO_MONGO_URI_INSTALACION'):
        values['MONGO_URI'] = os.environ['DEMO_MONGO_URI_INSTALACION']
    required = {
        'TIENDAYA_DEMO', 'MYSQL_HOST', 'MYSQL_PORT', 'MYSQL_DB', 'MYSQL_USER',
        'MYSQL_PASSWORD', 'MONGO_URI', 'MONGO_DB', 'REDIS_PORT',
        'CASSANDRA_PORT', 'CASSANDRA_KEYSPACE', 'NEO4J_URI', 'ES_URL',
        'ES_INDEX_ALIAS',
    }
    missing = sorted(required - values.keys())
    if missing:
        raise SystemExit(f'Variables DEMO faltantes: {", ".join(missing)}')
    checks = [
        (values['TIENDAYA_DEMO'].lower() == 'true', 'TIENDAYA_DEMO debe ser true'),
        (values['MYSQL_DB'].endswith('_demo'), 'MYSQL_DB debe terminar en _demo'),
        (values['MONGO_DB'].endswith('_demo'), 'MONGO_DB debe terminar en _demo'),
        (values['CASSANDRA_KEYSPACE'].endswith('_demo'), 'Cassandra debe usar keyspace _demo'),
        ('demo' in values['ES_INDEX_ALIAS'].lower(), 'El alias Elasticsearch debe contener demo'),
        (int(values['MYSQL_PORT']) != 3307, 'Se rechazó el puerto MySQL principal 3307'),
        (int(values['REDIS_PORT']) != 6379, 'Se rechazó el puerto Redis principal 6379'),
        (int(values['CASSANDRA_PORT']) != 9042, 'Se rechazó el puerto Cassandra principal 9042'),
        ('7687' not in values['NEO4J_URI'], 'Se rechazó el puerto Neo4j principal 7687'),
        (':9200' not in values['ES_URL'], 'Se rechazó el puerto Elasticsearch principal 9200'),
        ('27017' not in values['MONGO_URI'], 'Se rechazó el puerto MongoDB principal 27017'),
    ]
    failures = [message for ok, message in checks if not ok]
    if failures:
        raise SystemExit('Destino inseguro:\n- ' + '\n- '.join(failures))
    return values


def ref_for(run_id: str, kind: str, index: int) -> str:
    return hashlib.sha256(f'{run_id}:{kind}:{index}'.encode()).hexdigest()[:24]


def uid_for(run_id: str, kind: str, index: int) -> str:
    return str(uuid.uuid5(NAMESPACE, f'{run_id}:{kind}:{index}'))


def chunks(rows: list, size: int):
    for start in range(0, len(rows), size):
        yield rows[start:start + size]


def resolve_offer_rows(offer_meta, variant_ids, offer_by_variant_seller):
    """El SKU puede repetirse entre vendedores; la identidad es variante+vendedor."""
    rows = []
    for meta in offer_meta:
        ref, variant_ref, seller_id, sku, _, _ = meta
        offer_id = offer_by_variant_seller.get((variant_ids[variant_ref], seller_id))
        if offer_id is None:
            raise RuntimeError(
                'No se pudo resolver la oferta DEMO para '
                f'producto={ref}, vendedor={seller_id}, sku={sku}'
            )
        rows.append((offer_id, *meta))
    return rows


def should_seed_order(existing_line_count: int) -> bool:
    """Una ampliación de perfil no reescribe compras ya generadas y pagadas."""
    return existing_line_count == 0


def complete_paid_line_inventory_ids(inventory_ids, paid_lines, lookup):
    """Incluye inventarios de ofertas pagadas de perfiles DEMO anteriores."""
    missing = sorted({line['oferta_id'] for line in paid_lines} - inventory_ids.keys())
    if not missing:
        return inventory_ids
    resolved = lookup(missing)
    unresolved = set(missing) - resolved.keys()
    if unresolved:
        raise RuntimeError(
            f'Ofertas DEMO pagadas sin inventario: {sorted(unresolved)}'
        )
    return {**inventory_ids, **resolved}


def planned_fraud_order(index, users, sellers, offers, offers_by_seller, owner_by_seller):
    """Reserva compradores y compras verificables sin alterar los detectores."""
    if index < 25:
        return users[len(sellers) + index], [(offers[index // 5][0], 1)]
    if index < 40:
        offset = index - 25
        seller = sellers[offset // 3]
        seller_offers = offers_by_seller[seller]
        if len({row[1] for row in seller_offers}) < 3:
            raise RuntimeError(f'F02 requiere tres productos del vendedor {seller}')
        return users[len(sellers) + 30 + offset // 3], [(seller_offers[offset % 3][0], 1)]
    if index < 55:
        offset = index - 40
        return users[len(sellers) + 40 + offset // 3], [(offers_by_seller[sellers[0]][offset % 3][0], 1)]
    if index < 65:
        offer = offers[index % len(offers)]
        return owner_by_seller[offer[3]], [(offer[0], 1 + (index * 3) % 7)]
    if index < 71:
        return None, [(offers[index - 65][0], 10 + index - 65)]
    return None


class DemoSeeder:
    def __init__(self, cfg: dict[str, str], scale: Scale, *, seed: int,
                 run_id: str, batch_size: int):
        self.cfg = cfg
        self.scale = scale
        self.rng = random.Random(seed)
        self.run_id = run_id
        self.batch_size = batch_size
        self.now = datetime.now().replace(microsecond=0)
        self.prefix = f'demo-{run_id}'
        self.already_complete = False
        self.mysql = pymysql.connect(
            host=cfg['MYSQL_HOST'], port=int(cfg['MYSQL_PORT']),
            user=cfg['MYSQL_USER'], password=cfg['MYSQL_PASSWORD'],
            database=cfg['MYSQL_DB'], charset='utf8mb4', autocommit=False,
            cursorclass=pymysql.cursors.DictCursor,
        )
        self.mongo_client = MongoClient(cfg['MONGO_URI'], serverSelectionTimeoutMS=5000)
        self.mongo = self.mongo_client[cfg['MONGO_DB']]

    def many(self, sql: str, rows: list[tuple]) -> None:
        if not rows:
            return
        with self.mysql.cursor() as cur:
            for batch in chunks(rows, self.batch_size):
                cur.executemany(sql, batch)
        self.mysql.commit()

    def fetch_map(self, sql: str, args=()) -> dict:
        with self.mysql.cursor() as cur:
            cur.execute(sql, args)
            return {row['k']: row['v'] for row in cur.fetchall()}

    def prepare_tracking(self) -> None:
        requested_profile = next(k for k, v in SCALES.items() if v == self.scale)
        with self.mysql.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS demo_seed_runs (
                  run_id VARCHAR(64) PRIMARY KEY,
                  perfil VARCHAR(20) NOT NULL,
                  estado ENUM('en_curso','completo','error') NOT NULL,
                  semilla BIGINT NOT NULL,
                  metricas JSON NULL,
                  iniciado_en DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  finalizado_en DATETIME NULL
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            cur.execute(
                'SELECT estado, perfil FROM demo_seed_runs WHERE run_id=%s',
                (self.run_id,),
            )
            existing = cur.fetchone()
            if (
                existing
                and existing['estado'] == 'completo'
                and existing['perfil'] == requested_profile
            ):
                self.already_complete = True
                return
            cur.execute("""
                INSERT INTO demo_seed_runs(run_id, perfil, estado, semilla)
                VALUES (%s, %s, 'en_curso', %s)
                ON DUPLICATE KEY UPDATE
                  perfil=VALUES(perfil),
                  estado='en_curso',
                  semilla=VALUES(semilla),
                  finalizado_en=NULL
            """, (self.run_id, requested_profile, self.rng.getrandbits(31)))
        self.mysql.commit()

    def seed_users(self) -> tuple[list[int], list[int]]:
        total = self.scale.users
        seller_count = self.scale.sellers
        rows = []
        for i in range(total):
            is_seller = i < seller_count
            rows.append((
                f'{self.prefix}.u{i:05d}@example.invalid', PASSWORD_HASH,
                f'Demo{i:05d}', 'Sintético', f'555{i:08d}'[-11:], 'activo', 1,
            ))
        self.many("""
            INSERT IGNORE INTO usuarios
              (email,password_hash,nombre,apellido,telefono,estado,email_verificado)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
        """, rows)
        user_map = self.fetch_map(
            "SELECT email k,id v FROM usuarios WHERE email LIKE %s ORDER BY id",
            (f'{self.prefix}.u%@example.invalid',),
        )
        user_ids = [user_map[f'{self.prefix}.u{i:05d}@example.invalid'] for i in range(total)]
        self.many('INSERT IGNORE INTO usuario_rol(usuario_id,rol_id) VALUES (%s,1)', [(x,) for x in user_ids])
        self.many('INSERT IGNORE INTO usuario_rol(usuario_id,rol_id) VALUES (%s,2)', [(x,) for x in user_ids[:seller_count]])
        self.many("""
            INSERT IGNORE INTO direcciones
              (usuario_id,tipo,pais,departamento,municipio,linea1,es_predeterminada,activa)
            VALUES (%s,'envio','Guatemala',%s,%s,%s,1,1)
        """, [(uid, 'Guatemala', 'Guatemala', f'{self.prefix} dirección {i}') for i, uid in enumerate(user_ids)])
        self.many("""
            INSERT IGNORE INTO vendedores
              (usuario_id,nombre_comercial,nit,descripcion,estado_verificacion,es_tiendaya)
            VALUES (%s,%s,%s,%s,'verificado',0)
        """, [
            (uid, f'DEMO Tienda {i:03d}', f'DEMO-{self.run_id[:8]}-{i:04d}',
             'Vendedor sintético; no representa una persona o empresa real.')
            for i, uid in enumerate(user_ids[:seller_count])
        ])
        seller_by_user = self.fetch_map(
            "SELECT usuario_id k,id v FROM vendedores WHERE nit LIKE %s",
            (f'DEMO-{self.run_id[:8]}-%',),
        )
        return user_ids, [seller_by_user[x] for x in user_ids[:seller_count]]

    def seed_catalog(self, seller_ids: list[int]):
        categories = [9, 10, 11, 12, 13, 14, 3, 4, 5, 6, 7, 8]
        products = []
        for i in range(self.scale.products):
            ref = ref_for(self.run_id, 'product', i)
            products.append((ref, categories[i % len(categories)], self.now - timedelta(days=180 - i % 180)))
        self.many("""
            INSERT IGNORE INTO producto_referencias(producto_ref,categoria_id,fecha_creacion)
            VALUES (%s,%s,%s)
        """, products)
        product_ids = self.fetch_map(
            'SELECT producto_ref k,id v FROM producto_referencias WHERE producto_ref IN (' +
            ','.join(['%s'] * len(products)) + ')', tuple(row[0] for row in products),
        )
        self.many("""
            INSERT INTO producto_referencia_categorias
              (producto_referencia_id,categoria_id,es_principal)
            VALUES (%s,%s,1)
            ON DUPLICATE KEY UPDATE es_principal=VALUES(es_principal)
        """, [(product_ids[ref], category_id) for ref, category_id, _ in products])
        variants = [(product_ids[ref], ref_for(self.run_id, 'variant', i), self.now)
                    for i, (ref, _, _) in enumerate(products)]
        self.many("""
            INSERT IGNORE INTO producto_variante_referencias
              (producto_referencia_id,variante_ref,fecha_registro) VALUES (%s,%s,%s)
        """, variants)
        variant_ids = self.fetch_map(
            'SELECT variante_ref k,id v FROM producto_variante_referencias WHERE variante_ref IN (' +
            ','.join(['%s'] * len(variants)) + ')', tuple(row[1] for row in variants),
        )
        offers = []
        offer_meta = []
        used_pairs = set()
        i = 0
        while len(offers) < self.scale.offers:
            product_index = i % self.scale.products
            seller_index = (i // self.scale.products + product_index) % len(seller_ids)
            pair = (product_index, seller_index)
            i += 1
            if pair in used_pairs:
                continue
            used_pairs.add(pair)
            ref = products[product_index][0]
            variant_ref = variants[product_index][1]
            price = Decimal(25 + (product_index * 37 + seller_index * 11) % 4900).quantize(Decimal('0.01'))
            sku = f'DEMO-{self.run_id[:5].upper()}-{len(offers):05d}'
            offers.append((ref, variant_ids[variant_ref], seller_ids[seller_index], sku, price, 'GTQ', 'activa', self.now, self.now))
            offer_meta.append((ref, variant_ref, seller_ids[seller_index], sku, price, product_index))
        self.many("""
            INSERT IGNORE INTO ofertas
              (producto_ref,producto_variante_id,vendedor_id,sku,precio_actual,moneda,estado,fecha_creacion,fecha_actualizacion)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, offers)
        # Al ampliar una corrida small a medium/full, la secuencia de pares
        # producto-vendedor cambia porque también cambia el número de productos.
        # MySQL preserva correctamente una oferta ya existente mediante
        # uq_oferta_vendedor_variante, aunque su SKU anterior no coincida con el
        # SKU que habría generado el perfil mayor. El SKU no identifica una
        # oferta globalmente: distintos vendedores pueden usar el mismo.
        # Resolver exclusivamente por la identidad comercial evita enlazar el
        # inventario y los historiales al vendedor equivocado.
        with self.mysql.cursor() as cur:
            cur.execute(
                'SELECT id,producto_variante_id,vendedor_id FROM ofertas '
                'WHERE producto_variante_id IN (' +
                ','.join(['%s'] * len(variant_ids)) + ')',
                tuple(variant_ids.values()),
            )
            offer_by_variant_seller = {
                (row['producto_variante_id'], row['vendedor_id']): row['id']
                for row in cur.fetchall()
            }
        offer_rows = resolve_offer_rows(
            offer_meta, variant_ids, offer_by_variant_seller,
        )
        self.many("""
            INSERT IGNORE INTO inventario(oferta_id,cantidad_disponible,cantidad_reservada,punto_reorden,bodega)
            SELECT %s,5000,0,20,'principal'
            WHERE NOT EXISTS (
              SELECT 1 FROM inventario
              WHERE oferta_id=%s AND bodega IN ('principal','demo-principal')
            )
        """, [(row[0], row[0]) for row in offer_rows])
        inventory_ids = self.fetch_map(
            'SELECT oferta_id k,id v FROM inventario WHERE bodega IN '
            "('principal','demo-principal') AND oferta_id IN (" +
            ','.join(['%s'] * len(offer_rows)) + ') '
            "ORDER BY (cantidad_disponible > cantidad_reservada), "
            "FIELD(bodega,'demo-principal','principal')",
            tuple(row[0] for row in offer_rows),
        )
        self.many("""
            INSERT INTO oferta_precios_historial
              (oferta_id,precio,moneda,vigente_desde,motivo)
            SELECT %s,%s,'GTQ',%s,'Carga DEMO'
            WHERE NOT EXISTS (
              SELECT 1 FROM oferta_precios_historial WHERE oferta_id=%s AND motivo='Carga DEMO'
            )
        """, [(row[0], row[5], self.now, row[0]) for row in offer_rows])
        self.many("""
            INSERT INTO oferta_estados_historial
              (oferta_id,vendedor_id,sku,estado,vigente_desde,motivo)
            SELECT %s,%s,%s,'activa',%s,'Carga DEMO'
            WHERE NOT EXISTS (
              SELECT 1 FROM oferta_estados_historial WHERE oferta_id=%s AND motivo='Carga DEMO'
            )
        """, [(row[0], row[3], row[4], self.now, row[0]) for row in offer_rows])
        self.many("""
            INSERT INTO inventario_saldos_historial
              (inventario_id,cantidad_disponible,cantidad_reservada,vigente_desde,motivo)
            SELECT %s,5000,0,%s,'Carga DEMO'
            WHERE NOT EXISTS (
              SELECT 1 FROM inventario_saldos_historial WHERE inventario_id=%s AND motivo='Carga DEMO'
            )
        """, [(inventory_ids[row[0]], self.now, inventory_ids[row[0]]) for row in offer_rows])

        docs = []
        category_names = {9: 'Computadoras', 10: 'Celulares', 11: 'Audio', 12: 'Camisas', 13: 'Pantalones', 14: 'Calzado', 3: 'Hogar', 4: 'Libros', 5: 'Deportes', 6: 'Alimentos', 7: 'Juguetes', 8: 'Herramientas'}
        category_slugs = {k: v.lower().replace(' ', '-') for k, v in category_names.items()}
        first_offer = {}
        for row in offer_rows:
            first_offer.setdefault(row[1], row)
        for i, (ref, category_id, created) in enumerate(products):
            row = first_offer[ref]
            docs.append(ReplaceOne({'_id': ObjectId(ref)}, {
                '_id': ObjectId(ref), 'sku': row[4], 'nombre': demo_product_name(i),
                'descripcion': 'Producto sintético generado para pruebas de volumen.',
                'precio': float(row[5]), 'categoria': {'slug': category_slugs[category_id], 'nombre': category_names[category_id]},
                'categorias': [{'slug': category_slugs[category_id], 'nombre': category_names[category_id]}],
                'atributos': {'color': ['azul', 'negro', 'rojo'][i % 3], 'modelo_demo': i},
                'variantes': [{'variante_ref': ref_for(self.run_id, 'variant', i), 'atributos': {'modelo': f'V{i:04d}'}}],
                'estado': 'activo', 'disponible': True, 'stock': 5000,
                'fecha_creacion': created, 'fecha_actualizacion': self.now,
                'demo_run_id': self.run_id,
            }, upsert=True))
        for batch in chunks(docs, self.batch_size):
            self.mongo.productos.bulk_write(batch, ordered=False)
        self.mongo.productos.create_index('demo_run_id')
        variant_docs = []
        for i, (ref, _, _) in enumerate(products):
            variant_ref = ref_for(self.run_id, 'variant', i)
            row = first_offer[ref]
            variant_docs.append(ReplaceOne({'_id': ObjectId(variant_ref)}, {
                '_id': ObjectId(variant_ref),
                'producto_ref': ref,
                'sku_catalogo': row[4],
                'atributos': {'modelo': f'V{i:04d}'},
                'clave_variante': f'modelo=V{i:04d}',
                'estado': 'activa',
                'es_predeterminada': True,
                'fecha_creacion': self.now,
                'fecha_actualizacion': self.now,
                'demo_run_id': self.run_id,
            }, upsert=True))
        for batch in chunks(variant_docs, self.batch_size):
            self.mongo.producto_variantes.bulk_write(batch, ordered=False)
        return products, offer_rows, inventory_ids

    def seed_orders(self, user_ids: list[int], seller_ids: list[int], products,
                    offers, inventory_ids):
        direction_by_user = self.fetch_map(
            'SELECT usuario_id k,MIN(id) v FROM direcciones WHERE usuario_id IN (' +
            ','.join(['%s'] * len(user_ids)) + ') GROUP BY usuario_id', tuple(user_ids),
        )
        offer_by_id = {row[0]: row for row in offers}
        offers_by_seller = {}
        for row in offers:
            offers_by_seller.setdefault(row[3], []).append(row)
        owner_by_seller = self.fetch_map(
            'SELECT id k,usuario_id v FROM vendedores WHERE id IN (' +
            ','.join(['%s'] * len(seller_ids)) + ')', tuple(seller_ids),
        )
        exclusive_buyers = [user_ids[len(seller_ids) + 30 + n] for n in range(5)]
        ordinary_buyers = [uid for uid in user_ids if uid not in exclusive_buyers]
        order_rows = []
        planned: list[list[tuple[int, int]]] = []
        extra_lines = max(0, self.scale.lines - self.scale.orders)
        for i in range(self.scale.orders):
            buyer = ordinary_buyers[(i * 17 + 7) % len(ordinary_buyers)]
            line_count = 2 if i < extra_lines else 1
            choices = []
            scenario = planned_fraud_order(
                i, user_ids, seller_ids, offers, offers_by_seller, owner_by_seller,
            )
            if scenario is not None:
                special_buyer, choices = scenario
                if special_buyer is not None:
                    buyer = special_buyer
            else:
                for j in range(line_count):
                    offer = offers[(i * 13 + j * 29) % len(offers)]
                    choices.append((offer[0], 1 + ((i + j) % 3 == 0)))
            planned.append(choices)
            paid = i < 71 or i % 20 != 0
            state = 'entregado' if paid else 'cancelado'
            created = (
                self.now - timedelta(hours=1 + i // 5, minutes=i % 5)
                if i < 71 else
                self.now - timedelta(days=i % 180, minutes=i % 1440)
            )
            subtotal = sum(offer_by_id[x][5] * qty for x, qty in choices)
            order_rows.append((buyer, direction_by_user[buyer], state, subtotal, Decimal('0'), subtotal,
                               'Pedido sintético DEMO', uid_for(self.run_id, 'order', i),
                               hashlib.sha256(f'{self.run_id}:order:{i}'.encode()).hexdigest(), created, created))
        self.many("""
            INSERT IGNORE INTO pedidos
              (usuario_id,direccion_id,estado,subtotal,impuestos,total,notas,clave_idempotencia,huella_solicitud,fecha_creacion,fecha_actualizacion)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, order_rows)
        order_ids = self.fetch_map(
            'SELECT clave_idempotencia k,id v FROM pedidos WHERE clave_idempotencia IN (' +
            ','.join(['%s'] * len(order_rows)) + ')', tuple(row[7] for row in order_rows),
        )
        order_id_values = tuple(order_ids.values())
        with self.mysql.cursor() as cur:
            cur.execute(f"""
                INSERT IGNORE INTO pedido_direcciones
                  (pedido_id,receptor_nombre,receptor_telefono,pais,
                   departamento,municipio,linea1,linea2,codigo_postal)
                SELECT p.id,TRIM(CONCAT_WS(' ',u.nombre,u.apellido)),u.telefono,
                       d.pais,d.departamento,d.municipio,d.linea1,d.linea2,d.codigo_postal
                FROM pedidos p
                JOIN usuarios u ON u.id=p.usuario_id
                JOIN direcciones d ON d.id=p.direccion_id
                WHERE p.id IN ({','.join(['%s'] * len(order_id_values))})
            """, order_id_values)
        self.mysql.commit()
        line_rows = []
        movement_rows = []
        payment_rows = []
        line_context = []
        existing_line_counts = self.fetch_map(
            'SELECT pedido_id k,COUNT(*) v FROM pedido_lineas WHERE pedido_id IN (' +
            ','.join(['%s'] * len(order_ids)) + ') GROUP BY pedido_id', tuple(order_ids.values()),
        )
        for i, choices in enumerate(planned):
            order_id = order_ids[order_rows[i][7]]
            buyer = order_rows[i][0]
            paid = order_rows[i][2] != 'cancelado'
            grouped = {}
            # Al ampliar small -> medium/full cambia la planificación de los
            # primeros pedidos. Su importe y pago originales son históricos:
            # nunca añadir líneas nuevas a un pedido que ya tiene líneas.
            if not should_seed_order(int(existing_line_counts.get(order_id, 0))):
                continue
            for offer_id, qty in choices:
                grouped.setdefault(offer_by_id[offer_id][3], Decimal('0'))
                grouped[offer_by_id[offer_id][3]] += offer_by_id[offer_id][5] * qty
            with self.mysql.cursor() as cur:
                for seller_id, subtotal in grouped.items():
                    cur.execute("""
                        INSERT INTO pedido_vendedores(pedido_id,vendedor_id,estado,subtotal,costo_envio,fecha_creacion,fecha_actualizacion)
                        VALUES (%s,%s,%s,%s,0,%s,%s)
                        ON DUPLICATE KEY UPDATE id=LAST_INSERT_ID(id)
                    """, (order_id, seller_id, 'entregado' if paid else 'cancelado', subtotal, order_rows[i][9], order_rows[i][10]))
                    grouped[seller_id] = cur.lastrowid
            self.mysql.commit()
            for offer_id, qty in choices:
                meta = offer_by_id[offer_id]
                seller_id, sku, price, product_index = meta[3], meta[4], meta[5], meta[6]
                line_rows.append((order_id, grouped[seller_id], offer_id, meta[1], sku,
                                  demo_product_name(product_index), f'DEMO Tienda {seller_ids.index(seller_id):03d}',
                                  price, qty, price * qty))
                line_context.append((buyer, meta[1], seller_id, order_id, offer_id, paid, order_rows[i][9]))
                if paid:
                    inv_id = inventory_ids[offer_id]
                    movement_rows.append((inv_id, 'salida', qty, 'Venta DEMO pagada',
                                          order_id, buyer, order_rows[i][9], inv_id, order_id))
            payment_rows.append((order_id, 1, order_rows[i][5], 'aprobado' if paid else 'rechazado',
                                 f'DEMO-{self.run_id}-{i}', uid_for(self.run_id, 'payment', i), 1, order_rows[i][9]))
        self.many("""
            INSERT IGNORE INTO pedido_lineas
              (pedido_id,pedido_vendedor_id,oferta_id,producto_ref,sku_snapshot,producto_nombre,vendedor_nombre_snapshot,precio_unitario,cantidad,subtotal_linea)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, line_rows)
        self.many("""
            INSERT IGNORE INTO pagos
              (pedido_id,metodo_pago_id,monto,estado,referencia_transaccion,clave_idempotencia,intentos,fecha)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        """, payment_rows)
        # Ajustar el saldo solo por movimientos realmente nuevos. Reponerlo a
        # 5000 - ventas de esta corrida olvidaba las compras de perfiles previos.
        sold = {}
        with self.mysql.cursor() as cur:
            for row in movement_rows:
                inv_id, _, qty, _, order_id, *_ = row
                cur.execute("""
                    INSERT INTO movimientos_inventario
                      (inventario_id,tipo,cantidad,motivo,pedido_id,usuario_id,fecha)
                    SELECT %s,%s,%s,%s,%s,%s,%s
                    WHERE NOT EXISTS (
                      SELECT 1 FROM movimientos_inventario
                      WHERE inventario_id=%s AND pedido_id=%s AND tipo='salida'
                        AND motivo='Venta DEMO pagada'
                    )
                """, row)
                if cur.rowcount:
                    sold[inv_id] = sold.get(inv_id, 0) + qty
            for inv_id, qty in sold.items():
                cur.execute('UPDATE inventario SET cantidad_disponible=cantidad_disponible-%s WHERE id=%s AND cantidad_disponible>=%s', (qty, inv_id, qty))
                if cur.rowcount != 1:
                    self.mysql.rollback()
                    raise RuntimeError(f'Stock insuficiente en inventario DEMO {inv_id}')
        self.mysql.commit()
        return line_context

    def seed_reviews_and_inventory_patterns(self, user_ids, seller_ids, offers,
                                            inventory_ids, line_context):
        with self.mysql.cursor() as cur:
            cur.execute("""
              SELECT pl.id,pl.pedido_id,pl.producto_ref,pl.oferta_id,pl.cantidad,
                     p.usuario_id,pv.vendedor_id,p.fecha_creacion
              FROM pedido_lineas pl JOIN pedidos p ON p.id=pl.pedido_id
              JOIN pedido_vendedores pv ON pv.id=pl.pedido_vendedor_id
              JOIN pagos pa ON pa.pedido_id=p.id AND pa.estado='aprobado'
              WHERE pl.sku_snapshot LIKE %s ORDER BY pl.id
            """, (f'DEMO-{self.run_id[:5].upper()}-%',))
            paid_lines = cur.fetchall()
        inventory_ids = complete_paid_line_inventory_ids(
            inventory_ids, paid_lines,
            lambda offer_ids: self.fetch_map(
                'SELECT oferta_id k,id v FROM inventario WHERE oferta_id IN (' +
                ','.join(['%s'] * len(offer_ids)) + ')', tuple(offer_ids),
            ),
        )
        product_id_by_ref = self.fetch_map(
            'SELECT producto_ref k,id v FROM producto_referencias WHERE producto_ref IN (' +
            ','.join(['%s'] * self.scale.products) + ')',
            tuple(ref_for(self.run_id, 'product', i) for i in range(self.scale.products)),
        )
        seen = set()
        verified = []
        verified_target = max(0, self.scale.reviews - max(10, self.scale.reviews // 10))
        verified_comments = (
            'Llegó completo y coincide con la descripción de la tienda.',
            'La entrega fue puntual; funciona bien tras varios días de uso.',
            'Buena calidad para el precio, aunque el empaque podría mejorar.',
            'El vendedor respondió mis dudas y el artículo llegó en buen estado.',
            'Cumple lo ofrecido; volvería a comprar esta variante.',
        )
        for row in paid_lines:
            key = (row['usuario_id'], row['producto_ref'], row['vendedor_id'])
            if key in seen:
                continue
            seen.add(key)
            idx = len(verified)
            date = self.now - timedelta(hours=idx % 12) if idx < 6 else row['fecha_creacion']
            verified.append((f'demo:{self.run_id}:v:{idx}', row['usuario_id'], product_id_by_ref[row['producto_ref']],
                             row['vendedor_id'], row['id'], 4 + idx % 2,
                             f'DEMO: {verified_comments[idx % len(verified_comments)]}',
                             'aprobada', 1, None, 1, 1, date, date))
            if len(verified) >= verified_target:
                break
        historical = []
        remaining = self.scale.reviews - len(verified)
        historical_comments = (
            'DEMO histórica: no se encontró un pedido pagado que respalde esta opinión.',
            'DEMO histórica: la compra original no se puede atribuir a este vendedor.',
            'DEMO histórica: faltan evidencias de la línea comprada.',
        )
        for i in range(remaining):
            product_ref = ref_for(self.run_id, 'product', (i * 19 + 3) % self.scale.products)
            historical.append((f'demo:{self.run_id}:h:{i}', user_ids[(i * 23 + 5) % len(user_ids)],
                               product_id_by_ref[product_ref], seller_ids[i % len(seller_ids)], None,
                               2 + i % 4, historical_comments[i % len(historical_comments)], 'pendiente', 0,
                               'Sin compra elegible en el dataset DEMO', 1, 0,
                               self.now - timedelta(days=40 + i % 120), self.now))
        self.many("""
            INSERT IGNORE INTO resenas
              (public_id,usuario_id,producto_referencia_id,vendedor_id,pedido_linea_id,calificacion,comentario,estado_moderacion,verificada_compra,motivo_no_verificada,version,aprobada,fecha,fecha_actualizacion)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, verified + historical)
        # F06: ajustes variados por oferta, fecha, cantidad y propietario.
        seller_owner = self.fetch_map(
            'SELECT id k,usuario_id v FROM vendedores WHERE id IN (' + ','.join(['%s'] * len(seller_ids)) + ')',
            tuple(seller_ids),
        )
        adjustments = []
        for i, row in enumerate(offers[:max(3, min(20, len(offers)))]):
            for j in range(3):
                inv_id = inventory_ids[row[0]]
                quantity = 12 + ((i * 7 + j * 11) % 47)
                movement_type = 'entrada' if j == 0 else 'ajuste'
                motive = (
                    f'Entrada justificada DEMO F06 oferta {row[0]}' if j == 0
                    else f'Ajuste positivo DEMO F06 oferta {row[0]} patrón {j}'
                )
                responsible = (
                    seller_owner[row[3]] if j != 1
                    else user_ids[(i * 13 + 7) % len(user_ids)]
                )
                adjustments.append((inv_id, movement_type, quantity,
                                    motive, None, responsible,
                                    self.now - timedelta(days=(i + j) % 19, hours=(i * 3 + j) % 20), inv_id, motive))
        with self.mysql.cursor() as cur:
            try:
                for row in adjustments:
                    cur.execute("""
                        INSERT INTO movimientos_inventario
                          (inventario_id,tipo,cantidad,motivo,pedido_id,usuario_id,fecha)
                        SELECT %s,%s,%s,%s,%s,%s,%s
                        WHERE NOT EXISTS (
                          SELECT 1 FROM movimientos_inventario
                          WHERE inventario_id=%s AND motivo=%s
                        )
                    """, row)
                    if cur.rowcount:
                        cur.execute(
                            'UPDATE inventario SET cantidad_disponible=cantidad_disponible+%s WHERE id=%s',
                            (row[2], row[0]),
                        )
                self.mysql.commit()
            except Exception:
                self.mysql.rollback()
                raise

        # F07: escenarios deterministas. El positivo usa la primera compra de
        # cada combinación oferta/cantidad para evitar candidatos previos; el
        # ambiguo usa dos compras ya existentes y queda excluido por el detector.
        first_by_key = {}
        grouped = {}
        for line in paid_lines:
            key = (line['oferta_id'], int(line['cantidad']))
            first_by_key.setdefault(key, line)
            grouped.setdefault(key, []).append(line)

        f07_rows = []
        positive_order_keys = {
            uid_for(self.run_id, 'order', i) for i in range(65, 71)
        }
        positive_order_ids = set(self.fetch_map(
            'SELECT clave_idempotencia k,id v FROM pedidos WHERE clave_idempotencia IN (' +
            ','.join(['%s'] * len(positive_order_keys)) + ')',
            tuple(positive_order_keys),
        ).values())
        positive = [
            line for line in paid_lines
            if line['pedido_id'] in positive_order_ids
            and first_by_key[(line['oferta_id'], int(line['cantidad']))]['id'] == line['id']
        ][:6]
        for line in positive:
            inv_id = inventory_ids[line['oferta_id']]
            reason = f'DEMO F07 positivo línea {line["id"]}'
            date = line['fecha_creacion'] + timedelta(minutes=30)
            qty = int(line['cantidad'])
            f07_rows.append((inv_id, 'entrada', qty, reason, None, None, date, inv_id, reason))

        if positive:
            line = positive[0]
            inv_id = inventory_ids[line['oferta_id']]
            for label, qty, date in [
                ('cantidad distinta', int(line['cantidad']) + 7, line['fecha_creacion'] + timedelta(hours=1)),
                ('antes de compra', int(line['cantidad']), line['fecha_creacion'] - timedelta(hours=1)),
                ('fuera de ventana', int(line['cantidad']), line['fecha_creacion'] + timedelta(days=31)),
            ]:
                reason = f'DEMO F07 negativo {label} línea {line["id"]}'
                f07_rows.append((inv_id, 'entrada', qty, reason, None, None, date, inv_id, reason))
            other_offer = next((
                row for row in offers
                if row[0] != line['oferta_id']
                and (row[0], int(line['cantidad'])) not in grouped
            ), None)
            if other_offer:
                other_inv = inventory_ids[other_offer[0]]
                reason = f'DEMO F07 negativo oferta distinta línea {line["id"]}'
                f07_rows.append((
                    other_inv, 'entrada', int(line['cantidad']), reason,
                    None, None, line['fecha_creacion'] + timedelta(hours=1),
                    other_inv, reason,
                ))

        ambiguous = next((rows for rows in grouped.values() if len(rows) >= 2), None)
        if ambiguous:
            chosen = ambiguous[:2]
            inv_id = inventory_ids[chosen[0]['oferta_id']]
            qty = int(chosen[0]['cantidad'])
            reason = f'DEMO F07 ambiguo líneas {chosen[0]["id"]}-{chosen[1]["id"]}'
            date = max(row['fecha_creacion'] for row in chosen) + timedelta(minutes=30)
            f07_rows.append((inv_id, 'entrada', qty, reason, None, None, date, inv_id, reason))

        reasons = [row[3] for row in f07_rows]
        existing_reasons = set()
        if reasons:
            with self.mysql.cursor() as cur:
                cur.execute(
                    'SELECT motivo FROM movimientos_inventario WHERE motivo IN (' +
                    ','.join(['%s'] * len(reasons)) + ')', tuple(reasons),
                )
                existing_reasons = {row['motivo'] for row in cur.fetchall()}
        f07_rows = [row for row in f07_rows if row[3] not in existing_reasons]
        stock_delta = {}
        for inv_id, _, qty, *_ in f07_rows:
            stock_delta[inv_id] = stock_delta.get(inv_id, 0) + int(qty)

        self.many("""
            INSERT INTO movimientos_inventario
              (inventario_id,tipo,cantidad,motivo,pedido_id,usuario_id,fecha)
            SELECT %s,%s,%s,%s,%s,%s,%s
            WHERE NOT EXISTS (
              SELECT 1 FROM movimientos_inventario
              WHERE inventario_id=%s AND motivo=%s
            )
        """, f07_rows)
        with self.mysql.cursor() as cur:
            for inv_id, qty in stock_delta.items():
                # f07_rows contiene únicamente motivos aún no insertados.
                cur.execute(
                    'UPDATE inventario SET cantidad_disponible=cantidad_disponible+%s WHERE id=%s',
                    (qty, inv_id),
                )
        self.mysql.commit()

    def metrics(self) -> dict:
        tables = ['usuarios', 'vendedores', 'producto_referencias', 'ofertas', 'pedidos',
                  'pedido_lineas', 'pagos', 'resenas', 'movimientos_inventario']
        result = {}
        with self.mysql.cursor() as cur:
            for table in tables:
                cur.execute(f'SELECT COUNT(*) total FROM `{table}`')
                result[table] = int(cur.fetchone()['total'])
        result['mongo_productos'] = self.mongo.productos.count_documents({'demo_run_id': self.run_id})
        return result

    def run(self) -> dict:
        self.prepare_tracking()
        if self.already_complete:
            print(
                f'La corrida {self.run_id} ya estaba completa; se reconciliarán '
                'sus estructuras idempotentes sin duplicar datos.'
            )
        users, sellers = self.seed_users()
        products, offers, inventory = self.seed_catalog(sellers)
        context = self.seed_orders(users, sellers, products, offers, inventory)
        self.seed_reviews_and_inventory_patterns(users, sellers, offers, inventory, context)
        metrics = self.metrics()
        with self.mysql.cursor() as cur:
            cur.execute("""
              UPDATE demo_seed_runs SET estado='completo',metricas=%s,finalizado_en=NOW()
              WHERE run_id=%s
            """, (json.dumps(metrics), self.run_id))
        self.mysql.commit()
        return metrics

    def run_fraud_scenarios_only(self) -> dict:
        """Agrega solo patrones F05-F07 sobre datos DEMO ya existentes."""
        with self.mysql.cursor() as cur:
            cur.execute("SELECT id FROM usuarios WHERE email LIKE %s ORDER BY id", (f'{self.prefix}.u%@example.invalid',))
            users = [row['id'] for row in cur.fetchall()]
            cur.execute("SELECT id FROM vendedores WHERE nit LIKE %s ORDER BY id", (f'DEMO-{self.run_id[:8]}-%',))
            sellers = [row['id'] for row in cur.fetchall()]
            cur.execute("""
              SELECT o.id,o.producto_ref,pvr.variante_ref,o.vendedor_id,o.sku,
                     o.precio_actual,0 producto_index
              FROM ofertas o
              JOIN producto_variante_referencias pvr ON pvr.id=o.producto_variante_id
              WHERE o.sku LIKE %s ORDER BY o.id
            """, (f'DEMO-{self.run_id[:5].upper()}-%',))
            offers = [tuple(row.values()) for row in cur.fetchall()]
        if not users or not sellers or not offers:
            raise RuntimeError('La corrida DEMO no existe o está incompleta; no se aplicaron escenarios.')
        inventory = self.fetch_map(
            'SELECT oferta_id k,id v FROM inventario WHERE oferta_id IN (' +
            ','.join(['%s'] * len(offers)) + ')', tuple(row[0] for row in offers),
        )
        self.seed_reviews_and_inventory_patterns(users, sellers, offers, inventory, [])
        return self.metrics()

    def close(self):
        self.mysql.close()
        self.mongo_client.close()


def run_projection_scripts(cfg: dict[str, str]) -> None:
    env = os.environ.copy()
    env.update(cfg)
    commands = [
        [sys.executable, 'scripts/sync_mongo_projections.py'],
        [sys.executable, 'scripts/backfill_cassandra_analytics.py'],
        [sys.executable, 'scripts/backfill_neo4j_reviews.py', '--apply'],
        [sys.executable, 'scripts/reindex_search.py', '--recrear'],
    ]
    for command in commands:
        print('Proyección:', ' '.join(command[1:]))
        subprocess.run(command, cwd=BACKEND_DIR, env=env, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description='Genera datos únicamente en TiendaYa DEMO.')
    parser.add_argument('--env-file', type=Path, required=True)
    parser.add_argument('--profile', choices=SCALES, default='small')
    parser.add_argument('--seed', type=int, default=20261018)
    parser.add_argument('--run-id', default='entrega3-demo-v1')
    parser.add_argument('--batch-size', type=int, default=500)
    parser.add_argument('--confirm-demo', action='store_true')
    parser.add_argument('--project', action='store_true', help='Reconstruye Cassandra, Neo4j y Elasticsearch.')
    parser.add_argument('--fraud-scenarios-only', action='store_true',
                        help='Agrega únicamente escenarios F05-F07 a una DEMO ya cargada.')
    parser.add_argument('--validate-only', action='store_true')
    args = parser.parse_args()
    if not args.confirm_demo:
        raise SystemExit('Falta --confirm-demo; no se abrirá ninguna conexión.')
    cfg = load_demo_env(args.env_file.resolve())
    print(f'Destino validado: {cfg["MYSQL_DB"]} / {cfg["MONGO_DB"]} / perfil={args.profile}')
    if args.validate_only:
        print('Validación segura completada; no se modificó ningún motor.')
        return 0
    os.environ.update(cfg)
    seeder = DemoSeeder(cfg, SCALES[args.profile], seed=args.seed,
                        run_id=args.run_id, batch_size=args.batch_size)
    try:
        metrics = (
            seeder.run_fraud_scenarios_only()
            if args.fraud_scenarios_only else seeder.run()
        )
    finally:
        seeder.close()
    print('Carga DEMO completada:', json.dumps(metrics, indent=2, ensure_ascii=False))
    if args.project:
        run_projection_scripts(cfg)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
