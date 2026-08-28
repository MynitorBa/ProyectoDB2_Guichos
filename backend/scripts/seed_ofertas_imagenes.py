#!/usr/bin/env python3
"""
Seed: agrega >=2 ofertas por producto e imágenes a productos sin imagen.
Idempotente — usa INSERT IGNORE / upsert; no toca lógica de negocio.

Uso:
  python seed_ofertas_imagenes.py [--dry-run]
"""
import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pymysql
from dotenv import load_dotenv
from pymongo import MongoClient, UpdateOne

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / 'backend' / '.env')

MYSQL_CFG = dict(
    host=os.getenv('MYSQL_HOST', 'localhost'),
    port=int(os.getenv('MYSQL_PORT', 3307)),
    database=os.getenv('MYSQL_DB', 'tiendaya'),
    user=os.getenv('MYSQL_USER', 'tiendaya'),
    password=os.getenv('MYSQL_PASSWORD', 'tiendaya123'),
    charset='utf8mb4',
    cursorclass=pymysql.cursors.DictCursor,
    autocommit=False,
)
MONGO_URI = os.getenv('MONGO_URI', 'mongodb://admin:adminpassword@localhost:27017/tiendaya?authSource=admin')
MONGO_DB  = os.getenv('MONGO_DB', 'tiendaya')

# Vendedor secundario por vendedor principal
# 1=TechZone, 2=ModaExpress, 3=HogarIdeal, 4=LibroMundo, 5=SportMax
SECOND_VENDOR = {1: 3, 2: 4, 3: 5, 4: 2, 5: 1}

# Precio del vendedor secundario: 5% más barato (competencia de precio)
SECOND_PRICE_FACTOR = 0.95

