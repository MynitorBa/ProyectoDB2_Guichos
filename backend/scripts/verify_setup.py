#!/usr/bin/env python3
"""Verifica servicios, FKs de Fase 1 y referencias MySQL ↔ MongoDB."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import pymysql
from pymongo import MongoClient
from bson import ObjectId
from dotenv import load_dotenv
from app.core.security import verify_password

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
    offer_projections = []
    registry_refs = []
    variant_registry_refs = []

    # ── MySQL ─────────────────────────────────────────────────────────────────
    try:
        conn = pymysql.connect(host=MYSQL_HOST, port=MYSQL_PORT, db=MYSQL_DB,
                               user=MYSQL_USER, password=MYSQL_PASS,
                               charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor)
        with conn.cursor() as cur:
            cur.execute('SELECT COUNT(*) AS n FROM usuarios')
            print(f'MySQL usuarios: {cur.fetchone()["n"]}')
            cur.execute("""
                SELECT u.id, u.password_hash, u.estado,
                       GROUP_CONCAT(r.nombre ORDER BY r.nombre) AS roles
                FROM usuarios u
                LEFT JOIN usuario_rol ur ON ur.usuario_id = u.id
                LEFT JOIN roles r ON r.id = ur.rol_id
                WHERE u.email = 'admin@tiendaya.gt'
                GROUP BY u.id, u.password_hash, u.estado
            """)
            admin = cur.fetchone()
            admin_roles = set((admin.get('roles') or '').split(',')) if admin else set()
            if not admin:
                print('MySQL credenciales: falta admin@tiendaya.gt')
                ok = False
            elif admin['estado'] != 'activo':
                print(f"MySQL credenciales: administrador en estado {admin['estado']}")
                ok = False
            elif 'administrador' not in admin_roles:
                print('MySQL credenciales: el usuario de prueba no tiene rol administrador')
                ok = False
            elif not verify_password('password123', admin['password_hash']):
                print('MySQL credenciales: la contraseña documentada no coincide con el seed')
                ok = False
            else:
                print('MySQL credenciales: administrador de prueba verificado')
            cur.execute('SELECT COUNT(*) AS n FROM producto_referencias')
            n_productos_mysql = cur.fetchone()['n']
            print(f'MySQL referencias de producto: {n_productos_mysql}')
            cur.execute('SELECT COUNT(*) AS n FROM pedidos')
            print(f'MySQL pedidos:   {cur.fetchone()["n"]}')

            required_fks = {
                'fk_mi_pedido', 'fk_mi_usuario',
                'fk_notif_usuario', 'fk_notif_pedido',
            }
            cur.execute(
                """
                SELECT CONSTRAINT_NAME
                FROM information_schema.REFERENTIAL_CONSTRAINTS
                WHERE CONSTRAINT_SCHEMA = %s
                """,
                (MYSQL_DB,),
            )
            installed_fks = {row['CONSTRAINT_NAME'] for row in cur.fetchall()}
            missing_fks = sorted(required_fks - installed_fks)
            if missing_fks:
                print(f'MySQL Fase 1: FKs faltantes: {", ".join(missing_fks)}')
                ok = False
            else:
                print('MySQL Fase 1: FKs instaladas')

            phase2_tables = {
                'ofertas', 'oferta_precios_historial',
                'pedido_vendedores', 'pedido_direcciones', 'outbox_eventos',
            }
            cur.execute("""
                SELECT TABLE_NAME
                FROM information_schema.TABLES
                WHERE TABLE_SCHEMA = %s
            """, (MYSQL_DB,))
            installed_tables = {row['TABLE_NAME'] for row in cur.fetchall()}
            missing_tables = sorted(phase2_tables - installed_tables)

            required_columns = {
                ('inventario', 'oferta_id'),
                ('pedido_lineas', 'pedido_vendedor_id'),
                ('pedido_lineas', 'oferta_id'),
                ('pedido_lineas', 'sku_snapshot'),
                ('pedido_lineas', 'vendedor_nombre_snapshot'),
            }
            cur.execute("""
                SELECT TABLE_NAME, COLUMN_NAME
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = %s
            """, (MYSQL_DB,))
            installed_columns = {
                (row['TABLE_NAME'], row['COLUMN_NAME']) for row in cur.fetchall()
            }
            missing_columns = sorted(required_columns - installed_columns)

            phase2_fks = {
                'fk_oferta_vendedor', 'fk_oph_oferta', 'fk_oph_usuario',
                'fk_pv_pedido', 'fk_pv_vendedor', 'fk_pd_pedido',
                'fk_inv_oferta', 'fk_pl_pedido_vendedor', 'fk_pl_oferta',
            }
            missing_phase2_fks = sorted(phase2_fks - installed_fks)

            if missing_tables or missing_columns or missing_phase2_fks:
                if missing_tables:
                    print(f'MySQL Fase 2: tablas faltantes: {", ".join(missing_tables)}')
                if missing_columns:
                    print(f'MySQL Fase 2: columnas faltantes: {missing_columns}')
                if missing_phase2_fks:
                    print(f'MySQL Fase 2: FKs faltantes: {", ".join(missing_phase2_fks)}')
                ok = False
            else:
                print('MySQL Fase 2: estructura aditiva instalada')

            phase3_checks = {
                'referencias sin oferta': """
                    SELECT COUNT(*) AS n
                    FROM producto_referencias p
                    LEFT JOIN ofertas o ON o.producto_ref = p.producto_ref
                    WHERE o.id IS NULL
                """,
                'ofertas sin precio vigente': """
                    SELECT COUNT(*) AS n
                    FROM ofertas o
                    LEFT JOIN oferta_precios_historial h
                      ON h.oferta_id = o.id AND h.vigente_hasta IS NULL
                    WHERE h.id IS NULL
                """,
                'inventarios sin oferta': """
                    SELECT COUNT(*) AS n
                    FROM inventario WHERE oferta_id IS NULL
                """,
                'lineas incompletas': """
                    SELECT COUNT(*) AS n
                    FROM pedido_lineas
                    WHERE oferta_id IS NULL OR pedido_vendedor_id IS NULL
                       OR sku_snapshot IS NULL
                       OR vendedor_nombre_snapshot IS NULL
                """,
                'pedidos sin snapshot de direccion': """
                    SELECT COUNT(*) AS n
                    FROM pedidos pe
                    LEFT JOIN pedido_direcciones pd ON pd.pedido_id = pe.id
                    WHERE pd.pedido_id IS NULL
                """,
            }
            phase3_errors = []
            for label, query in phase3_checks.items():
                cur.execute(query)
                count = cur.fetchone()['n']
                if count:
                    phase3_errors.append(f'{label}: {count}')
            if phase3_errors:
                print(f'MySQL Fase 3: {"; ".join(phase3_errors)}')
                ok = False
            else:
                cur.execute('SELECT COUNT(*) AS n FROM ofertas')
                offer_count = cur.fetchone()['n']
                cur.execute('SELECT COUNT(*) AS n FROM pedido_vendedores')
                vendor_order_count = cur.fetchone()['n']
                print(
                    'MySQL Fase 3: backfill completo '
                    f'({offer_count} ofertas, {vendor_order_count} subpedidos)'
                )

            cur.execute("""
                SELECT COUNT(*) AS n
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = %s
                  AND TABLE_NAME = 'carrito_items'
                  AND COLUMN_NAME = 'oferta_id'
            """, (MYSQL_DB,))
            phase4_column = cur.fetchone()['n'] == 1
            phase4_fk = 'fk_ci_oferta' in installed_fks
            cur.execute("""
                SELECT COUNT(*) AS n
                FROM information_schema.STATISTICS
                WHERE TABLE_SCHEMA = %s
                  AND TABLE_NAME = 'carrito_items'
                  AND INDEX_NAME = 'uq_ci_carrito_oferta'
            """, (MYSQL_DB,))
            phase4_unique = cur.fetchone()['n'] > 0
            cur.execute("""
                SELECT COUNT(*) AS n
                FROM carrito_items ci
                JOIN carritos c ON c.id = ci.carrito_id
                WHERE c.estado = 'activo' AND ci.oferta_id IS NULL
            """)
            pending_cart_items = cur.fetchone()['n']
            if not (phase4_column and phase4_fk and phase4_unique) or pending_cart_items:
                print(
                    'MySQL Fase 4: contrato de carrito incompleto '
                    f'(columna={phase4_column}, fk={phase4_fk}, '
                    f'unique={phase4_unique}, pendientes={pending_cart_items})'
                )
                ok = False
            else:
                print('MySQL Fase 4: carrito identificado por oferta')

            cur.execute("""
                SELECT estado, COUNT(*) AS n
                FROM outbox_eventos
                GROUP BY estado
            """)
            outbox_counts = {row['estado']: row['n'] for row in cur.fetchall()}
            cur.execute("""
                SELECT COUNT(*) AS n
                FROM outbox_eventos
                WHERE estado = 'error' AND intentos >= 5
            """)
            exhausted = cur.fetchone()['n']
            if exhausted:
                print(f'MySQL Fase 5: {exhausted} eventos agotaron sus reintentos')
                ok = False
            else:
                print(f'MySQL Fase 5: outbox saludable {outbox_counts}')

            phase6b_fks = {
                'fk_res_producto_referencia', 'fk_mi_inventario',
            }
            phase6b_columns = {
                ('resenas', 'producto_referencia_id'),
                ('movimientos_inventario', 'inventario_id'),
            }
            phase6b_errors = []
            if 'producto_referencias' not in installed_tables:
                phase6b_errors.append('falta tabla producto_referencias')
            missing_phase6b_columns = sorted(
                phase6b_columns - installed_columns
            )
            if missing_phase6b_columns:
                phase6b_errors.append(
                    f'columnas faltantes: {missing_phase6b_columns}'
                )
            missing_phase6b_fks = sorted(phase6b_fks - installed_fks)
            if missing_phase6b_fks:
                phase6b_errors.append(
                    f'FKs faltantes: {missing_phase6b_fks}'
                )
            if not phase6b_errors:
                checks = {
                    'referencias inválidas': """
                        SELECT COUNT(*) AS n FROM producto_referencias
                        WHERE producto_ref IS NULL OR CHAR_LENGTH(producto_ref) <> 24
                    """,
                    'resenas sin referencia': """
                        SELECT COUNT(*) AS n FROM resenas
                        WHERE producto_referencia_id IS NULL
                    """,
                    'movimientos sin inventario': """
                        SELECT COUNT(*) AS n FROM movimientos_inventario
                        WHERE inventario_id IS NULL
                    """,
                }
                for label, query in checks.items():
                    cur.execute(query)
                    count = cur.fetchone()['n']
                    if count:
                        phase6b_errors.append(f'{label}: {count}')
            if phase6b_errors:
                print(f'MySQL Fase 6B: {"; ".join(phase6b_errors)}')
                ok = False
            else:
                cur.execute('SELECT COUNT(*) AS n FROM producto_referencias')
                registry_count = cur.fetchone()['n']
                print(
                    'MySQL Fase 6B: referencias y FKs nuevas completas '
                    f'({registry_count} productos)'
                )

            phase7_fks = {
                'fk_pr_categoria', 'fk_oferta_producto_referencia',
            }
            phase7_errors = []
            if ('producto_referencias', 'categoria_id') not in installed_columns:
                phase7_errors.append('falta producto_referencias.categoria_id')
            missing_phase7_fks = sorted(phase7_fks - installed_fks)
            if missing_phase7_fks:
                phase7_errors.append(f'FKs faltantes: {missing_phase7_fks}')
            if not phase7_errors:
                checks = {
                    'referencias sin categoría': """
                        SELECT COUNT(*) AS n FROM producto_referencias pr
                        LEFT JOIN categorias c ON c.id = pr.categoria_id
                        WHERE c.id IS NULL
                    """,
                    'ofertas sin referencia registrada': """
                        SELECT COUNT(*) AS n FROM ofertas o
                        LEFT JOIN producto_referencias pr
                          ON pr.producto_ref = o.producto_ref
                        WHERE pr.id IS NULL
                    """,
                }
                for label, query in checks.items():
                    cur.execute(query)
                    count = cur.fetchone()['n']
                    if count:
                        phase7_errors.append(f'{label}: {count}')
            if phase7_errors:
                print(f'MySQL Fase 7: {"; ".join(phase7_errors)}')
                ok = False
            else:
                cur.execute("""
                    SELECT pr.id, pr.producto_ref, c.slug AS categoria_slug
                    FROM producto_referencias pr
                    JOIN categorias c ON c.id = pr.categoria_id
                    ORDER BY pr.id
                """)
                registry_refs = cur.fetchall()
                print('MySQL Fase 7: categorías, referencias y ofertas enlazadas')

            catalog_extension_tables = {
                'producto_imagenes', 'producto_referencia_categorias',
            }
            missing_extension_tables = sorted(
                catalog_extension_tables - installed_tables
            )
            extension_fks = {
                'fk_pi_referencia', 'fk_prc_referencia', 'fk_prc_categoria',
            }
            missing_extension_fks = sorted(extension_fks - installed_fks)
            extension_errors = []
            if ('categorias', 'sku_prefix') not in installed_columns:
                extension_errors.append('falta categorias.sku_prefix')
            if missing_extension_tables:
                extension_errors.append(
                    f'tablas faltantes: {missing_extension_tables}'
                )
            if missing_extension_fks:
                extension_errors.append(f'FKs faltantes: {missing_extension_fks}')
            if not extension_errors:
                cur.execute("""
                    SELECT COUNT(*) AS n
                    FROM producto_referencias pr
                    LEFT JOIN producto_referencia_categorias prc
                      ON prc.producto_referencia_id = pr.id
                     AND prc.es_principal = 1
                    WHERE prc.id IS NULL
                """)
                missing_primary = cur.fetchone()['n']
                if missing_primary:
                    extension_errors.append(
                        f'referencias sin categoría principal: {missing_primary}'
                    )
            if extension_errors:
                print(f'MySQL catálogo extendido: {"; ".join(extension_errors)}')
                ok = False
            else:
                print('MySQL catálogo extendido: imágenes y categorías múltiples listas')

            request_tables = {
                'solicitudes_catalogo', 'solicitud_catalogo_categorias',
                'solicitud_catalogo_imagenes',
            }
            request_fks = {
                'fk_sc_vendedor', 'fk_sc_producto_solicitado',
                'fk_sc_revisada_por', 'fk_sc_producto_resultado',
                'fk_sc_oferta_resultado', 'fk_scc_solicitud',
                'fk_scc_categoria', 'fk_sci_solicitud', 'fk_sci_imagen',
                'fk_pi_subida_por',
            }
            request_errors = []
            missing_request_tables = sorted(request_tables - installed_tables)
            missing_request_fks = sorted(request_fks - installed_fks)
            if ('producto_imagenes', 'subida_por') not in installed_columns:
                request_errors.append('falta producto_imagenes.subida_por')
            if missing_request_tables:
                request_errors.append(f'tablas faltantes: {missing_request_tables}')
            if missing_request_fks:
                request_errors.append(f'FKs faltantes: {missing_request_fks}')
            if request_errors:
                print(f'MySQL solicitudes de catálogo: {"; ".join(request_errors)}')
                ok = False
            else:
                print('MySQL solicitudes de catálogo: estructura y propiedad de imágenes listas')

            temporal_tables = {
                'oferta_estados_historial', 'inventario_saldos_historial',
            }
            temporal_errors = []
            missing_temporal_tables = sorted(temporal_tables - installed_tables)
            if missing_temporal_tables:
                temporal_errors.append(
                    f'tablas faltantes: {missing_temporal_tables}'
                )
            else:
                temporal_checks = {
                    'ofertas sin estado temporal vigente': """
                        SELECT COUNT(*) AS n FROM ofertas o
                        LEFT JOIN oferta_estados_historial h
                          ON h.oferta_id = o.id AND h.vigente_hasta IS NULL
                        WHERE h.id IS NULL
                    """,
                    'inventarios sin saldo temporal vigente': """
                        SELECT COUNT(*) AS n FROM inventario i
                        LEFT JOIN inventario_saldos_historial h
                          ON h.inventario_id = i.id AND h.vigente_hasta IS NULL
                        WHERE h.id IS NULL
                    """,
                }
                for label, query in temporal_checks.items():
                    cur.execute(query)
                    count = cur.fetchone()['n']
                    if count:
                        temporal_errors.append(f'{label}: {count}')
            if temporal_errors:
                print(f'MySQL historial temporal: {"; ".join(temporal_errors)}')
                ok = False
            else:
                print('MySQL historial temporal: ofertas e inventarios completos')

            variant_errors = []
            if 'producto_variante_referencias' not in installed_tables:
                variant_errors.append('falta tabla producto_variante_referencias')
            if ('ofertas', 'producto_variante_id') not in installed_columns:
                variant_errors.append('falta ofertas.producto_variante_id')
            if (
                'solicitudes_catalogo', 'producto_variante_id_solicitado'
            ) not in installed_columns:
                variant_errors.append(
                    'falta solicitudes_catalogo.producto_variante_id_solicitado'
                )
            missing_variant_fks = sorted(
                {
                    'fk_pvr_producto', 'fk_oferta_variante',
                    'fk_sc_variante_solicitada',
                } - installed_fks
            )
            if missing_variant_fks:
                variant_errors.append(f'FKs faltantes: {missing_variant_fks}')
            cur.execute("""
                SELECT COUNT(*) AS n
                FROM information_schema.STATISTICS
                WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'ofertas'
                  AND INDEX_NAME = 'uq_oferta_vendedor_variante'
                  AND NON_UNIQUE = 0
            """)
            if not cur.fetchone()['n']:
                variant_errors.append('falta único uq_oferta_vendedor_variante')
            if not variant_errors:
                checks = {
                    'ofertas sin variante': """
                        SELECT COUNT(*) AS n FROM ofertas
                        WHERE producto_variante_id IS NULL
                    """,
                    'ofertas enlazadas a variante de otro producto': """
                        SELECT COUNT(*) AS n
                        FROM ofertas o
                        JOIN producto_variante_referencias pvr
                          ON pvr.id = o.producto_variante_id
                        JOIN producto_referencias pr
                          ON pr.id = pvr.producto_referencia_id
                        WHERE pr.producto_ref <> o.producto_ref
                    """,
                    'productos sin variante registrada': """
                        SELECT COUNT(*) AS n
                        FROM producto_referencias pr
                        LEFT JOIN producto_variante_referencias pvr
                          ON pvr.producto_referencia_id = pr.id
                        WHERE pvr.id IS NULL
                    """,
                }
                for label, query in checks.items():
                    cur.execute(query)
                    count = cur.fetchone()['n']
                    if count:
                        variant_errors.append(f'{label}: {count}')
                cur.execute("""
                    SELECT pvr.id, pvr.variante_ref, pr.producto_ref
                    FROM producto_variante_referencias pvr
                    JOIN producto_referencias pr
                      ON pr.id = pvr.producto_referencia_id
                    ORDER BY pvr.id
                """)
                variant_registry_refs = cur.fetchall()
            if variant_errors:
                print(f'MySQL variantes dinámicas: {"; ".join(variant_errors)}')
                ok = False
            else:
                print(
                    'MySQL variantes dinámicas: registro y ofertas enlazados '
                    f'({len(variant_registry_refs)} variantes)'
                )

            legacy_tables = {'productos'} & installed_tables
            legacy_columns = {
                ('carrito_items', 'producto_id'),
                ('inventario', 'producto_id'),
                ('movimientos_inventario', 'producto_id'),
                ('pedido_lineas', 'producto_id'),
                ('resenas', 'producto_id'),
            } & installed_columns
            cur.execute("""
                SELECT COUNT(*) AS n
                FROM information_schema.ROUTINES
                WHERE ROUTINE_SCHEMA = %s AND ROUTINE_NAME = 'sp_crear_pedido'
            """, (MYSQL_DB,))
            legacy_procedure = cur.fetchone()['n']
            if legacy_tables or legacy_columns or legacy_procedure:
                print(
                    'MySQL Fase 6B: objetos heredados restantes '
                    f'(tablas={sorted(legacy_tables)}, '
                    f'columnas={sorted(legacy_columns)}, '
                    f'procedimiento={legacy_procedure})'
                )
                ok = False
            else:
                print('MySQL Fase 6B: corte físico completo')

            cur.execute("""
                WITH oferta_stock AS (
                  SELECT o.id, o.producto_ref, o.precio_actual,
                         v.nombre_comercial,
                         COALESCE(SUM(
                           i.cantidad_disponible - i.cantidad_reservada
                         ), 0) AS stock
                  FROM ofertas o
                  JOIN vendedores v ON v.id = o.vendedor_id
                  LEFT JOIN inventario i ON i.oferta_id = o.id
                  WHERE o.estado = 'activa'
                  GROUP BY o.id, o.producto_ref, o.precio_actual,
                           v.nombre_comercial
                ), ranked AS (
                  SELECT oferta_stock.*,
                         COUNT(*) OVER (PARTITION BY producto_ref) AS ofertas_count,
                         ROW_NUMBER() OVER (
                           PARTITION BY producto_ref
                           ORDER BY (stock > 0) DESC, precio_actual, id
                         ) AS rn
                  FROM oferta_stock
                )
                SELECT producto_ref, id AS oferta_id, precio_actual,
                       nombre_comercial, stock, ofertas_count
                FROM ranked WHERE rn = 1
            """)
            offer_projections = cur.fetchall()

            orphan_queries = {
                'movimientos.pedido_id': """
                    SELECT COUNT(*) AS n
                    FROM movimientos_inventario mi
                    LEFT JOIN pedidos p ON p.id = mi.pedido_id
                    WHERE mi.pedido_id IS NOT NULL AND p.id IS NULL
                """,
                'movimientos.usuario_id': """
                    SELECT COUNT(*) AS n
                    FROM movimientos_inventario mi
                    LEFT JOIN usuarios u ON u.id = mi.usuario_id
                    WHERE mi.usuario_id IS NOT NULL AND u.id IS NULL
                """,
                'notificaciones.usuario_id': """
                    SELECT COUNT(*) AS n
                    FROM notificaciones n
                    LEFT JOIN usuarios u ON u.id = n.usuario_id
                    WHERE u.id IS NULL
                """,
                'notificaciones.pedido_id': """
                    SELECT COUNT(*) AS n
                    FROM notificaciones n
                    LEFT JOIN pedidos p ON p.id = n.pedido_id
                    WHERE n.pedido_id IS NOT NULL AND p.id IS NULL
                """,
            }
            for label, query in orphan_queries.items():
                cur.execute(query)
                count = cur.fetchone()['n']
                if count:
                    print(f'MySQL: {count} referencias huérfanas en {label}')
                    ok = False

            # Referencias huérfanas: pedido_lineas con producto_ref que no existe en Mongo
            cur.execute("SELECT id, producto_ref FROM pedido_lineas WHERE producto_ref IS NOT NULL")
            refs = cur.fetchall()
        conn.close()
        print(f'MySQL: OK')
    except Exception as e:
        print(f'MySQL: ERROR — {e}')
        ok = False
        refs = []
        registry_refs = []
        variant_registry_refs = []

    # ── MongoDB ───────────────────────────────────────────────────────────────
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        client.server_info()
        mongo = client[MONGO_DB]
        n_mongo = mongo.productos.count_documents({})
        n_eventos = mongo.producto_eventos.count_documents({})
        print(f'MongoDB productos: {n_mongo}')
        print(f'MongoDB eventos:   {n_eventos}')

        operational_events = mongo.producto_eventos.count_documents({
            'tipo_evento': {'$in': ['PRECIO_ACTUALIZADO', 'DISPONIBILIDAD_CAMBIADA']}
        })
        events_before_creation = 0
        for product_id in mongo.producto_eventos.distinct('producto_id'):
            created = mongo.producto_eventos.find_one({
                'producto_id': product_id,
                'tipo_evento': 'PRODUCTO_CREADO',
            }, {'timestamp': 1})
            if created and created.get('timestamp'):
                events_before_creation += mongo.producto_eventos.count_documents({
                    'producto_id': product_id,
                    'timestamp': {'$lt': created['timestamp']},
                })
        if operational_events or events_before_creation:
            print(
                'MongoDB historial: separación pendiente '
                f'({operational_events} operativos, '
                f'{events_before_creation} anteriores a creación)'
            )
            ok = False
        else:
            print('MongoDB historial: únicamente eventos documentales coherentes')

        indexes = mongo.producto_eventos.index_information()
        outbox_index = indexes.get('uidx_evento_outbox', {})
        if not outbox_index.get('unique'):
            print('MongoDB Fase 5: falta índice único uidx_evento_outbox')
            ok = False
        else:
            print('MongoDB Fase 5: idempotencia por outbox_id instalada')

        projection_mismatches = 0
        for offer in offer_projections:
            try:
                doc = mongo.productos.find_one(
                    {'_id': ObjectId(offer['producto_ref'])},
                    {'precio': 1, 'stock': 1, 'vendedor_nombre': 1,
                     'oferta_id': 1, 'ofertas_count': 1},
                )
            except Exception:
                doc = None
            if (
                not doc
                or float(doc.get('precio', 0)) != float(offer['precio_actual'])
                or int(doc.get('stock', 0)) != int(offer['stock'])
                or doc.get('vendedor_nombre') != offer['nombre_comercial']
                or int(doc.get('oferta_id', 0)) != int(offer['oferta_id'])
                or int(doc.get('ofertas_count', 0)) != int(offer['ofertas_count'])
            ):
                projection_mismatches += 1
        if projection_mismatches:
            print(
                f'MongoDB Fase 5: {projection_mismatches} proyecciones '
                'pendientes o divergentes'
            )
            ok = False
        else:
            print('MongoDB Fase 5: proyecciones sincronizadas')

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

        registry_orphans = []
        category_mismatches = []
        for ref in registry_refs:
            try:
                document = mongo.productos.find_one(
                    {'_id': ObjectId(ref['producto_ref'])},
                    {'categoria.slug': 1},
                )
                if not document:
                    registry_orphans.append(ref)
                elif (
                    document.get('categoria', {}).get('slug')
                    != ref.get('categoria_slug')
                ):
                    category_mismatches.append(ref)
            except Exception:
                registry_orphans.append(ref)
        if registry_orphans:
            print(
                'MongoDB Fase 6B: '
                f'{len(registry_orphans)} referencias mínimas huérfanas'
            )
            ok = False
        else:
            print('MongoDB Fase 6B: 0 referencias mínimas huérfanas')
        if category_mismatches:
            print(
                'MongoDB Fase 7: '
                f'{len(category_mismatches)} categorías divergentes'
            )
            ok = False
        else:
            print('MongoDB Fase 7: categorías sincronizadas con MySQL')

        variant_indexes = mongo.producto_variantes.index_information()
        expected_variant_indexes = {
            'uidx_variante_producto_clave', 'uidx_variante_sku',
        }
        invalid_variant_indexes = sorted(
            name for name in expected_variant_indexes
            if not variant_indexes.get(name, {}).get('unique')
        )
        variant_orphans = []
        for ref in variant_registry_refs:
            try:
                document = mongo.producto_variantes.find_one(
                    {'_id': ObjectId(ref['variante_ref'])},
                    {'producto_ref': 1},
                )
            except Exception:
                document = None
            if not document or document.get('producto_ref') != ref['producto_ref']:
                variant_orphans.append(ref['id'])
        if invalid_variant_indexes or variant_orphans:
            print(
                'MongoDB variantes dinámicas: '
                f'índices inválidos={invalid_variant_indexes}, '
                f'referencias divergentes={len(variant_orphans)}'
            )
            ok = False
        else:
            print(
                'MongoDB variantes dinámicas: índices únicos y '
                'referencias sincronizadas'
            )

        client.close()
    except Exception as e:
        print(f'MongoDB: ERROR - {e}')
        ok = False

    print(f'\n{"[OK] Setup completo." if ok else "[ERROR] Hay problemas que corregir."}')
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
