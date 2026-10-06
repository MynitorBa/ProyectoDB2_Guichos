#!/usr/bin/env python3
"""Construye o reconcilia el índice de búsqueda de productos en Elasticsearch.

Modos (todos idempotentes):

- Sin opciones: crea el índice si falta y sincroniza **todos** los productos
  sobre el índice vigente. Elimina del índice los productos que ya no están
  activos en MongoDB.
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
from datetime import datetime
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from elasticsearch import helpers  # noqa: E402

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


def _ids_indexados(es) -> dict[str, str | None]:
    """{producto_id: indexado_en} de todo lo que hay en el índice vigente."""
    return {
        hit['_id']: hit['_source'].get('indexado_en')
        for hit in helpers.scan(
            es, index=settings.ES_INDEX_ALIAS, _source=['indexado_en'],
            query={'query': {'match_all': {}}},
        )
    }


def _como_fecha(valor) -> datetime | None:
    if isinstance(valor, datetime):
        return valor
    if isinstance(valor, str):
        return datetime.fromisoformat(valor)
    return None


def sincronizar(es, mysql_db, mongo, neo4j) -> dict:
    indice.asegurar_indice(es)
    activos = [str(doc['_id']) for doc in mongo.productos.find({'estado': 'activo'}, {'_id': 1})]
    sobrantes = set(_ids_indexados(es)) - set(activos)
    return indice.indexar_productos(es, mysql_db, mongo, activos + sorted(sobrantes), neo4j, refrescar=True)


def recrear(es, mysql_db, mongo, neo4j) -> dict:
    nuevo = indice.nombre_indice_nuevo()
    indice.crear_indice(es, nuevo)
    version = indice.version_lectura()
    documentos = indice.construir_documentos(mysql_db, mongo, None, neo4j)
    resumen = indice.escribir_documentos(es, documentos, indice=nuevo, version=version, refrescar=True)
    anteriores = indice.cambiar_alias(es, nuevo)
    for viejo in anteriores:
        es.indices.delete(index=viejo)
    resumen.update({'indice': nuevo, 'reemplazados': anteriores})
    return resumen


def diferencias(es, mysql_db, mongo, neo4j) -> dict:
    indice.asegurar_indice(es)
    indexados = _ids_indexados(es)
    desfasados = []
    for doc in mongo.productos.find({'estado': 'activo'}, {'fecha_actualizacion': 1}):
        ref = str(doc['_id'])
        indexado_en = _como_fecha(indexados.pop(ref, None))
        actualizado = _como_fecha(doc.get('fecha_actualizacion'))
        if indexado_en is None or (actualizado and actualizado > indexado_en):
            desfasados.append(ref)
    # Lo que queda en ``indexados`` ya no está activo en MongoDB.
    refs = desfasados + sorted(indexados)
    if not refs:
        return {'indexados': 0, 'eliminados': 0, 'omitidos': 0}
    return indice.indexar_productos(es, mysql_db, mongo, refs, neo4j, refrescar=True)


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
            resumen = diferencias(es, mysql_db, mongo, neo4j)
        else:
            resumen = sincronizar(es, mysql_db, mongo, neo4j)

    total = es.count(index=settings.ES_INDEX_ALIAS)['count']
    print(f'Índice de búsqueda ({indice.indice_actual(es)}): {resumen} · documentos={total}')


if __name__ == '__main__':
    main()
