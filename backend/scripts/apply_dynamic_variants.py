#!/usr/bin/env python3
"""Instala y rellena el registro mínimo de variantes dinámicas de forma idempotente."""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pymysql
from bson import ObjectId
from dotenv import load_dotenv
from pymongo import MongoClient, ReturnDocument
from pymongo import ASCENDING

from run_sql_migration import run_sql_file


BACKEND_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BACKEND_DIR.parent
MIGRATION = ROOT_DIR / 'database' / 'mysql' / '15_dynamic_variants.sql'
BACKUP_DIR = ROOT_DIR / 'backups' / 'dynamic_variants'
load_dotenv(BACKEND_DIR / '.env')


def connect_mysql():
    return pymysql.connect(
        host=os.getenv('MYSQL_HOST', 'localhost'),
        port=int(os.getenv('MYSQL_PORT', 3306)),
        db=os.getenv('MYSQL_DB', 'tiendaya'),
        user=os.getenv('MYSQL_USER', 'tiendaya'),
        password=os.getenv('MYSQL_PASSWORD', 'tiendaya123'),
        charset='utf8mb4',
        autocommit=True,
        cursorclass=pymysql.cursors.DictCursor,
    )


def connect_mongo():
    client = MongoClient(os.getenv('MONGO_URI'), serverSelectionTimeoutMS=5000)
    client.admin.command('ping')
    return client, client[os.getenv('MONGO_DB', 'tiendaya')]