# ─── Imágenes por SKU ─────────────────────────────────────────────────────────
# Libros: Open Library CDN (basado en ISBN, muy estable).
# Electrónica: CDNs oficiales de fabricantes.
# Resto: placehold.co con colores representativos del producto.
IMAGES: dict[str, str] = {
    # ── LIBROS (Open Library — garantizadas por ISBN) ─────────────────────────
    'LIBRO-FIC-001': 'https://covers.openlibrary.org/b/isbn/9780307474728-L.jpg',
    'LIBRO-TEC-001': 'https://covers.openlibrary.org/b/isbn/9780132350884-L.jpg',
    'LIBRO-TEC-002': 'https://covers.openlibrary.org/b/isbn/9781449373320-L.jpg',
    'LIBRO-EDU-001': 'https://covers.openlibrary.org/b/isbn/9780073523323-L.jpg',
    'LIBRO-FIC-002': 'https://covers.openlibrary.org/b/isbn/9788401337208-L.jpg',
    'LIBRO-TEC-003': 'https://covers.openlibrary.org/b/isbn/9781593279288-L.jpg',
    'LIBRO-FIC-003': 'https://covers.openlibrary.org/b/isbn/9788498383638-L.jpg',
    'LIBRO-AUT-001': 'https://covers.openlibrary.org/b/isbn/9788497774338-L.jpg',

    # ── COMPUTADORAS ─────────────────────────────────────────────────────────
    'TECH-LAP-001': 'https://i.dell.com/is/image/DellContent/content/dam/ss2/product-images/dell-client-products/notebooks/inspiron-notebooks/inspiron-15-3520/media-gallery/black/notebook-inspiron-15-3520-t-black-gallery-1.psd?fmt=png,rgb&wid=800&hei=600',
    'TECH-LAP-002': 'https://ssl-product-images.www8-hp.com/digmedialib/prodimg/knowledgebase/c08320375.png',
    'TECH-LAP-003': 'https://www.apple.com/newsroom/images/product/mac/standard/Apple_MacBook-Air_M2-chip_06062022_big.jpg.large.jpg',
    'TECH-LAP-004': 'https://psrefimage.lenovo.com/Lenovo_IdeaPad_3_Gen_7_15inch_Intel_CT1_01.png',
    'TECH-LAP-005': 'https://dlcdnwebimgs.asus.com/files/media/C9B7F3E2-F53D-4D33-A6DC-A4C2CF4E4D2E/1x/img/kv/kv.png',

    # ── CELULARES ────────────────────────────────────────────────────────────
    'TECH-CEL-001': 'https://images.samsung.com/is/image/samsung/p6pim/latin/sm-a546blbdltl/gallery/latin-galaxy-a54-5g-sm-a546-sm-a546blbdltl-534612680',
    'TECH-CEL-002': 'https://www.apple.com/newsroom/images/product/iphone/standard/Apple_iPhone-14_2-Up_Midnight_09072022_big.jpg.large.jpg',
    'TECH-CEL-003': 'https://i02.appmifile.com/mi-com-product/fly-birds/redmi-note-12/pc/hero.png',
    'TECH-CEL-004': 'https://motorola-global-portal.imagesbi.com/media/catalog/product/cache/600x800/motorola-edge40.png',

    # ── AUDIO ────────────────────────────────────────────────────────────────
    'TECH-AUD-001': 'https://www.sony.com/image/5d02da5df552836db894cead401a0abe?fmt=png-alpha&wid=800',
    'TECH-AUD-002': 'https://www.jbl.com/dw/image/v2/AAUJ_PRD/on/demandware.static/-/Sites-masterCatalog_Harman/default/dwf5e9c0e7/JBL_CHARGE5_Hero_Black_32581.png',
    'TECH-AUD-003': 'https://www.apple.com/newsroom/images/product/airpods/standard/Apple-AirPods-Pro-2nd-gen-hero-220907_big.jpg.large.jpg',

    # ── MONITOR Y PERIFÉRICOS ─────────────────────────────────────────────────
    'TECH-MON-001': 'https://www.lg.com/us/images/monitors/md05003388/gallery/B-01.jpg',
    'TECH-TEC-001': 'https://cdn.shopify.com/s/files/1/0059/0630/1017/products/K2-V2-WL-ISO-Alum_1200x.jpg',
    'TECH-RAT-001': 'https://resource.logitech.com/content/dam/logitech/en/products/mice/mx-master-3s/gallery/mx-master-3s-mouse-top-view-graphite.png',

    # ── ROPA: CAMISAS ────────────────────────────────────────────────────────
    'ROPA-CAM-001': 'https://placehold.co/800x600/0d2b6e/ffffff?text=Camisa+Oxford+Azul+Marino',
    'ROPA-CAM-002': 'https://placehold.co/800x600/8b2020/ffffff?text=Camisa+Cuadros+Franela',
    'ROPA-CAM-003': 'https://placehold.co/800x600/e8c4b8/333333?text=Blusa+Floral+Mujer',
    'ROPA-CAM-004': 'https://placehold.co/800x600/f0f0f0/333333?text=Polo+Lacoste+Blanco',
    'ROPA-CAM-005': 'https://placehold.co/800x600/f5f5ee/333333?text=Camisa+Lino+Blanca',
    'ROPA-CAM-006': 'https://placehold.co/800x600/1a1a1a/ffffff?text=Blusa+Seda+Negra',

    # ── ROPA: PANTALONES ────────────────────────────────────────────────────
    'ROPA-PAN-001': 'https://placehold.co/800x600/1a3a6e/ffffff?text=Jeans+Slim+Fit+Azul',
    'ROPA-PAN-002': 'https://placehold.co/800x600/111111/ffffff?text=Jean+Skinny+Negro',
    'ROPA-PAN-003': 'https://placehold.co/800x600/c8b48a/333333?text=Pantalon+Cargo+Beige',

    # ── ROPA: CALZADO ────────────────────────────────────────────────────────
    'ROPA-CAL-001': 'https://placehold.co/800x600/f5f5f5/333333?text=Nike+Air+Force+1',
    'ROPA-CAL-002': 'https://placehold.co/800x600/111111/ffffff?text=Zapato+Oxford+Negro',

    # ── HOGAR ────────────────────────────────────────────────────────────────
    'HOGAR-COC-001': 'https://placehold.co/800x600/2a2a2a/ffffff?text=Licuadora+Oster+600W',
    'HOGAR-COC-002': 'https://placehold.co/800x600/c0392b/ffffff?text=Nespresso+Essenza+Mini',
    'HOGAR-COC-003': 'https://placehold.co/800x600/b0b0b0/333333?text=Ollas+Tramontina+5pz',
    'HOGAR-MUE-001': 'https://placehold.co/800x600/1a1a1a/ffffff?text=Silla+Ergonomica',
    'HOGAR-MUE-002': 'https://placehold.co/800x600/7a5230/ffffff?text=Escritorio+Esquinero+140cm',
    'HOGAR-DEC-001': 'https://placehold.co/800x600/f0f0f0/333333?text=Lampara+LED+Moderna',
    'HOGAR-DEC-002': 'https://placehold.co/800x600/c8955a/ffffff?text=Cuadro+Canvas+60x90',

    # ── ALIMENTOS ────────────────────────────────────────────────────────────
    'ALI-CAF-001': 'https://placehold.co/800x600/3d1e0a/ffffff?text=Cafe+Huehuetenango+500g',
    'ALI-CHO-001': 'https://placehold.co/800x600/3d1c02/ffffff?text=Chocolate+Negro+70%25',
    'ALI-MIE-001': 'https://placehold.co/800x600/f5a623/333333?text=Miel+de+Abeja+1kg',
    'ALI-SAL-001': 'https://placehold.co/800x600/2a1a2e/ffffff?text=Sal+Negra+Himalaya+250g',
    'ALI-GRA-001': 'https://placehold.co/800x600/c8a87a/333333?text=Granola+Artesanal+400g',

    # ── DEPORTES ─────────────────────────────────────────────────────────────
    'DEP-FUT-001': 'https://placehold.co/800x600/1a3a8a/ffffff?text=Balon+Nike+Premier+League',
    'DEP-GIM-001': 'https://placehold.co/800x600/2a2a2a/ffffff?text=Mancuernas+10kg+Par',
    'DEP-GIM-002': 'https://placehold.co/800x600/7b2fbe/ffffff?text=Colchoneta+Yoga+6mm',
    'DEP-NAT-001': 'https://placehold.co/800x600/1565c0/ffffff?text=Gafas+Natacion+Speedo',
    'DEP-CIC-001': 'https://placehold.co/800x600/1a1a1a/ffffff?text=Casco+MTB+Giro+Fixture',
    'DEP-ROP-001': 'https://placehold.co/800x600/111122/ffffff?text=Licra+Deportiva+Mujer',
    'DEP-ROP-002': 'https://placehold.co/800x600/1a3a6e/ffffff?text=Short+Deportivo+Hombre',

    # ── JUGUETES ─────────────────────────────────────────────────────────────
    'JUG-ARM-001': 'https://placehold.co/800x600/d32f2f/ffffff?text=LEGO+Dragon+31112',
    'JUG-MAD-001': 'https://placehold.co/800x600/8b5e3c/ffffff?text=Rompecabezas+Madera+40pz',
    'JUG-ELE-001': 'https://placehold.co/800x600/1a1a3a/ffffff?text=Dron+RC+720p',
    'JUG-MUÑ-001': 'https://placehold.co/800x600/e91e8c/ffffff?text=Muneca+Articulada+30cm',
    'JUG-CAR-001': 'https://placehold.co/800x600/e53935/ffffff?text=Pista+Hot+Wheels+60pz',

    # ── HERRAMIENTAS ─────────────────────────────────────────────────────────
    'HER-TAL-001': 'https://placehold.co/800x600/f9a825/333333?text=Taladro+DeWalt+750W',
    'HER-MED-001': 'https://placehold.co/800x600/e65100/ffffff?text=Multimetro+Fluke+115',
    'HER-SAR-001': 'https://placehold.co/800x600/212121/ffffff?text=Sargentos+Presion+12pul',
    'HER-MAN-001': 'https://placehold.co/800x600/b0bec5/333333?text=Llaves+Combinadas+12pz',
    'HER-NIV-001': 'https://placehold.co/800x600/2e7d32/ffffff?text=Nivel+Laser+3+Lineas',
    'HER-ESM-001': 'https://placehold.co/800x600/263238/ffffff?text=Esmeril+Banco+200W',
    'HER-SIE-001': 'https://placehold.co/800x600/c62828/ffffff?text=Sierra+Circular+1200W',
}


