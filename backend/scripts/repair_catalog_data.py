"""Repara atributos migrados y elimina cargas de imagen realmente huérfanas.

El script es idempotente y trabaja en modo diagnóstico salvo que se indique
``--apply``. Antes de modificar MongoDB o MySQL genera un respaldo JSON que
incluye los documentos originales y los BLOB que serán eliminados.
"""

from __future__ import annotations

import argparse
import base64
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pymysql
from bson import json_util
from dotenv import load_dotenv
from pymongo import MongoClient


ROOT = Path(__file__).resolve().parents[2]
BACKUP_DIR = ROOT / 'backups' / 'catalog-repair'
MIGRATION_ID = 'catalog_attribute_repair_v1'
load_dotenv(ROOT / 'backend' / '.env')


# Los valores proceden del nombre y la descripción de los datos semilla. El
# registro CAL-BB9A1604 fue creado como prueba sin descripción; se conserva con
# valores explícitos "No especificado" en vez de inventar características.
ATTRIBUTE_REPLACEMENTS: dict[str, dict] = {
    'ALI-MIE-001': {
        'peso_g': 1000, 'origen': 'Alta Verapaz',
        'apto_vegano': False, 'sin_gluten': True,
    },
    'DEP-ROP-002': {
        'deporte': 'Entrenamiento', 'talla': 'L', 'material': 'Poliéster',
        'genero': 'Hombre', 'color': 'Azul marino',
    },
    'DEP-GIM-002': {
        'deporte': 'Yoga', 'talla': '183 x 61 cm',
        'material': 'Material antideslizante', 'genero': 'Unisex',
        'color': 'Morado',
    },
    'DEP-NAT-001': {
        'deporte': 'Natación', 'material': 'Silicona', 'genero': 'Unisex',
    },
    'HER-SAR-001': {'uso': 'Sujeción y presión'},
    'DEP-ROP-001': {
        'deporte': 'Entrenamiento', 'talla': 'M',
        'material': '80% poliamida, 20% elastano', 'genero': 'Mujer',
        'color': 'Negro/Rosa',
    },
    'ROPA-PAN-002': {
        'talla': '28', 'color': 'Negro',
        'material': '95% algodón, 5% elastano',
        'corte': 'Skinny fit', 'genero': 'Mujer',
    },
    'ROPA-PAN-001': {
        'talla': '32', 'color': 'Azul índigo',
        'material': '98% algodón, 2% elastano',
        'corte': 'Slim fit', 'genero': 'Hombre',
    },
    'HER-MAN-001': {'uso': 'Mecánica y ajuste de tuercas'},
    'DEP-FUT-001': {
        'deporte': 'Fútbol', 'talla': '5',
        'material': 'Cuero sintético TPU', 'color': 'Blanco/Azul',
    },
    'ROPA-PAN-003': {
        'talla': '34', 'color': 'Beige', 'material': '100% algodón',
        'corte': 'Recto', 'genero': 'Hombre',
    },
    'JUG-ELE-001': {'edad_minima': 8, 'requiere_pilas': True},
    'HER-ESM-001': {
        'potencia_w': 200, 'uso': 'Desbaste y afilado',
        'incluye': 'Protectores y lámpara de trabajo',
    },
    'DEP-GIM-001': {
        'deporte': 'Gimnasio', 'talla': '10 kg cada una',
        'material': 'Goma y acero cromado',
    },
    'DEP-CIC-001': {
        'deporte': 'Ciclismo', 'talla': 'M/L',
        'genero': 'Unisex', 'color': 'Negro mate',
    },
    'HER-NIV-001': {
        'uso': 'Nivelación y alineación', 'incluye': 'Trípode',
    },
    'TECH-RAT-001': {
        'procesador': 'No aplica (periférico)', 'ram_gb': 0,
        'almacenamiento': 'No aplica (periférico)', 'pulgadas': 0,
        'color': 'Grafito',
    },
    'HER-SIE-001': {
        'potencia_w': 1200, 'uso': 'Corte de madera',
        'incluye': 'Guía paralela y disco para madera',
    },
    'TECH-TEC-001': {
        'procesador': 'No aplica (periférico)', 'ram_gb': 0,
        'almacenamiento': 'No aplica (periférico)', 'pulgadas': 0,
    },
    'HER-TAL-001': {
        'potencia_w': 750, 'uso': 'Perforación con percusión',
        'incluye': 'Maletín',
    },
    'HER-A9E516E7': {'uso': 'Pa chambear'},
    'HER-MED-001': {'uso': 'Medición eléctrica'},
    'ROPA-CAL-001': {
        'talla': 42, 'color': 'Blanco', 'material': 'Cuero sintético', 'genero': 'Unisex',
    },
    'LIBRO-FIC-001': {
        'autor': 'Gabriel García Márquez', 'isbn': '978-0307474728',
        'editorial': 'Random House', 'paginas': 432,
    },
    'LIBRO-TEC-001': {
        'autor': 'Robert C. Martin', 'isbn': '978-0132350884',
        'editorial': 'Prentice Hall', 'paginas': 431,
    },
    'LIBRO-TEC-002': {
        'autor': 'Martin Kleppmann', 'isbn': '978-1449373320',
        'editorial': "O'Reilly", 'paginas': 562,
    },
    'LIBRO-EDU-001': {
        'autor': 'Abraham Silberschatz', 'isbn': '978-0073523323',
        'editorial': 'McGraw-Hill', 'paginas': 1376,
    },
    'LIBRO-FIC-002': {
        'autor': 'Patrick Rothfuss', 'isbn': '978-8401337208',
        'editorial': 'Ediciones B', 'paginas': 662,
    },
    'LIBRO-TEC-003': {
        'autor': 'Eric Matthes', 'isbn': '978-1593279288',
        'editorial': 'No Starch Press', 'paginas': 544,
    },
    'LIBRO-FIC-003': {
        'autor': 'J.K. Rowling', 'isbn': '978-8498383638',
        'editorial': 'Salamandra', 'paginas': 309,
    },
    'LIBRO-AUT-001': {
        'autor': 'George S. Clason', 'isbn': '978-8497774338',
        'editorial': 'Obelisco', 'paginas': 192,
    },
    'TECH-AUD-002': {
        'tipo_audio': 'Bocina', 'conectividad': 'Bluetooth',
        'bateria_horas': 20, 'cancelacion_ruido': False,
    },
    'TECH-AUD-003': {
        'tipo_audio': 'In-ear', 'conectividad': 'Bluetooth / USB-C',
        'cancelacion_ruido': True, 'color': 'Blanco',
    },
    'TECH-LAP-004': {
        'procesador': 'Intel Core i3-1215U', 'ram_gb': 8,
        'almacenamiento': '128GB SSD', 'pulgadas': 15.6,
    },
    'TECH-MON-001': {
        'procesador': 'No aplica (monitor)', 'ram_gb': 0,
        'almacenamiento': 'No aplica (monitor)', 'pulgadas': 27,
    },
    'TECH-LAP-002': {
        'procesador': 'AMD Ryzen 5 5500U', 'ram_gb': 16,
        'almacenamiento': '256GB SSD', 'pulgadas': 14,
    },
    'TECH-LAP-001': {
        'procesador': 'Intel Core i5-1235U', 'ram_gb': 8,
        'almacenamiento': '512GB SSD', 'pulgadas': 15.6,
    },
    'TECH-LAP-005': {
        'procesador': 'Intel Core i7-12650H', 'ram_gb': 16,
        'almacenamiento': '1TB SSD', 'pulgadas': 14,
    },
    'TECH-LAP-003': {
        'procesador': 'Apple M2', 'ram_gb': 8,
        'almacenamiento': '256GB SSD', 'pulgadas': 13.6,
    },
    'CAL-BB9A1604': {
        'talla': 1, 'color': 'Negro', 'material': 'Lana',
        'genero': 'No binario', 'procesador': 'No especificado',
        'ram_gb': 0, 'almacenamiento': 'No especificado', 'pulgadas': 0,
    },
}