def create_backup(connection, mongo):
    with connection.cursor() as cursor:
        cursor.execute('SELECT * FROM ofertas ORDER BY id')
        offers = cursor.fetchall()
        cursor.execute("""
            SELECT TABLE_NAME FROM information_schema.TABLES
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'producto_variante_referencias'
        """)
        registry_exists = bool(cursor.fetchone())
        registry = []
        if registry_exists:
            cursor.execute('SELECT * FROM producto_variante_referencias ORDER BY id')
            registry = cursor.fetchall()

    variants = list(mongo.producto_variantes.find({}))
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    path = BACKUP_DIR / f'before_dynamic_variants_{datetime.now():%Y%m%d_%H%M%S}.json'
    path.write_text(json.dumps({
        'created_at': datetime.now().astimezone().isoformat(),
        'ofertas': offers,
        'producto_variante_referencias': registry,
        'producto_variantes_mongo': variants,
    }, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
    return path


def ensure_mysql_structure(connection):
    statements = run_sql_file(connection, MIGRATION)
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT COUNT(*) AS n FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'ofertas'
              AND COLUMN_NAME = 'producto_variante_id'
        """)
        if not cursor.fetchone()['n']:
            cursor.execute(
                'ALTER TABLE ofertas ADD COLUMN producto_variante_id '
                'INT UNSIGNED NULL AFTER producto_ref'
            )

        cursor.execute("""
            SELECT INDEX_NAME FROM information_schema.STATISTICS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'ofertas'
        """)
        indexes = {row['INDEX_NAME'] for row in cursor.fetchall()}
        if 'idx_oferta_variante' not in indexes:
            cursor.execute(
                'ALTER TABLE ofertas ADD INDEX idx_oferta_variante '
                '(producto_variante_id)'
            )

        cursor.execute("""
            SELECT CONSTRAINT_NAME FROM information_schema.REFERENTIAL_CONSTRAINTS
            WHERE CONSTRAINT_SCHEMA = DATABASE() AND TABLE_NAME = 'ofertas'
        """)
        constraints = {row['CONSTRAINT_NAME'] for row in cursor.fetchall()}
        if 'fk_oferta_variante' not in constraints:
            cursor.execute("""
                ALTER TABLE ofertas ADD CONSTRAINT fk_oferta_variante
                FOREIGN KEY (producto_variante_id)
                REFERENCES producto_variante_referencias(id) ON DELETE RESTRICT
            """)

        cursor.execute("""
            SELECT COUNT(*) AS n FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'solicitudes_catalogo'
              AND COLUMN_NAME = 'producto_variante_id_solicitado'
        """)
        if not cursor.fetchone()['n']:
            cursor.execute(
                'ALTER TABLE solicitudes_catalogo ADD COLUMN '
                'producto_variante_id_solicitado INT UNSIGNED NULL '
                'AFTER producto_ref_solicitado'
            )
        cursor.execute("""
            SELECT CONSTRAINT_NAME FROM information_schema.REFERENTIAL_CONSTRAINTS
            WHERE CONSTRAINT_SCHEMA = DATABASE()
              AND TABLE_NAME = 'solicitudes_catalogo'
        """)
        request_constraints = {row['CONSTRAINT_NAME'] for row in cursor.fetchall()}
        if 'fk_sc_variante_solicitada' not in request_constraints:
            cursor.execute("""
                ALTER TABLE solicitudes_catalogo
                ADD CONSTRAINT fk_sc_variante_solicitada
                FOREIGN KEY (producto_variante_id_solicitado)
                REFERENCES producto_variante_referencias(id) ON DELETE RESTRICT
            """)
    return statements


def ensure_default_variants(connection, mongo):
    with connection.cursor() as cursor:
        cursor.execute(
            'SELECT id, producto_ref FROM producto_referencias ORDER BY id'
        )
        references = cursor.fetchall()

    created = 0
    registered = 0
    for reference in references:
        product = mongo.productos.find_one({'_id': ObjectId(reference['producto_ref'])})
        if not product:
            raise RuntimeError(
                f'No existe el producto MongoDB {reference["producto_ref"]}.'
            )
        existing = mongo.producto_variantes.find_one({
            'producto_ref': reference['producto_ref'],
            'clave_variante': '__default__',
        }, {'_id': 1})
        now = datetime.now(timezone.utc)
        variant = mongo.producto_variantes.find_one_and_update(
            {
                'producto_ref': reference['producto_ref'],
                'clave_variante': '__default__',
            },
            {
                '$setOnInsert': {
                    '_id': ObjectId(),
                    'producto_ref': reference['producto_ref'],
                    'sku_catalogo': product.get('sku') or f'PRODUCTO-{reference["id"]}',
                    'atributos': {},
                    'clave_variante': '__default__',
                    'estado': 'activa' if product.get('estado') == 'activo' else product.get('estado', 'activa'),
                    'es_predeterminada': True,
                    'fecha_creacion': now,
                    'fecha_actualizacion': now,
                },
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        if not existing:
            created += 1
        with connection.cursor() as cursor:
            affected = cursor.execute("""
                INSERT IGNORE INTO producto_variante_referencias
                    (producto_referencia_id, variante_ref)
                VALUES (%s, %s)
            """, (reference['id'], str(variant['_id'])))
            registered += affected
    return created, registered


def ensure_mongo_indexes(mongo):
    mongo.producto_variantes.create_index(
        [('producto_ref', ASCENDING), ('clave_variante', ASCENDING)],
        name='uidx_variante_producto_clave',
        unique=True,
        background=True,
    )
    mongo.producto_variantes.create_index(
        [('sku_catalogo', ASCENDING)],
        name='uidx_variante_sku',
        unique=True,
        background=True,
    )


def backfill_offers(connection):
    with connection.cursor() as cursor:
        cursor.execute("""
            UPDATE ofertas o
            JOIN producto_referencias pr ON pr.producto_ref = o.producto_ref
            JOIN producto_variante_referencias pvr
              ON pvr.producto_referencia_id = pr.id
            JOIN (
                SELECT producto_referencia_id, COUNT(*) AS n
                FROM producto_variante_referencias
                GROUP BY producto_referencia_id
            ) counts ON counts.producto_referencia_id = pr.id AND counts.n = 1
            SET o.producto_variante_id = pvr.id
            WHERE o.producto_variante_id IS NULL
        """)
        updated = cursor.rowcount
        cursor.execute(
            'SELECT COUNT(*) AS n FROM ofertas WHERE producto_variante_id IS NULL'
        )
        missing = cursor.fetchone()['n']
        if missing:
            raise RuntimeError(
                f'Quedaron {missing} ofertas sin variante; no se asumirá una variante ambigua.'
            )

        cursor.execute("""
            SELECT IS_NULLABLE FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'ofertas'
              AND COLUMN_NAME = 'producto_variante_id'
        """)
        if cursor.fetchone()['IS_NULLABLE'] == 'YES':
            cursor.execute(
                'ALTER TABLE ofertas MODIFY producto_variante_id INT UNSIGNED NOT NULL'
            )

        cursor.execute("""
            SELECT INDEX_NAME FROM information_schema.STATISTICS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'ofertas'
        """)
        indexes = {row['INDEX_NAME'] for row in cursor.fetchall()}
        if 'uq_oferta_vendedor_producto' in indexes:
            cursor.execute(
                'ALTER TABLE ofertas DROP INDEX uq_oferta_vendedor_producto'
            )
        if 'uq_oferta_vendedor_variante' not in indexes:
            cursor.execute("""
                ALTER TABLE ofertas ADD UNIQUE INDEX uq_oferta_vendedor_variante
                    (vendedor_id, producto_variante_id)
            """)
    return updated


def main() -> int:
    connection = None
    mongo_client = None
    try:
        connection = connect_mysql()
        mongo_client, mongo = connect_mongo()
        backup = create_backup(connection, mongo)
        statements = ensure_mysql_structure(connection)
        created, registered = ensure_default_variants(connection, mongo)
        ensure_mongo_indexes(mongo)
        updated = backfill_offers(connection)
        print(f'Respaldo creado: {backup}')
        print(
            'Variantes dinámicas instaladas '
            f'({statements} sentencias, {created} documentos creados, '
            f'{registered} referencias registradas, {updated} ofertas enlazadas).'
        )
        return 0
    except Exception as exc:
        print(f'ERROR al instalar variantes dinámicas: {exc}', file=sys.stderr)
        return 1
    finally:
        if connection:
            connection.close()
        if mongo_client:
            mongo_client.close()


if __name__ == '__main__':
    raise SystemExit(main())
