"""Repara texto de catálogo guardado con doble codificación UTF-8 (mojibake).

Algunos productos semilla se insertaron decodificando bytes UTF-8 como
Windows-1252, por ejemplo ``Cien aÃ±os`` en lugar de ``Cien años``. El
índice de búsqueda indexaría ese texto corrupto, así que se repara en la
fuente antes de construirlo.

Alcance deliberado:
- Se reparan los campos descriptivos que ve el usuario: ``nombre``,
  ``descripcion`` y los valores de texto de ``atributos`` en ``productos``.
- **No** se modifican los SKU: son identificadores compartidos con MySQL
  (ofertas y snapshots de pedidos) y variantes; cambiarlos rompería
  referencias.
- **No** se reescribe ``producto_eventos``: el historial es de solo
  agregado por diseño (Entrega 1).

Es idempotente y trabaja en modo diagnóstico salvo con ``--apply``. Antes de
modificar genera un respaldo JSON con los documentos originales.

Uso (desde backend/):
    .\\venv\\Scripts\\python.exe scripts\\repair_text_encoding.py
    .\\venv\\Scripts\\python.exe scripts\\repair_text_encoding.py --apply
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from bson import json_util

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from app.core.db_mongo import get_mongo_db  # noqa: E402

BACKUP_DIR = BACKEND_DIR.parent / 'backups' / 'encoding'
# Secuencias que solo aparecen cuando UTF-8 se leyó como Windows-1252.
MARCAS_MOJIBAKE = ('Ã', 'â€', 'Â')


def reparar_texto(valor: str) -> str:
    """Devuelve el texto original si ``valor`` es mojibake reversible."""
    if not any(marca in valor for marca in MARCAS_MOJIBAKE):
        return valor
    try:
        reparado = valor.encode('cp1252').decode('utf-8')
    except (UnicodeEncodeError, UnicodeDecodeError):
        # Windows-1252 no define 5 bytes (0x81, 0x8D, 0x8F, 0x90, 0x9D);
        # latin-1 los cubre como caracteres de control.
        try:
            reparado = valor.encode('latin-1').decode('utf-8')
        except (UnicodeEncodeError, UnicodeDecodeError):
            return valor
    return reparado


def cambios_de(doc: dict) -> dict:
    cambios = {}
    for campo in ('nombre', 'descripcion'):
        valor = doc.get(campo)
        if isinstance(valor, str) and reparar_texto(valor) != valor:
            cambios[campo] = reparar_texto(valor)
    for clave, valor in (doc.get('atributos') or {}).items():
        if isinstance(valor, str) and reparar_texto(valor) != valor:
            cambios[f'atributos.{clave}'] = reparar_texto(valor)
    return cambios


def main() -> None:
    parser = argparse.ArgumentParser(description='Repara texto mal codificado del catálogo.')
    parser.add_argument('--apply', action='store_true', help='Aplica los cambios (por defecto solo diagnostica).')
    args = parser.parse_args()

    mongo = get_mongo_db()
    pendientes = []
    for doc in mongo.productos.find({}, {'nombre': 1, 'descripcion': 1, 'atributos': 1, 'sku': 1}):
        cambios = cambios_de(doc)
        if cambios:
            pendientes.append((doc, cambios))

    if not pendientes:
        print('Texto del catálogo: sin mojibake pendiente.')
        return

    for doc, cambios in pendientes:
        for campo, nuevo in cambios.items():
            anterior = doc.get(campo) if '.' not in campo else doc['atributos'][campo.split('.', 1)[1]]
            print(f"{doc.get('sku')} · {campo}: {anterior!r} -> {nuevo!r}")

    if not args.apply:
        print(f'\n{len(pendientes)} documento(s) por reparar. Ejecuta con --apply para aplicar.')
        return

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    marca = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
    respaldo = BACKUP_DIR / f'productos_mojibake_{marca}.json'
    respaldo.write_text(
        json.dumps(json.loads(json_util.dumps([doc for doc, _ in pendientes])), ensure_ascii=False, indent=2),
        encoding='utf-8',
    )
    for doc, cambios in pendientes:
        mongo.productos.update_one({'_id': doc['_id']}, {'$set': cambios})
    print(f'\n{len(pendientes)} documento(s) reparados. Respaldo: {respaldo}')


if __name__ == '__main__':
    main()
