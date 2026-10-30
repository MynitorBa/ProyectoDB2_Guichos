"""Benchmark de escala del índice vectorial (Entrega 4, fase 7).

¿Aguanta Elasticsearch el kNN con 100 000 o 1 000 000 de productos? Genera N
vectores sintéticos de las mismas dimensiones que el modelo, agrupados
alrededor de los vectores reales del catálogo (como variantes y productos de
una misma familia; vectores al azar serían el peor caso y poco realista), los
indexa con el mismo mapping que producción y mide:

- carga: documentos por segundo y tiempo de fusión de segmentos;
- espacio: disco del campo vectorial y estimación de memoria necesaria;
- latencia del kNN (p50/p95/p99) con y sin filtro, y consultas por segundo
  con varios hilos;
- calidad: recall@10 frente a la búsqueda exacta (numpy, float32) con
  distintos ``num_candidates``;
- búsqueda exacta dentro de Elasticsearch (``script_score``), para ver por qué
  hace falta el índice aproximado (HNSW).

El índice de prueba (``bench_vectores_*``) es independiente del de la tienda y
se borra al terminar salvo ``--conservar``. Resultados en
docs/evidencia/benchmark/vectores_<n>_<tipo>.json.

Crea y borra índices: necesita el usuario indexador de Elasticsearch (el del backend
no puede crear índices):
    $env:ES_USERNAME = 'tiendaya_indexador'; $env:ES_PASSWORD = '<ES_INDEXADOR_PASSWORD del .env raíz>'

Uso (desde backend/):
    venv/Scripts/python.exe scripts/benchmark_vectores.py --n 100000
    venv/Scripts/python.exe scripts/benchmark_vectores.py --n 100000 --tipo hnsw   # sin cuantizar
    venv/Scripts/python.exe scripts/benchmark_vectores.py --n 1000000
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from elasticsearch import helpers

RAIZ_BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ_BACKEND))

from app.core.config import settings  # noqa: E402
from app.core.db_elastic import get_es  # noqa: E402

SALIDA = RAIZ_BACKEND.parent / 'docs' / 'evidencia' / 'benchmark'
CATEGORIAS = 100          # el filtro por categoría deja ~1 % del índice
CONSULTAS = 200
CONSULTAS_EXACTAS = 5
HILOS = 8
K = 10
# Con 512 MB de heap, Elasticsearch admite ~51 MB de escrituras en curso (indexing
# pressure, 10 % del heap): lotes más grandes o más hilos reciben 429.
LOTE = 300
HILOS_CARGA = 2


def vectores_reales(es) -> np.ndarray:
    respuesta = es.search(index=settings.ES_INDEX_ALIAS, size=500, source=['vector'],
                          query={'exists': {'field': 'vector'}})
    return np.array([h['_source']['vector'] for h in respuesta['hits']['hits']], dtype=np.float32)


def _normalizar(m: np.ndarray) -> np.ndarray:
    return m / np.linalg.norm(m, axis=1, keepdims=True)


def generar(reales: np.ndarray, n: int, semilla: int = 7) -> tuple[np.ndarray, np.ndarray]:
    """N vectores en familias: cada centro mezcla dos productos reales y se le suma ruido."""
    rng = np.random.default_rng(semilla)
    dims = reales.shape[1]
    centros_n = max(50, n // 200)
    a, b = rng.integers(0, len(reales), centros_n), rng.integers(0, len(reales), centros_n)
    pesos = rng.uniform(0.2, 0.8, (centros_n, 1)).astype(np.float32)
    centros = _normalizar(pesos * reales[a] + (1 - pesos) * reales[b]
                          + rng.normal(0, 0.02, (centros_n, dims)).astype(np.float32))
    asignados = rng.integers(0, centros_n, n)
    datos = np.empty((n, dims), dtype=np.float32)
    for inicio in range(0, n, 100_000):
        fin = min(n, inicio + 100_000)
        ruido = rng.normal(0, 0.012, (fin - inicio, dims)).astype(np.float32)
        datos[inicio:fin] = _normalizar(centros[asignados[inicio:fin]] + ruido)
    categorias = rng.integers(0, CATEGORIAS, n)
    return datos, categorias


def crear_indice(es, nombre: str, dims: int, tipo: str) -> None:
    es.options(ignore_status=404).indices.delete(index=nombre)
    es.indices.create(index=nombre, settings={
        'number_of_shards': 1, 'number_of_replicas': 0, 'refresh_interval': '-1',
    }, mappings={'dynamic': 'strict', 'properties': {
        'vector': {'type': 'dense_vector', 'dims': dims, 'index': True, 'similarity': 'cosine',
                   'index_options': {'type': tipo, 'm': 16, 'ef_construction': 100}},
        'categoria': {'type': 'keyword'},
        'estado': {'type': 'keyword'},
    }})


def cargar(es, nombre: str, datos: np.ndarray, categorias: np.ndarray) -> dict:
    def acciones(desde: int, hasta: int):
        for i in range(desde, hasta):
            yield {'_index': nombre, '_id': str(i), '_source': {
                'vector': np.round(datos[i], 5).tolist(),
                'categoria': f'c{categorias[i]}',
                'estado': 'activo' if i % 20 else 'inactivo',
            }}

    def parte(rango) -> int:
        errores = 0
        for ok, _ in helpers.streaming_bulk(es, acciones(*rango), chunk_size=LOTE, max_retries=10,
                                            initial_backoff=1, max_backoff=30, raise_on_error=False):
            errores += not ok
        return errores

    corte = np.linspace(0, len(datos), HILOS_CARGA + 1, dtype=int)
    inicio = time.perf_counter()
    with ThreadPoolExecutor(HILOS_CARGA) as hilos:
        errores = sum(hilos.map(parte, zip(corte[:-1], corte[1:])))
    carga = time.perf_counter() - inicio
    inicio = time.perf_counter()
    es.indices.refresh(index=nombre, request_timeout=1800)
    refresco = time.perf_counter() - inicio
    return {'segundos': round(carga, 1), 'docs_por_segundo': round(len(datos) / carga),
            'refresh_s': round(refresco, 1), 'errores': errores}


def segmentos(es, nombre: str) -> int:
    return len(es.cat.segments(index=nombre, format='json'))


def fusionar(es, nombre: str) -> float:
    inicio = time.perf_counter()
    es.options(request_timeout=7200).indices.forcemerge(index=nombre, max_num_segments=1)
    return round(time.perf_counter() - inicio, 1)


def espacio(es, nombre: str, n: int, dims: int, tipo: str) -> dict:
    uso = es.options(request_timeout=1800).indices.disk_usage(index=nombre, run_expensive_tasks=True)[nombre]
    campo = uso['fields']['vector']
    int8 = tipo.startswith('int8')
    # Lo que el kNN necesita en memoria (caché de páginas, fuera del heap):
    # los vectores con los que se compara y el grafo HNSW (~ n · m · 2 vecinos · 4 bytes).
    vectores_busqueda = n * (dims + 4) if int8 else n * dims * 4
    grafo = n * 16 * 2 * 4
    return {
        'disco_total_mb': round(uso['store_size_in_bytes'] / 2**20, 1),
        'disco_vector_mb': round(campo['total_in_bytes'] / 2**20, 1),
        'memoria_knn_estimada_mb': round((vectores_busqueda + grafo) / 2**20, 1),
        'float32_crudo_mb': round(n * dims * 4 / 2**20, 1),
    }


def memoria_contenedor() -> str | None:
    try:
        salida = subprocess.run(['docker', 'stats', '--no-stream', '--format', '{{.MemUsage}}',
                                 'tiendaya_elasticsearch'], capture_output=True, text=True, timeout=60)
        return salida.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def consultas(reales: np.ndarray, cantidad: int, semilla: int = 11) -> np.ndarray:
    """Consultas parecidas a búsquedas reales: un producto real con ruido."""
    rng = np.random.default_rng(semilla)
    base = reales[rng.integers(0, len(reales), cantidad)]
    return _normalizar(base + rng.normal(0, 0.03, base.shape).astype(np.float32))


def _knn(es, nombre: str, vector, candidatos: int, filtro: dict | None) -> tuple[list[int], float, int]:
    cuerpo = {'field': 'vector', 'query_vector': vector, 'k': K, 'num_candidates': candidatos}
    if filtro:
        cuerpo['filter'] = filtro
    inicio = time.perf_counter()
    r = es.search(index=nombre, size=K, source=False, knn=cuerpo, request_timeout=120)
    return [int(h['_id']) for h in r['hits']['hits']], (time.perf_counter() - inicio) * 1000, r['took']


def _percentiles(valores: list[float]) -> dict:
    v = np.array(valores)
    return {'p50': round(float(np.percentile(v, 50)), 1), 'p95': round(float(np.percentile(v, 95)), 1),
            'p99': round(float(np.percentile(v, 99)), 1)}


def latencias(es, nombre: str, q: np.ndarray, filtro: dict | None, candidatos: int = 100) -> dict:
    for vector in q[:20]:  # calentar la caché
        _knn(es, nombre, vector.tolist(), candidatos, filtro)
    cliente, servidor = [], []
    for vector in q:
        _, ms, took = _knn(es, nombre, vector.tolist(), candidatos, filtro)
        cliente.append(ms)
        servidor.append(took)
    return {'cliente_ms': _percentiles(cliente), 'elasticsearch_ms': _percentiles(servidor)}


def rendimiento(es, nombre: str, q: np.ndarray) -> dict:
    lista = [v.tolist() for v in np.concatenate([q, q])]
    inicio = time.perf_counter()
    with ThreadPoolExecutor(HILOS) as hilos:
        list(hilos.map(lambda v: _knn(es, nombre, v, 100, None), lista))
    return {'hilos': HILOS, 'consultas_por_segundo': round(len(lista) / (time.perf_counter() - inicio), 1)}


def recall(es, nombre: str, datos: np.ndarray, q: np.ndarray, activos: np.ndarray) -> dict:
    """Coincidencia del top 10 aproximado con el exacto, para varios num_candidates."""
    muestra = q[:100]
    exactos = []
    for inicio in range(0, len(muestra), 20):
        similitudes = muestra[inicio:inicio + 20] @ datos.T
        similitudes[:, ~activos] = -2
        exactos += [set(np.argsort(-fila)[:K].tolist()) for fila in similitudes]
    filtro = {'term': {'estado': 'activo'}}
    resultado = {}
    for candidatos in (20, 50, 100, 200, 400):
        aciertos = [len(set(_knn(es, nombre, v.tolist(), candidatos, filtro)[0]) & e) / K
                    for v, e in zip(muestra, exactos)]
        resultado[str(candidatos)] = round(sum(aciertos) / len(aciertos), 3)
    return resultado


def _knn_reordenado(es, nombre: str, vector, candidatos: int, filtro: dict) -> tuple[list[int], float]:
    """kNN que pide 5 veces más vecinos (int8) y los reordena con los vectores float32 originales."""
    inicio = time.perf_counter()
    r = es.search(index=nombre, size=K, source=False, request_timeout=120,
                  knn={'field': 'vector', 'query_vector': vector, 'k': K * 5,
                       'num_candidates': max(candidatos, K * 5), 'filter': filtro},
                  rescore={'window_size': K * 5, 'query': {
                      'query_weight': 0, 'rescore_query_weight': 1,
                      'rescore_query': {'script_score': {'query': {'match_all': {}}, 'script': {
                          'source': "cosineSimilarity(params.q, 'vector') + 1.0", 'params': {'q': vector}}}},
                  }})
    return [int(h['_id']) for h in r['hits']['hits']], (time.perf_counter() - inicio) * 1000


def recall_reordenado(es, nombre: str, datos: np.ndarray, q: np.ndarray, activos: np.ndarray) -> dict:
    """Recall@10 y latencia del kNN con sobremuestreo y reordenamiento exacto."""
    muestra = q[:100]
    similitudes = np.concatenate([muestra[i:i + 20] @ datos.T for i in range(0, len(muestra), 20)])
    similitudes[:, ~activos] = -2
    exactos = [set(np.argsort(-fila)[:K].tolist()) for fila in similitudes]
    filtro = {'term': {'estado': 'activo'}}
    resultado = {}
    for candidatos in (100, 200):
        aciertos, tiempos = [], []
        for v, e in zip(muestra, exactos):
            ids, ms = _knn_reordenado(es, nombre, v.tolist(), candidatos, filtro)
            aciertos.append(len(set(ids) & e) / K)
            tiempos.append(ms)
        resultado[str(candidatos)] = {'recall_10': round(sum(aciertos) / len(aciertos), 3),
                                      'cliente_ms': _percentiles(tiempos)}
    return resultado


def exacta(es, nombre: str, q: np.ndarray) -> dict:
    """La misma consulta recorriendo todos los documentos (sin HNSW)."""
    tiempos = []
    for vector in q[:CONSULTAS_EXACTAS]:
        inicio = time.perf_counter()
        es.search(index=nombre, size=K, source=False, request_timeout=600, query={'script_score': {
            'query': {'term': {'estado': 'activo'}},
            'script': {'source': "cosineSimilarity(params.q, 'vector') + 1.0", 'params': {'q': vector.tolist()}},
        }})
        tiempos.append((time.perf_counter() - inicio) * 1000)
    return {'consultas': len(tiempos), 'p50_ms': round(float(np.median(tiempos)), 1)}


def main() -> None:
    argumentos = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    argumentos.add_argument('--n', type=int, default=100_000)
    argumentos.add_argument('--tipo', default='int8_hnsw', choices=['int8_hnsw', 'hnsw'])
    argumentos.add_argument('--conservar', action='store_true')
    argumentos.add_argument('--reusar', action='store_true', help='usar el índice ya cargado (mismos datos: semilla fija)')
    argumentos.add_argument('--sin-fusion', action='store_true',
                            help='no fusionar a un segmento (con 512 MB de heap, 1M vectores no caben en la fusión)')
    opciones = argumentos.parse_args()

    es = get_es().options(request_timeout=600)
    reales = vectores_reales(es)
    nombre = f'bench_vectores_{opciones.n}_{opciones.tipo}'
    print(f'{nombre}: generando {opciones.n} vectores de {reales.shape[1]} dims')
    datos, categorias = generar(reales, opciones.n)
    activos = np.arange(opciones.n) % 20 != 0
    q = consultas(reales, CONSULTAS)

    resultado = {'n': opciones.n, 'dims': reales.shape[1], 'tipo': opciones.tipo, 'fecha': time.strftime('%Y-%m-%d %H:%M')}
    reusar = opciones.reusar and es.indices.exists(index=nombre) and es.count(index=nombre)['count'] == opciones.n
    if not reusar:
        crear_indice(es, nombre, reales.shape[1], opciones.tipo)
    try:
        if not reusar:
            resultado['carga'] = cargar(es, nombre, datos, categorias)
            print('carga', resultado['carga'])
        resultado['segmentos_tras_carga'] = segmentos(es, nombre)
        resultado['sin_fusionar'] = {'latencia': latencias(es, nombre, q, None)}
        print('sin fusionar', resultado['segmentos_tras_carga'], 'segmentos', resultado['sin_fusionar'])
        if opciones.sin_fusion:
            resultado['fusion_s'] = None
        else:
            resultado['fusion_s'] = fusionar(es, nombre)
            print('fusión', resultado['fusion_s'], 's')
        resultado['espacio'] = espacio(es, nombre, opciones.n, reales.shape[1], opciones.tipo)
        print('espacio', resultado['espacio'])
        resultado['latencia'] = latencias(es, nombre, q, None)
        resultado['latencia_filtro_estado'] = latencias(es, nombre, q, {'term': {'estado': 'activo'}})
        resultado['latencia_filtro_categoria_1pct'] = latencias(es, nombre, q, {'term': {'categoria': 'c7'}})
        print('latencia', resultado['latencia'], resultado['latencia_filtro_categoria_1pct'])
        resultado['rendimiento'] = rendimiento(es, nombre, q)
        resultado['memoria_contenedor'] = memoria_contenedor()
        print('rendimiento', resultado['rendimiento'], resultado['memoria_contenedor'])
        resultado['recall_10'] = recall(es, nombre, datos, q, activos)
        print('recall', resultado['recall_10'])
        if opciones.tipo.startswith('int8'):
            resultado['reordenado_float32'] = recall_reordenado(es, nombre, datos, q, activos)
            print('reordenado', resultado['reordenado_float32'])
        resultado['exacta_sin_hnsw'] = exacta(es, nombre, q)
        print('exacta', resultado['exacta_sin_hnsw'])
    finally:
        if not opciones.conservar:
            es.options(ignore_status=404).indices.delete(index=nombre)
    SALIDA.mkdir(parents=True, exist_ok=True)
    archivo = SALIDA / f'vectores_{opciones.n}_{opciones.tipo}.json'
    archivo.write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Resultados en', archivo.relative_to(RAIZ_BACKEND.parent))


if __name__ == '__main__':
    main()
