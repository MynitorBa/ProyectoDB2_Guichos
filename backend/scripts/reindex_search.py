#!/usr/bin/env python3
"""Construye o reconcilia el índice de búsqueda de productos en Elasticsearch.

Modos (todos idempotentes):

- Sin opciones: crea el índice si falta y sincroniza **todos** los productos
  sobre el índice vigente. Elimina del índice los productos que ya no están
  activos en MongoDB. Si el índice vigente usa un mapping anterior (por
  ejemplo v1, sin vectores), lo migra como ``--recrear``.
- ``--recrear``: construye un índice nuevo (``productos_vN_<fecha>``), lo carga,
  mueve el alias ``productos`` de forma atómica y borra el índice anterior. Se
  usa al cambiar el mapping; las búsquedas no se interrumpen.
- ``--diff``: solo reindexa lo desfasado (productos editados en MongoDB después
  de su último indexado, ausentes del índice o que sobran en él). Cubre las
  escrituras de catálogo cuyo evento de sincronización no llegó a encolarse.

Uso (desde backend/):
    .\\venv\\Scripts\\python.exe scripts\\reindex_search.py
    .\\venv\\Scripts\\python.exe scripts\\reindex_search.py --recrear
    .\\venv\\Scripts\\python.exe scripts\\reindex_search.py --diff
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from app.core.config import settings  # noqa: E402
from app.core.db_elastic import get_es  # noqa: E402
from app.core.db_mongo import get_mongo_db  # noqa: E402
from app.core.db_mysql import SessionLocal  # noqa: E402
from app.services import search_index_service as indice  # noqa: E402


def _neo4j_driver():
    try:
        from app.core.db_neo4j import get_driver
        return get_driver()
    except Exception as exc:
        print(f'  Aviso: Neo4j no disponible ({exc}); se indexa sin rating.')
        return None


def sincronizar(es, mysql_db, mongo, neo4j) -> dict:
    actual = indice.indice_actual(es)
    if actual and not actual.startswith(f'{indice.PREFIJO_INDICE}{indice.VERSION_MAPPING}_'):
        # El índice vigente usa un mapping anterior (p. ej. v1 sin vectores): se
        # migra sin caída con un índice nuevo y cambio de alias.
        print(f'  El índice {actual} usa un mapping anterior; se migra a v{indice.VERSION_MAPPING}.')
        return recrear(es, mysql_db, mongo, neo4j)
    indice.asegurar_indice(es)
    activos = [str(doc['_id']) for doc in mongo.productos.find({'estado': 'activo'}, {'_id': 1})]
    sobrantes = set(indice.ids_indexados(es)) - set(activos)
    return indice.indexar_productos(es, mysql_db, mongo, activos + sorted(sobrantes), neo4j, refrescar=True)


def recrear(es, mysql_db, mongo, neo4j) -> dict:
    nuevo = indice.nombre_indice_nuevo()
    indice.crear_indice(es, nuevo)
    version = indice.version_lectura()
    documentos = indice.construir_documentos(mysql_db, mongo, None, neo4j)
    # Los vectores se reutilizan del índice anterior si el texto del producto no cambió.
    vectores = indice.adjuntar_vectores(es, documentos, indice=nuevo)
    resumen = indice.escribir_documentos(es, documentos, indice=nuevo, version=version, refrescar=True)
    resumen['vectores'] = vectores
    anteriores = indice.cambiar_alias(es, nuevo)
    for viejo in anteriores:
        es.indices.delete(index=viejo)
    resumen.update({'indice': nuevo, 'reemplazados': anteriores})
    return resumen


def main() -> None:
    parser = argparse.ArgumentParser(description='Índice de búsqueda de productos.')
    modo = parser.add_mutually_exclusive_group()
    modo.add_argument('--recrear', action='store_true', help='Índice nuevo + cambio atómico de alias.')
    modo.add_argument('--diff', action='store_true', help='Solo productos desfasados.')
    args = parser.parse_args()

    es = get_es().options(request_timeout=30)
    mongo = get_mongo_db()
    neo4j = _neo4j_driver()
    with SessionLocal() as mysql_db:
        if args.recrear:
            resumen = recrear(es, mysql_db, mongo, neo4j)
        elif args.diff:
            resumen = indice.reconciliar_desfasados(es, mysql_db, mongo, neo4j)
        else:
            resumen = sincronizar(es, mysql_db, mongo, neo4j)

    total = es.count(index=settings.ES_INDEX_ALIAS)['count']
    print(f'Índice de búsqueda ({indice.indice_actual(es)}): {resumen} · documentos={total}')


if __name__ == '__main__':
    main()
