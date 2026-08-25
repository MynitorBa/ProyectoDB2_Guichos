#!/usr/bin/env python3
"""
Script de migración: MySQL → MongoDB (idempotente).
Lee los productos de MySQL, construye documentos con atributos variables
según la categoría, y los inserta/actualiza en MongoDB con bulk_write + upsert.

Uso:
  python migrate_products_to_mongo.py [--dry-run] [--reset]

Flags:
  --dry-run   Solo muestra cuántos documentos se procesarían, sin escribir.
  --reset     Borra la colección productos en Mongo antes de migrar.
"""
import sys
import os
import argparse
from datetime import datetime

# Asegurar que el módulo app sea encontrable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pymysql
from pymongo import MongoClient, UpdateOne
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

# ── Configuración ─────────────────────────────────────────────────────────────
MYSQL_HOST     = os.getenv('MYSQL_HOST', 'localhost')
MYSQL_PORT     = int(os.getenv('MYSQL_PORT', 3306))
MYSQL_DB       = os.getenv('MYSQL_DB', 'tiendaya')
MYSQL_USER     = os.getenv('MYSQL_USER', 'tiendaya')
MYSQL_PASSWORD = os.getenv('MYSQL_PASSWORD', 'tiendaya123')
MONGO_URI      = os.getenv('MONGO_URI', 'mongodb://admin:adminpassword@localhost:27017/tiendaya?authSource=admin')
MONGO_DB       = os.getenv('MONGO_DB', 'tiendaya')

# Mapa de categoría slug → función que extrae atributos del campo descripcion
# En producción esto leería la colección categoria_esquemas de Mongo;
# aquí usamos mapeo directo porque el seed de MySQL codificó los atributos
# en la descripción con un formato reconocible.
ATRIBUTOS_EXTRACTORES = {
    'computadoras': lambda p: _extraer_laptop(p['descripcion']),
    'celulares':    lambda p: _extraer_celular(p['descripcion']),
    'audio':        lambda p: _extraer_audio(p['descripcion']),
    'camisas':      lambda p: _extraer_ropa(p['descripcion']),
    'pantalones':   lambda p: _extraer_pantalon(p['descripcion']),
    'calzado':      lambda p: _extraer_calzado(p['descripcion']),
    'libros':       lambda p: _extraer_libro(p['descripcion']),
    'deportes':     lambda p: _extraer_deporte(p['descripcion']),
    'alimentos':    lambda p: _extraer_alimento(p['descripcion']),
    'juguetes':     lambda p: _extraer_juguete(p['descripcion']),
    'herramientas': lambda p: _extraer_herramienta(p['descripcion']),
    'hogar':        lambda p: _extraer_hogar(p['descripcion']),
}


def _parse_desc(desc: str) -> dict[str, str]:
    """Parsea descripcion con formato 'clave: valor | clave: valor' en dict."""
    partes = {}
    if not desc:
        return partes
    for parte in desc.split('|'):
        if ':' in parte:
            k, _, v = parte.partition(':')
            partes[k.strip().lower()] = v.strip()
    return partes


def _extraer_laptop(desc):
    p = _parse_desc(desc)
    r = {}
    if 'intel core' in desc.lower() or 'amd ryzen' in desc.lower() or 'apple m' in desc.lower():
        r['procesador'] = desc.split('|')[0].strip() if '|' in desc else desc
    for k in p:
        if 'gb ram' in k or 'ram' in k:
            try:
                r['ram_gb'] = int(k.replace('gb ram', '').replace('gb', '').strip())
            except Exception:
                r['ram_gb'] = k
        if 'ssd' in k or 'almacen' in k:
            r['almacenamiento'] = k
    if '"' in desc:
        import re
        m = re.search(r'(\d+\.?\d*)"', desc)
        if m:
            r['pulgadas'] = float(m.group(1))
    return r or {'nota': desc[:100]}


