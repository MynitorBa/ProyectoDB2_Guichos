#!/usr/bin/env python3
"""Compara la calidad de la búsqueda de productos entre motores.

Ejecuta un conjunto fijo de consultas representativas (errores ortográficos,
tildes, sinónimos, prefijos, orden de palabras y SKU) y mide para cada motor:
resultados obtenidos, si un producto esperado aparece entre los tres primeros
y la latencia promedio. Solo lee datos; no modifica ninguna base.

Uso (desde backend/):
    .\\venv\\Scripts\\python.exe scripts\\comparar_busqueda.py
    .\\venv\\Scripts\\python.exe scripts\\comparar_busqueda.py --salida ..\\docs\\evidencia\\busqueda-linea-base.md
"""

import argparse
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from app.core.db_mongo import get_mongo_db  # noqa: E402


@dataclass(frozen=True)
class Caso:
    consulta: str
    tipo: str
    # Prefijos de SKU que cuentan como resultado correcto.
    esperados: tuple[str, ...]


CASOS = (
    Caso('laptop', 'control', ('TECH-LAP-',)),
    Caso('licuadora oster', 'control', ('HOGAR-COC-001',)),
    Caso('lapto', 'error ortográfico', ('TECH-LAP-',)),
    Caso('macbok', 'error ortográfico', ('TECH-LAP-003',)),
    Caso('samsng galaxy', 'error ortográfico', ('TECH-CEL-001',)),
    Caso('harry poter', 'error ortográfico', ('LIBRO-FIC-003',)),
    Caso('audifonos sony', 'sin tilde', ('TECH-AUD-001',)),
    Caso('mouse inalambrico', 'sin tilde', ('TECH-RAT-001',)),
    Caso('cafe huehuetenango', 'sin tilde', ('ALI-CAF-001',)),
    Caso('telefono', 'sinónimo', ('TECH-CEL-',)),
    Caso('portatil', 'sinónimo', ('TECH-LAP-',)),
    Caso('zapatillas nike', 'sinónimo', ('ROPA-CAL-001',)),
    Caso('sams', 'prefijo', ('TECH-CEL-001',)),
    Caso('tala', 'prefijo', ('HER-TAL-001',)),
    Caso('inspiron dell', 'orden de palabras', ('TECH-LAP-001',)),
    Caso('dewalt taladro', 'orden de palabras', ('HER-TAL-001',)),
    Caso('TECH-LAP-001', 'SKU exacto', ('TECH-LAP-001',)),
)

REPETICIONES = 5
TOP = 3


def buscar_regex(mongo, consulta: str) -> list[dict]:
    """Réplica del filtro actual de catalog_service.listar_productos."""
    pattern = re.escape(consulta.strip())
    return list(mongo.productos.find(
        {'estado': 'activo', '$or': [
            {'nombre': {'$regex': pattern, '$options': 'i'}},
            {'sku': {'$regex': pattern, '$options': 'i'}},
        ]},
        {'nombre': 1, 'sku': 1},
    ))


def buscar_texto_mongo(mongo, consulta: str) -> list[dict]:
    """Índice $text existente (idx_texto_nombre_descripcion), ordenado por score."""
    return list(mongo.productos.find(
        {'estado': 'activo', '$text': {'$search': consulta}},
        {'nombre': 1, 'sku': 1, 'score': {'$meta': 'textScore'}},
    ).sort([('score', {'$meta': 'textScore'})]))


def buscar_elasticsearch(mongo, consulta: str) -> list[dict]:
    """La misma consulta que usa GET /api/v1/search (search_service.construir_consulta)."""
    from app.core.config import settings
    from app.core.db_elastic import get_es
    from app.services.search_service import ParametrosBusqueda, como_argumentos, construir_consulta

    cuerpo = construir_consulta(ParametrosBusqueda(q=consulta, page_size=TOP))
    cuerpo.pop('aggs')
    cuerpo.pop('suggest', None)
    cuerpo.pop('highlight', None)
    cuerpo['_source'] = ['nombre', 'sku']
    respuesta = get_es().search(index=settings.ES_INDEX_ALIAS, **como_argumentos(cuerpo))
    total = respuesta['hits']['total']['value']
    resultados = [hit['_source'] for hit in respuesta['hits']['hits']]
    # Solo se piden los primeros; se rellena para reportar el total real.
    return resultados + [{}] * (total - len(resultados))


