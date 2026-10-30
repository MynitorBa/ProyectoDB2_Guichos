"""Evaluación de calidad de la búsqueda por vectores (Entrega 4, fase 7).

Mide con un conjunto etiquetado a mano (``scripts/evaluacion/consultas.json``):

1. Búsqueda: solo texto (la de la Entrega 3), solo vectores, vectores con
   umbral e híbrida (la que quedó en producción).
2. Productos similares: ``more_like_this`` (por palabras) frente a kNN.
3. Modelos: MiniLM-L12 (384 dims) frente a mpnet (768 dims), con búsqueda
   exacta en memoria para comparar solo el modelo.
4. Pérdida por HNSW + int8 frente a la búsqueda exacta.
5. Umbral de similitud: precisión y cobertura, y falsos positivos con
   consultas sin sentido.

No modifica nada. Escribe el informe en docs/evidencia/evaluacion-vectores.md
y los números crudos en docs/evidencia/evaluacion-vectores.json.

Uso (desde backend/, con Elasticsearch, Redis y el servicio de embeddings arriba):
    venv/Scripts/python.exe scripts/evaluar_vectores.py
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import numpy as np
from elasticsearch import helpers

RAIZ_BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ_BACKEND))

from app.core.config import settings  # noqa: E402
from app.core.db_elastic import get_es  # noqa: E402
from app.core.db_redis import get_redis  # noqa: E402
from app.services import search_index_service as indice  # noqa: E402
from app.services import search_service as busqueda  # noqa: E402

CONSULTAS = RAIZ_BACKEND / 'scripts' / 'evaluacion' / 'consultas.json'
SALIDA = RAIZ_BACKEND.parent / 'docs' / 'evidencia'
CACHE_MODELOS = Path(os.getenv('EMBEDDINGS_CACHE_DIR', Path(os.getenv('LOCALAPPDATA', Path.home())) / 'TiendaYa' / 'modelos'))
MODELOS = {
    'MiniLM-L12 (384)': 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2',
    'mpnet (768)': 'sentence-transformers/paraphrase-multilingual-mpnet-base-v2',
}
SIN_SENTIDO = ['hefkjdshafh', 'asdf qwer', 'xyz', 'tractor agrícola', 'boleto de avión a Miami', 'seguro de vida']
UMBRALES = [0.35, 0.40, 0.45, 0.50, 0.55, 0.60]
K = 10


# ── Métricas ──────────────────────────────────────────────────────────────────

def metricas(ranking: list[str], relevantes: set[str]) -> dict:
    top5 = ranking[:5]
    aciertos5 = sum(1 for s in top5 if s in relevantes)
    rr = next((1 / (i + 1) for i, s in enumerate(ranking[:K]) if s in relevantes), 0.0)
    return {
        'p5': aciertos5 / 5,
        'r5': aciertos5 / len(relevantes),
        'mrr': rr,
        'exito5': 1.0 if aciertos5 else 0.0,
    }


def promedio(filas: list[dict]) -> dict:
    return {clave: round(sum(f[clave] for f in filas) / len(filas), 3) for clave in filas[0]} if filas else {}


# ── Datos ─────────────────────────────────────────────────────────────────────

def catalogo(es) -> dict[str, dict]:
    """id → documento activo del índice (sku, textos, vector)."""
    docs = {}
    for hit in helpers.scan(es, index=settings.ES_INDEX_ALIAS, query={'query': {'term': {'estado': 'activo'}}},
                            _source=['sku', 'nombre', 'categorias', 'descripcion', 'texto_atributos', 'vector']):
        docs[hit['_id']] = hit['_source']
    return docs


def skus(ids: list[str], docs: dict) -> list[str]:
    return [docs[i]['sku'] for i in ids if i in docs]


# ── 1. Búsqueda ───────────────────────────────────────────────────────────────

def _cuerpo(p, vector=None, solo_vector=False):
    cuerpo = busqueda.construir_consulta(p, vector, solo_vector=solo_vector)
    for clave in ('aggs', 'suggest', 'highlight', 'post_filter'):
        cuerpo.pop(clave, None)
    return busqueda.como_argumentos(cuerpo)


def metodos_busqueda(es, redis_db, q: str) -> dict[str, list[str]]:
    p = busqueda.ParametrosBusqueda(q=q, page_size=K)
    vector = busqueda.vector_consulta(q, redis_db)
    knn = {'field': 'vector', 'query_vector': vector, 'k': K, 'num_candidates': 100,
           'filter': {'term': {'estado': 'activo'}}}
    ids = lambda r: [h['_id'] for h in r['hits']['hits']]  # noqa: E731
    return {
        'texto': ids(es.search(index=settings.ES_INDEX_ALIAS, **_cuerpo(p))),
        'vector': ids(es.search(index=settings.ES_INDEX_ALIAS, size=K, source=False, knn=knn)),
        'vector_umbral': ids(es.search(index=settings.ES_INDEX_ALIAS, size=K, source=False,
                                       knn={**knn, 'similarity': busqueda.UMBRAL_SEMANTICO})),
        'hibrida': ids(es.search(index=settings.ES_INDEX_ALIAS, **_cuerpo(p, vector))),
    }


def evaluar_busqueda(es, redis_db, docs, consultas) -> dict:
    por_metodo: dict[str, dict[str, list]] = {}
    detalle = []
    for c in consultas:
        resultados = metodos_busqueda(es, redis_db, c['q'])
        fila = {'q': c['q'], 'tipo': c['tipo']}
        for metodo, ids in resultados.items():
            m = metricas(skus(ids, docs), set(c['relevantes']))
            por_metodo.setdefault(metodo, {}).setdefault(c['tipo'], []).append(m)
            por_metodo[metodo].setdefault('todas', []).append(m)
            fila[metodo] = {'top5': skus(ids, docs)[:5], **m}
        detalle.append(fila)
    resumen = {metodo: {tipo: promedio(filas) for tipo, filas in tipos.items()} for metodo, tipos in por_metodo.items()}
    return {'resumen': resumen, 'detalle': detalle}


# ── 2. Similares: more_like_this frente a kNN ─────────────────────────────────

def familia(sku: str) -> str:
    return sku.rsplit('-', 1)[0]


def departamento(sku: str) -> str:
    return sku.split('-', 1)[0]


def evaluar_similares(es, docs, excluidos: set[str]) -> dict:
    nombre_indice = indice.indice_actual(es)
    semillas = [i for i, d in docs.items() if d['sku'] not in excluidos]
    filas = {'more_like_this': [], 'knn': []}
    for ref in semillas:
        sku = docs[ref]['sku']
        mlt = es.search(index=settings.ES_INDEX_ALIAS, size=5, source=False, query={'bool': {
            'must': {'more_like_this': {
                'fields': ['nombre', 'descripcion', 'texto_atributos', 'categorias.nombre'],
                'like': [{'_index': nombre_indice, '_id': ref}],
                'min_term_freq': 1, 'min_doc_freq': 1, 'max_query_terms': 25,
            }},
            'filter': [{'term': {'estado': 'activo'}}],
        }})
        knn = es.search(index=settings.ES_INDEX_ALIAS, size=5, source=False, knn={
            'field': 'vector', 'query_vector': docs[ref]['vector'], 'k': 6, 'num_candidates': 100,
            'filter': {'bool': {'filter': [{'term': {'estado': 'activo'}}],
                                'must_not': [{'ids': {'values': [ref]}}]}},
        })
        for metodo, respuesta in (('more_like_this', mlt), ('knn', knn)):
            vecinos = skus([h['_id'] for h in respuesta['hits']['hits']], docs)
            filas[metodo].append({
                'familia_p5': sum(familia(v) == familia(sku) for v in vecinos) / 5,
                'departamento_p5': sum(departamento(v) == departamento(sku) for v in vecinos) / 5,
                'con_resultados': 1.0 if vecinos else 0.0,
                'prueba_en_top5': sum(v in excluidos for v in vecinos) / 5,
            })
    return {metodo: promedio(f) for metodo, f in filas.items()} | {'semillas': len(semillas)}


# ── 3–5. Modelos, pérdida por HNSW + int8 y umbral ───────────────────────────

def _normalizados(vectores) -> np.ndarray:
    matriz = np.array(list(vectores), dtype=np.float32)
    return matriz / np.linalg.norm(matriz, axis=1, keepdims=True)


def evaluar_modelos(es, docs, consultas) -> dict:
    from fastembed import TextEmbedding

    ids = list(docs)
    textos = [indice.texto_vector(docs[i]) for i in ids]
    consultas_texto = [' '.join(c['q'].lower().split()) for c in consultas]
    resultado = {}
    for etiqueta, modelo_id in MODELOS.items():
        inicio = time.perf_counter()
        modelo = TextEmbedding(modelo_id, cache_dir=str(CACHE_MODELOS))
        carga = time.perf_counter() - inicio
        inicio = time.perf_counter()
        matriz = _normalizados(modelo.embed(textos))
        por_texto_ms = (time.perf_counter() - inicio) * 1000 / len(textos)
        q = _normalizados(modelo.embed(consultas_texto))
        sin_sentido = _normalizados(modelo.embed(SIN_SENTIDO))
        similitudes = q @ matriz.T
        por_tipo: dict[str, list] = {}
        for c, fila in zip(consultas, similitudes):
            orden = np.argsort(-fila)[:K]
            m = metricas(skus([ids[j] for j in orden], docs), set(c['relevantes']))
            por_tipo.setdefault(c['tipo'], []).append(m)
            por_tipo.setdefault('todas', []).append(m)
        resultado[etiqueta] = {
            'dimensiones': matriz.shape[1],
            'carga_s': round(carga, 1),
            'ms_por_producto': round(por_texto_ms, 1),
            'metricas': {tipo: promedio(f) for tipo, f in por_tipo.items()},
            'max_sin_sentido': round(float((sin_sentido @ matriz.T).max()), 3),
            'umbral': _curva_umbral(similitudes, consultas, ids, docs, sin_sentido @ matriz.T),
        }
        if modelo_id == settings.EMBEDDINGS_MODEL:
            resultado[etiqueta]['hnsw_int8'] = _perdida_hnsw(es, q, matriz, ids)
    return resultado


def _curva_umbral(similitudes, consultas, ids, docs, sin_sentido) -> list[dict]:
    """Para cada umbral: precisión y cobertura de lo que pasa el corte (consultas naturales y de tolerancia)."""
    curva = []
    for umbral in UMBRALES:
        devueltos = relevantes_devueltos = total_relevantes = 0
        for c, fila in zip(consultas, similitudes):
            if c['tipo'] == 'exacta':
                continue
            orden = [j for j in np.argsort(-fila)[:K] if fila[j] >= umbral]
            encontrados = skus([ids[j] for j in orden], docs)
            devueltos += len(encontrados)
            relevantes_devueltos += sum(s in c['relevantes'] for s in encontrados)
            total_relevantes += len(c['relevantes'])
        falsos = int(sum(min(K, int((fila >= umbral).sum())) for fila in sin_sentido))
        curva.append({
            'umbral': umbral,
            'precision': round(relevantes_devueltos / devueltos, 3) if devueltos else None,
            'cobertura': round(relevantes_devueltos / total_relevantes, 3),
            'resultados_sin_sentido': falsos,
        })
    return curva


def _perdida_hnsw(es, q: np.ndarray, matriz: np.ndarray, ids: list[str]) -> dict:
    """Coincidencia entre el top 10 exacto (float32) y el del índice (HNSW + int8)."""
    coincidencias = []
    for vector in q:
        exacto = {ids[j] for j in np.argsort(-(matriz @ vector))[:K]}
        aproximado = {h['_id'] for h in es.search(index=settings.ES_INDEX_ALIAS, size=K, source=False, knn={
            'field': 'vector', 'query_vector': vector.tolist(), 'k': K, 'num_candidates': 100,
            'filter': {'term': {'estado': 'activo'}},
        })['hits']['hits']}
        coincidencias.append(len(exacto & aproximado) / K)
    return {'recall_10': round(sum(coincidencias) / len(coincidencias), 3)}


# ── Informe ───────────────────────────────────────────────────────────────────

def _tabla(encabezado: list[str], filas: list[list]) -> str:
    lineas = ['| ' + ' | '.join(encabezado) + ' |', '|' + '---|' * len(encabezado)]
    lineas += ['| ' + ' | '.join(str(x) for x in fila) + ' |' for fila in filas]
    return '\n'.join(lineas)


def informe(datos: dict) -> str:
    b = datos['busqueda']['resumen']
    nombres = {'texto': 'Solo texto (Entrega 3)', 'vector': 'Solo vectores', 'vector_umbral': 'Vectores con umbral',
               'hibrida': 'Híbrida (producción)'}
    partes = [
        '# Evaluación de la búsqueda por vectores (fase 7)',
        '',
        f"Generado por `backend/scripts/evaluar_vectores.py` el {datos['fecha']}. Catálogo de {datos['productos']} "
        f"productos activos; {len(datos['busqueda']['detalle'])} consultas etiquetadas a mano "
        '(`backend/scripts/evaluacion/consultas.json`). Los productos de prueba creados durante el desarrollo '
        '(«CER», «Gadieles», «Ferxo»…) siguen en el índice y cuentan como no relevantes.',
        '',
        'Métricas: **P@5** (relevantes entre los 5 primeros / 5), **R@5** (relevantes encontrados en los 5 primeros / '
        'total de relevantes), **MRR** (1 / posición del primer relevante) y **Éxito@5** (consultas con al menos un '
        'relevante en los 5 primeros).',
        '',
        '## 1. Búsqueda: texto, vectores e híbrida',
        '',
    ]
    for tipo, titulo in (('todas', 'Todas las consultas'), ('exacta', 'Exactas'), ('tolerancia', 'Errores y sinónimos'),
                         ('natural', 'Lenguaje natural')):
        partes += [f'**{titulo}**', '', _tabla(['Método', 'P@5', 'R@5', 'MRR', 'Éxito@5'], [
            [nombres[m], b[m][tipo]['p5'], b[m][tipo]['r5'], b[m][tipo]['mrr'], b[m][tipo]['exito5']] for m in nombres
        ]), '']
    s = datos['similares']
    partes += [
        '## 2. Productos similares: `more_like_this` frente a kNN',
        '',
        f"Para cada uno de los {s['semillas']} productos reales, sus 5 más parecidos. Se toma como correcto que "
        'sean de la misma familia (prefijo del SKU, p. ej. `TECH-LAP`) o del mismo departamento (`TECH`).',
        '',
        _tabla(['Método', 'Misma familia (P@5)', 'Mismo departamento (P@5)', 'Con resultados', 'Productos de prueba en el top 5'], [
            [m, s[m]['familia_p5'], s[m]['departamento_p5'], s[m]['con_resultados'], s[m]['prueba_en_top5']]
            for m in ('more_like_this', 'knn')
        ]),
        '',
        '## 3. Modelos (búsqueda exacta en memoria)',
        '',
        _tabla(['Modelo', 'Dims', 'Carga (s)', 'ms por producto', 'P@5', 'MRR', 'MRR natural', 'Máx. sin sentido'], [
            [m, d['dimensiones'], d['carga_s'], d['ms_por_producto'], d['metricas']['todas']['p5'],
             d['metricas']['todas']['mrr'], d['metricas']['natural']['mrr'], d['max_sin_sentido']]
            for m, d in datos['modelos'].items()
        ]),
        '',
    ]
    for m, d in datos['modelos'].items():
        if 'hnsw_int8' in d:
            partes += [f"**Pérdida por HNSW + int8 ({m})**: el top 10 del índice coincide en un "
                       f"{round(d['hnsw_int8']['recall_10'] * 100, 1)} % con el exacto en float32.", '']
    partes += ['## 4. Umbral de similitud', '']
    for m, d in datos['modelos'].items():
        partes += [f'**{m}** (consultas naturales y de tolerancia; «sin sentido»: resultados que pasan el umbral '
                   f'para {len(SIN_SENTIDO)} consultas sin productos relacionados)', '',
                   _tabla(['Umbral', 'Precisión', 'Cobertura', 'Resultados sin sentido'], [
                       [u['umbral'], u['precision'], u['cobertura'], u['resultados_sin_sentido']] for u in d['umbral']
                   ]), '']
    partes += ['## Detalle por consulta (top 5 de cada método)', '']
    partes += [_tabla(['Consulta', 'Tipo', 'Texto', 'Híbrida', 'Vectores'], [
        [f['q'], f['tipo'], ', '.join(f['texto']['top5']) or '—', ', '.join(f['hibrida']['top5']) or '—',
         ', '.join(f['vector']['top5'])]
        for f in datos['busqueda']['detalle']
    ])]
    return '\n'.join(partes) + '\n'


def main() -> None:
    conjunto = json.loads(CONSULTAS.read_text(encoding='utf-8'))
    es, redis_db = get_es(), get_redis()
    docs = catalogo(es)
    print(f'{len(docs)} productos activos, {len(conjunto["consultas"])} consultas')
    datos = {
        'fecha': time.strftime('%Y-%m-%d %H:%M'),
        'productos': len(docs),
        'busqueda': evaluar_busqueda(es, redis_db, docs, conjunto['consultas']),
        'similares': evaluar_similares(es, docs, set(conjunto['excluidos'])),
        'modelos': evaluar_modelos(es, docs, conjunto['consultas']),
    }
    SALIDA.mkdir(parents=True, exist_ok=True)
    (SALIDA / 'evaluacion-vectores.json').write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding='utf-8')
    (SALIDA / 'evaluacion-vectores.md').write_text(informe(datos), encoding='utf-8')
    for metodo, tipos in datos['busqueda']['resumen'].items():
        print(f"{metodo:14s}", {t: (v['p5'], v['mrr']) for t, v in tipos.items()})
    print('similares', datos['similares'])
    for m, d in datos['modelos'].items():
        print(m, d['metricas']['todas'], 'natural', d['metricas']['natural'], d.get('hnsw_int8'))
    print('Informe en docs/evidencia/evaluacion-vectores.md')


if __name__ == '__main__':
    main()