def _extraer_celular(desc):
    import re
    r = {}
    m_ram = re.search(r'(\d+)GB RAM', desc)
    if m_ram:
        r['ram_gb'] = int(m_ram.group(1))
    m_alm = re.search(r'(\d+)GB\b', desc)
    if m_alm:
        r['almacenamiento'] = f"{m_alm.group(1)}GB"
    m_mp = re.search(r'(\d+)MP', desc)
    if m_mp:
        r['camara_mp'] = int(m_mp.group(1))
    m_pul = re.search(r'(\d+\.\d+)"', desc)
    if m_pul:
        r['pulgadas'] = float(m_pul.group(1))
    if 'android' in desc.lower():
        m_so = re.search(r'Android \d+', desc)
        r['sistema_op'] = m_so.group(0) if m_so else 'Android'
    elif 'ios' in desc.lower():
        m_so = re.search(r'iOS \d+', desc)
        r['sistema_op'] = m_so.group(0) if m_so else 'iOS'
    return r


def _extraer_audio(desc):
    import re
    r = {}
    if 'bluetooth' in desc.lower():
        m = re.search(r'Bluetooth ([\d.]+)', desc, re.IGNORECASE)
        r['conectividad'] = f"Bluetooth {m.group(1)}" if m else 'Bluetooth'
    elif '3.5' in desc:
        r['conectividad'] = '3.5mm jack'
    m_bat = re.search(r'(\d+)h batería', desc, re.IGNORECASE)
    if m_bat:
        r['bateria_horas'] = int(m_bat.group(1))
    r['cancelacion_ruido'] = 'cancelación de ruido' in desc.lower()
    m_w = re.search(r'(\d+)W RMS', desc)
    if m_w:
        r['potencia_w'] = int(m_w.group(1))
        r['tipo_audio'] = 'Bocina'
    else:
        r['tipo_audio'] = 'Over-ear' if 'over' in desc.lower() else 'In-ear'
    return r


def _extraer_ropa(desc):
    import re
    r = {}
    m_talla = re.search(r'Talla (XS|S|M|L|XL|XXL)', desc, re.IGNORECASE)
    if m_talla:
        r['talla'] = m_talla.group(1).upper()
    if '100%' in desc or '%' in desc:
        m_mat = re.search(r'(\d+% [\w]+(?:\s+\d+% [\w]+)?)', desc)
        if m_mat:
            r['material'] = m_mat.group(0)
    r['genero'] = 'Mujer' if 'mujer' in desc.lower() or 'blusa' in desc.lower() else 'Hombre'
    for color in ['azul', 'rojo', 'negro', 'blanco', 'beige', 'multicolor']:
        if color in desc.lower():
            r['color'] = color.capitalize()
            break
    return r


def _extraer_pantalon(desc):
    import re
    r = {}
    m_talla = re.search(r'Talla (\d{2})', desc)
    if m_talla:
        r['talla'] = m_talla.group(1)
    for corte in ['Slim fit', 'Skinny fit', 'Regular fit', 'Recto']:
        if corte.lower() in desc.lower():
            r['corte'] = corte
            break
    r['genero'] = 'Mujer' if 'mujer' in desc.lower() else 'Hombre'
    for color in ['azul', 'negro', 'beige', 'café']:
        if color in desc.lower():
            r['color'] = color.capitalize()
            break
    return r


def _extraer_calzado(desc):
    import re
    r = {}
    m_talla = re.search(r'Talla (\d{2})', desc)
    if m_talla:
        r['talla'] = int(m_talla.group(1))
    for color in ['blanco', 'negro', 'café', 'beige']:
        if color in desc.lower():
            r['color'] = color.capitalize()
            break
    for material in ['cuero genuino', 'cuero sintético', 'tela']:
        if material in desc.lower():
            r['material'] = material.capitalize()
            break
    r['genero'] = 'Hombre' if 'hombre' in desc.lower() else ('Mujer' if 'mujer' in desc.lower() else 'Unisex')
    return r


def _extraer_libro(desc):
    import re
    r = {}
    m_autor = re.search(r'Autor: ([^|]+)', desc)
    if m_autor:
        r['autor'] = m_autor.group(1).strip()
    m_isbn = re.search(r'ISBN: ([\d-]+)', desc)
    if m_isbn:
        r['isbn'] = m_isbn.group(1)
    m_pag = re.search(r'(\d+) págs', desc)
    if m_pag:
        r['paginas'] = int(m_pag.group(1))
    # Editorial es lo último después de la última |
    partes = desc.split('|')
    if len(partes) >= 4:
        r['editorial'] = partes[-1].strip()
    return r