MOTORES = {
    'mongo_regex': ('MongoDB $regex (anterior)', buscar_regex),
    'mongo_text': ('MongoDB $text', buscar_texto_mongo),
    'elasticsearch': ('Elasticsearch (nuevo)', buscar_elasticsearch),
}


def medir(funcion, mongo, consulta: str) -> tuple[list[dict], float]:
    resultados = funcion(mongo, consulta)
    inicio = time.perf_counter()
    for _ in range(REPETICIONES):
        funcion(mongo, consulta)
    latencia_ms = (time.perf_counter() - inicio) * 1000 / REPETICIONES
    return resultados, latencia_ms


def acierta(resultados: list[dict], caso: Caso) -> bool:
    return any(
        str(doc.get('sku', '')).startswith(prefijo)
        for doc in resultados[:TOP]
        for prefijo in caso.esperados
    )


def ejecutar(motores: list[str]) -> str:
    mongo = get_mongo_db()
    lineas = [
        '| Consulta | Tipo | ' + ' | '.join(MOTORES[m][0] for m in motores) + ' |',
        '|---|---|' + '---|' * len(motores),
    ]
    aciertos = {m: 0 for m in motores}
    latencias = {m: [] for m in motores}
    detalle = []

    for caso in CASOS:
        celdas = []
        for motor in motores:
            nombre, funcion = MOTORES[motor]
            resultados, latencia = medir(funcion, mongo, caso.consulta)
            ok = acierta(resultados, caso)
            aciertos[motor] += ok
            latencias[motor].append(latencia)
            celdas.append(f"{'✅' if ok else '❌'} {len(resultados)} res. · {latencia:.1f} ms")
            top = ', '.join(doc.get('nombre', '?') for doc in resultados[:TOP]) or '—'
            detalle.append(f'| `{caso.consulta}` | {nombre} | {top} |')
        lineas.append(f'| `{caso.consulta}` | {caso.tipo} | ' + ' | '.join(celdas) + ' |')

    total = len(CASOS)
    lineas.append(
        f'| **Aciertos en top {TOP}** | | '
        + ' | '.join(
            f'**{aciertos[m]}/{total}** · prom. {sum(latencias[m]) / total:.1f} ms'
            for m in motores
        )
        + ' |'
    )
    lineas += [
        '',
        f'### Primeros {TOP} resultados por consulta',
        '',
        '| Consulta | Motor | Resultados |',
        '|---|---|---|',
        *detalle,
    ]
    return '\n'.join(lineas)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--motores', nargs='+', choices=sorted(MOTORES), default=list(MOTORES))
    parser.add_argument('--titulo', default='Comparación de búsqueda de productos')
    parser.add_argument('--salida', type=Path, help='Archivo Markdown donde guardar la tabla.')
    args = parser.parse_args()

    tabla = ejecutar(args.motores)
    print(tabla)
    if args.salida:
        args.salida.parent.mkdir(parents=True, exist_ok=True)
        encabezado = (
            f'# {args.titulo}\n\n'
            f'Generado por `backend/scripts/comparar_busqueda.py`. '
            f'Un acierto significa que un producto esperado aparece entre los '
            f'{TOP} primeros resultados. La latencia es el promedio de '
            f'{REPETICIONES} ejecuciones.\n\n'
        )
        args.salida.write_text(encabezado + tabla + '\n', encoding='utf-8')
        print(f'\nGuardado en {args.salida}')


if __name__ == '__main__':
    main()