def main(dry_run: bool) -> None:
    tag = '[DRY-RUN] ' if dry_run else ''
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    conn  = pymysql.connect(**MYSQL_CFG)
    mongo = MongoClient(MONGO_URI)[MONGO_DB]

    try:
        # ── 1. Cargar datos actuales ──────────────────────────────────────────
        with conn.cursor() as cur:
            cur.execute("SELECT id, producto_ref FROM producto_referencias")
            ref_by_mongo_id = {r['producto_ref']: r['id'] for r in cur.fetchall()}

            cur.execute(
                "SELECT producto_ref, vendedor_id, sku, precio_actual FROM ofertas"
            )
            offers_by_ref: dict[str, list] = {}
            for o in cur.fetchall():
                offers_by_ref.setdefault(o['producto_ref'], []).append(o)

        mongo_products = {str(p['_id']): p for p in mongo.productos.find({})}

        # ── 2. Segunda oferta por producto ────────────────────────────────────
        added_offers = 0
        for prod_ref, offers in offers_by_ref.items():
            if len(offers) >= 2:
                continue

            primary      = offers[0]
            sec_vendor   = SECOND_VENDOR.get(primary['vendedor_id'])
            if sec_vendor is None:
                continue

            # Verificar que no exista ya una oferta de ese vendedor para este producto
            already_exists = any(
                o['vendedor_id'] == sec_vendor for o in offers
            )
            if already_exists:
                continue

            new_sku   = f"{primary['sku']}-V{sec_vendor}"
            new_price = round(float(primary['precio_actual']) * SECOND_PRICE_FACTOR, 2)

            print(f"{tag}  Oferta: {new_sku} | vendedor {sec_vendor} | Q{new_price:.2f}")

            if dry_run:
                added_offers += 1
                continue

            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT IGNORE INTO ofertas
                        (producto_ref, vendedor_id, sku, precio_actual, estado, version)
                    VALUES (%s, %s, %s, %s, 'activa', 1)
                    """,
                    (prod_ref, sec_vendor, new_sku, new_price),
                )
                oferta_id = cur.lastrowid
                if oferta_id == 0:
                    # Ya existía (IGNORE la saltó)
                    continue

                # Inventario
                cur.execute(
                    """
                    INSERT INTO inventario
                        (oferta_id, cantidad_disponible, cantidad_reservada, punto_reorden)
                    VALUES (%s, 10, 0, 3)
                    """,
                    (oferta_id,),
                )
                inventario_id = cur.lastrowid

                # Historial de precio (el registro vigente: vigente_hasta = NULL)
                cur.execute(
                    """
                    INSERT INTO oferta_precios_historial
                        (oferta_id, precio, moneda, vigente_desde, cambiado_por, motivo)
                    VALUES (%s, %s, 'GTQ', %s, NULL, 'Precio inicial — seed ofertas')
                    """,
                    (oferta_id, new_price, now),
                )

                # Historial de estado (estado vigente: vigente_hasta = NULL)
                cur.execute(
                    """
                    INSERT INTO oferta_estados_historial
                        (oferta_id, vendedor_id, sku, estado, vigente_desde, motivo)
                    VALUES (%s, %s, %s, 'activa', %s, 'Estado inicial — seed ofertas')
                    """,
                    (oferta_id, sec_vendor, new_sku, now),
                )

                # Historial de inventario
                cur.execute(
                    """
                    INSERT INTO inventario_saldos_historial
                        (inventario_id, cantidad_disponible, cantidad_reservada, vigente_desde, motivo)
                    VALUES (%s, 10, 0, %s, 'Saldo inicial — seed ofertas')
                    """,
                    (inventario_id, now),
                )

                added_offers += 1

        if not dry_run:
            conn.commit()

        # ── 3. Imágenes faltantes en MongoDB ──────────────────────────────────
        image_ops   = []
        added_imgs  = 0
        skipped_imgs = 0

        for prod_ref, p in mongo_products.items():
            sku = p.get('sku', '')
            url = IMAGES.get(sku)
            if not url:
                skipped_imgs += 1
                continue

            existing = p.get('imagenes') or []
            if existing:
                # Ya tiene al menos una imagen — no sobreescribir
                continue

            print(f"{tag}  Imagen: {sku}")
            added_imgs += 1

            if not dry_run:
                image_ops.append(
                    UpdateOne(
                        {'_id': p['_id']},
                        {'$set': {'imagenes': [url]}},
                    )
                )

        if image_ops and not dry_run:
            mongo.productos.bulk_write(image_ops)

        # ── Resumen ────────────────────────────────────────────────────────────
        print(f'\n{tag}Resumen:')
        print(f'{tag}  Ofertas agregadas:  {added_offers}')
        print(f'{tag}  Imagenes agregadas: {added_imgs}')
        print(f'{tag}  SKUs sin imagen conocida: {skipped_imgs}')
        if dry_run:
            print('[DRY-RUN] Ningun cambio fue escrito.')

    except Exception:
        if not dry_run:
            conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Seed ofertas e imágenes')
    parser.add_argument('--dry-run', action='store_true', help='Solo muestra qué se haría')
    args = parser.parse_args()
    main(dry_run=args.dry_run)