def _extraer_deporte(desc):
    import re
    r = {}
    for dep in ['Fútbol', 'Natación', 'Ciclismo', 'Gimnasio', 'Yoga']:
        if dep.lower() in desc.lower():
            r['deporte'] = dep
            break
    m_talla = re.search(r'Talla (\w+)', desc)
    if m_talla:
        r['talla'] = m_talla.group(1)
    for color in ['negro', 'azul', 'rojo', 'blanco', 'morado']:
        if color in desc.lower():
            r['color'] = color.capitalize()
            break
    return r


def _extraer_alimento(desc):
    import re
    r = {}
    m_g = re.search(r'(\d+)g', desc, re.IGNORECASE)
    if m_g:
        r['peso_g'] = int(m_g.group(1))
    for region in ['Huehuetenango', 'Alta Verapaz', 'Guatemala']:
        if region in desc:
            r['origen'] = region
            break
    r['apto_vegano'] = 'vegano' in desc.lower()
    r['sin_gluten'] = 'sin gluten' in desc.lower()
    return r


def _extraer_juguete(desc):
    import re
    r = {}
    m_edad = re.search(r'Edad (\d+)\+', desc, re.IGNORECASE)
    if m_edad:
        r['edad_minima'] = int(m_edad.group(1))
    m_piezas = re.search(r'(\d+) piezas', desc, re.IGNORECASE)
    if m_piezas:
        r['num_piezas'] = int(m_piezas.group(1))
    r['requiere_pilas'] = 'pilas' in desc.lower() or 'batería' in desc.lower()
    return r


def _extraer_herramienta(desc):
    import re
    r = {}
    m_w = re.search(r'(\d+)W', desc)
    if m_w:
        r['potencia_w'] = int(m_w.group(1))
    for uso in ['Carpintería', 'Electricidad', 'Medición', 'Sujeción', 'Nivelación']:
        if uso.lower() in desc.lower():
            r['uso'] = uso
            break
    if 'maletín' in desc.lower():
        r['incluye'] = 'Maletín'
    return r


def _extraer_hogar(desc):
    import re
    r = {}
    m_w = re.search(r'(\d+)W', desc)
    if m_w:
        r['potencia_w'] = int(m_w.group(1))
    for mat in ['acero inox', 'mdf', 'vidrio', 'aluminio']:
        if mat in desc.lower():
            r['material'] = mat.title()
            break
    for color in ['negro', 'blanco', 'nogal', 'plateado']:
        if color in desc.lower():
            r['color'] = color.capitalize()
            break
    return r


# ── Lógica principal ──────────────────────────────────────────────────────────