def mysql_connection():
    return pymysql.connect(
        host=os.getenv('MYSQL_HOST', 'localhost'),
        port=int(os.getenv('MYSQL_PORT', 3306)),
        database=os.getenv('MYSQL_DB', 'tiendaya'),
        user=os.getenv('MYSQL_USER', 'tiendaya'),
        password=os.getenv('MYSQL_PASSWORD', 'tiendaya123'),
        charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )


def validate_attributes(doc: dict, schemas: dict[str, dict]) -> list[str]:
    categories = doc.get('categorias') or [doc.get('categoria', {})]
    definitions: dict[str, dict] = {}
    for category in categories:
        slug = category.get('slug') if category else None
        for field in schemas.get(slug, {}).get('atributos', []):
            definitions[field['nombre']] = field
    attrs = doc.get('atributos') or {}
    errors = []
    unknown = sorted(set(attrs) - set(definitions))
    if unknown:
        errors.append(f'atributos no definidos: {", ".join(unknown)}')
    for name, field in definitions.items():
        value = attrs.get(name)
        if field.get('requerido') and (
            value is None or (isinstance(value, str) and not value.strip())
        ):
            errors.append(f'falta {name}')
            continue
        if value is None:
            continue
        expected = field.get('tipo', 'string')
        valid = (
            expected == 'string' and isinstance(value, str)
            or expected == 'number' and isinstance(value, (int, float)) and not isinstance(value, bool)
            or expected == 'boolean' and isinstance(value, bool)
        )
        if not valid:
            errors.append(f'{name} no es {expected}')
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--cleanup-orphan-images', action='store_true')
    args = parser.parse_args()

    mongo_client = MongoClient(
        os.getenv('MONGO_URI'), serverSelectionTimeoutMS=5000
    )
    mongo = mongo_client[os.getenv('MONGO_DB', 'tiendaya')]
    sql = mysql_connection()
    try:
        schemas = {
            row['categoria_slug']: row
            for row in mongo.categoria_esquemas.find({})
        }
        first_reconciliation = mongo.migraciones.find_one(
            {'_id': MIGRATION_ID}, {'_id': 1}
        ) is None
        docs = list(mongo.productos.find({}))
        proposed = []
        for original in docs:
            candidate = dict(original)
            if (
                first_reconciliation
                and original.get('sku') in ATTRIBUTE_REPLACEMENTS
            ):
                candidate['atributos'] = ATTRIBUTE_REPLACEMENTS[original['sku']]
            errors = validate_attributes(candidate, schemas)
            if errors:
                proposed.append((original, candidate, errors))
            elif (
                candidate.get('atributos') != original.get('atributos')
                or 'mysql_id' in original
            ):
                proposed.append((original, candidate, []))

        invalid = [
            f"{old.get('sku')} ({old.get('nombre')}): {', '.join(errors)}"
            for old, _, errors in proposed if errors
        ]
        if invalid:
            print('No se aplicó nada; aún hay productos inválidos:')
            print('\n'.join(f'  - {line}' for line in invalid))
            return 1

        with sql.cursor() as cursor:
            cursor.execute('''
                SELECT pi.*
                FROM producto_imagenes pi
                LEFT JOIN solicitud_catalogo_imagenes sci
                  ON sci.producto_imagen_id = pi.id
                WHERE pi.producto_referencia_id IS NULL
                  AND sci.producto_imagen_id IS NULL
                ORDER BY pi.id
            ''')
            orphan_images = cursor.fetchall()

        changed = [(old, new) for old, new, _ in proposed]
        print(
            f'Productos por corregir: {len(changed)}; '
            f'imágenes huérfanas: {len(orphan_images)}'
        )
        if not args.apply:
            print('Diagnóstico correcto. Usa --apply para guardar los cambios.')
            return 0
        if (
            not changed
            and not first_reconciliation
            and (not args.cleanup_orphan_images or not orphan_images)
        ):
            print('El catálogo ya está reparado.')
            return 0

        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        backup_path = BACKUP_DIR / f'catalog_repair_{datetime.now():%Y%m%d_%H%M%S}.json'
        backup = {
            'created_at': datetime.now(timezone.utc).isoformat(),
            'products': [old for old, _ in changed],
            'orphan_images': [
                {
                    **{k: v for k, v in image.items() if k != 'datos'},
                    'datos_base64': base64.b64encode(image['datos']).decode('ascii'),
                }
                for image in orphan_images
            ] if args.cleanup_orphan_images else [],
        }
        backup_path.write_text(
            json_util.dumps(backup, ensure_ascii=False, indent=2),
            encoding='utf-8',
        )

        for original, candidate in changed:
            updates = {'atributos': candidate.get('atributos', {})}
            mongo.productos.update_one(
                {'_id': original['_id']},
                {'$set': updates, '$unset': {'mysql_id': ''}},
            )
            if candidate.get('atributos') == original.get('atributos'):
                continue
            latest = mongo.producto_eventos.find_one(
                {'producto_id': str(original['_id'])},
                sort=[('version', -1)], projection={'version': 1},
            )
            mongo.producto_eventos.insert_one({
                'producto_id': str(original['_id']),
                'tipo_evento': 'ATRIBUTOS_RECONCILIADOS',
                'datos_anteriores': {'atributos': original.get('atributos', {})},
                'datos_nuevos': {'atributos': candidate.get('atributos', {})},
                'usuario_id': None,
                'timestamp': datetime.now(timezone.utc).replace(tzinfo=None),
                'version': int((latest or {}).get('version', 0)) + 1,
            })

        if args.cleanup_orphan_images and orphan_images:
            ids = [image['id'] for image in orphan_images]
            with sql.cursor() as cursor:
                placeholders = ','.join(['%s'] * len(ids))
                cursor.execute(
                    f'DELETE FROM producto_imagenes WHERE id IN ({placeholders}) '
                    'AND producto_referencia_id IS NULL', ids,
                )
            sql.commit()

        mongo.migraciones.update_one(
            {'_id': MIGRATION_ID},
            {'$set': {
                'aplicada_en': datetime.now(timezone.utc).replace(tzinfo=None),
                'productos_reconciliados': len(changed),
            }},
            upsert=True,
        )

        remaining_invalid = []
        for doc in mongo.productos.find({}):
            errors = validate_attributes(doc, schemas)
            if errors:
                remaining_invalid.append(f"{doc.get('sku')}: {', '.join(errors)}")
        if remaining_invalid:
            raise RuntimeError('La validación posterior falló: ' + '; '.join(remaining_invalid))
        print(f'Reparación aplicada. Respaldo: {backup_path}')
        return 0
    except Exception:
        sql.rollback()
        raise
    finally:
        sql.close()
        mongo_client.close()


if __name__ == '__main__':
    sys.exit(main())