def main(dry_run: bool = False, reset: bool = False):
    print(f"{'[DRY-RUN] ' if dry_run else ''}Iniciando migracion MySQL -> MongoDB")

    # Conexión MySQL
    conn = pymysql.connect(
        host=MYSQL_HOST, port=MYSQL_PORT, db=MYSQL_DB,
        user=MYSQL_USER, password=MYSQL_PASSWORD,
        charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor
    )

    # Conexión Mongo
    client = MongoClient(MONGO_URI)
    mongo = client[MONGO_DB]

    if reset and not dry_run:
        mongo.productos.drop()
        mongo.producto_eventos.drop()
        print('Colecciones productos y producto_eventos eliminadas.')

    with conn.cursor() as cur:
        # Leer productos con su categoría, vendedor e imágenes
        cur.execute("""
            SELECT
              p.id, p.sku, p.nombre, p.descripcion, p.precio, p.estado,
              p.fecha_creacion, p.fecha_actualizacion,
              c.slug  AS cat_slug,
              c.nombre AS cat_nombre,
              v.id    AS vendedor_id,
              v.nombre_comercial AS vendedor_nombre
            FROM productos p
            JOIN categorias c ON p.categoria_id = c.id
            JOIN vendedores v ON p.vendedor_id   = v.id
            WHERE p.estado != 'descontinuado'
        """)
        productos = cur.fetchall()

        # Leer imágenes
        cur.execute("SELECT producto_id, url, alt_text, orden, es_principal FROM producto_imagenes ORDER BY orden")
        imagenes_raw = cur.fetchall()
        imagenes_por_producto: dict[int, list] = {}
        for img in imagenes_raw:
            imagenes_por_producto.setdefault(img['producto_id'], []).append({
                'url': img['url'],
                'alt_text': img['alt_text'],
                'orden': img['orden'],
                'es_principal': bool(img['es_principal']),
            })

        # Leer inventario
        cur.execute("SELECT producto_id, cantidad_disponible FROM inventario WHERE bodega='principal'")
        inventario_raw = {r['producto_id']: r['cantidad_disponible'] for r in cur.fetchall()}

    leidos = len(productos)
    migrados = actualizados = omitidos = errores = 0
    operaciones = []

    for p in productos:
        try:
            cat_slug = p['cat_slug']
            extractor = ATRIBUTOS_EXTRACTORES.get(cat_slug, lambda x: {})
            atributos = extractor(p)
            stock = int(inventario_raw.get(p['id'], 0))

            doc = {
                'sku': p['sku'],
                'nombre': p['nombre'],
                'descripcion': p['descripcion'],
                'precio': float(p['precio']),
                'moneda': 'GTQ',
                'categoria': {'slug': cat_slug, 'nombre': p['cat_nombre']},
                'estado': p['estado'],
                'stock': stock,
                'disponible': stock > 0,
                'atributos': atributos,
                'imagenes': imagenes_por_producto.get(p['id'], []),
                'vendedor_id': int(p['vendedor_id']),
                'vendedor_nombre': p['vendedor_nombre'],
                'resumen_resenas': {'promedio': 0.0, 'total': 0},
                'fecha_creacion': p['fecha_creacion'],
                'fecha_actualizacion': p['fecha_actualizacion'],
                'mysql_id': p['id'],  # referencia cruzada
            }

            # Upsert por SKU: idempotente aunque se corra varias veces.
            # fecha_creacion solo se escribe en la inserción inicial (setOnInsert),
            # no en actualizaciones posteriores.
            doc_sin_fecha_creacion = {k: v for k, v in doc.items() if k != 'fecha_creacion'}
            op = UpdateOne(
                {'sku': p['sku']},
                {
                    '$set': doc_sin_fecha_creacion,
                    '$setOnInsert': {'fecha_creacion': p['fecha_creacion']},
                },
                upsert=True
            )
            operaciones.append((p['id'], p['sku'], op))

        except Exception as e:
            print(f'  ERROR procesando producto id={p["id"]} sku={p["sku"]}: {e}')
            errores += 1

    print(f'  Leídos de MySQL: {leidos}')
    print(f'  Errores al procesar: {errores}')

    if dry_run:
        print(f'  [DRY-RUN] Se insertarían/actualizarían: {len(operaciones)}')
        conn.close()
        client.close()
        return

    if operaciones:
        resultado = mongo.productos.bulk_write([op for _, _, op in operaciones])
        migrados   = resultado.upserted_count
        actualizados = resultado.modified_count

    # Actualizar producto_ref en MySQL para cada documento migrado
    conn_upd = pymysql.connect(
        host=MYSQL_HOST, port=MYSQL_PORT, db=MYSQL_DB,
        user=MYSQL_USER, password=MYSQL_PASSWORD, charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
    )
    with conn_upd.cursor() as cur:
        for mysql_id, sku, _ in operaciones:
            doc = mongo.productos.find_one({'sku': sku}, {'_id': 1})
            if doc:
                cur.execute(
                    "UPDATE productos SET producto_ref = %s WHERE id = %s",
                    (str(doc['_id']), mysql_id)
                )
    conn_upd.commit()
    conn_upd.close()

    # Validación de consistencia
    total_mysql = leidos - errores
    total_mongo = mongo.productos.count_documents({})
    print(f'\n-- Resumen ------------------------------------------')
    print(f'  Leidos MySQL:        {leidos}')
    print(f'  Insertados (nuevos): {migrados}')
    print(f'  Actualizados:        {actualizados}')
    print(f'  Omitidos (errores):  {errores}')
    print(f'  Total en MongoDB:    {total_mongo}')
    if total_mongo != total_mysql:
        print(f'  DISCREPANCIA: MySQL tiene {total_mysql}, Mongo tiene {total_mongo}')
    else:
        print(f'  OK: Conteos coinciden.')

    conn.close()
    client.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Migracion productos MySQL -> MongoDB')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--reset', action='store_true')
    args = parser.parse_args()
    main(dry_run=args.dry_run, reset=args.reset)
