# Escala del índice vectorial: 100 000 y 1 000 000 de vectores (fase 7)

Generado con `backend/scripts/benchmark_vectores.py`. Números crudos en `docs/evidencia/benchmark/`.

## Cómo se midió

- **Vectores**: 768 dimensiones (las del modelo mpnet), sintéticos pero agrupados en familias alrededor de los
  vectores reales del catálogo (cada familia mezcla dos productos reales más ruido). Vectores al azar puro
  serían el peor caso y no se parecen a un catálogo.
- **Índice**: el mismo mapping que producción (`dense_vector`, coseno, HNSW con m = 16 y ef_construction = 100),
  1 shard, sin réplicas. Un 5 % de documentos inactivos y 100 categorías, para medir filtros.
- **Consultas**: 200, cada una un producto real con ruido; k = 10 y `num_candidates` = 100 salvo que se indique.
- **Recall@10**: coincidencia del top 10 de Elasticsearch con el top 10 exacto calculado en numpy (float32).
- **Máquina**: una laptop con Windows; Elasticsearch 8.15 en Docker con **512 MB de heap**; la VM de Docker
  tiene 5.8 GB para todos los contenedores del proyecto (MySQL, Mongo, Redis, Cassandra, Neo4j y Elasticsearch).

## Resultados

| | 100k int8_hnsw | 100k hnsw (float32) | 1M int8_hnsw |
|---|---|---|---|
| Carga | 1 709 vectores/s (59 s) | 1 765 vectores/s (57 s) | 1 622 vectores/s (617 s) |
| Fusión a 1 segmento | 9.5 s | 27.3 s | **falló: sin memoria (heap)** |
| Disco del campo vectorial | 370 MB | 297 MB | 3 698 MB |
| Disco total del índice | 1.4 GB | 1.3 GB | 14 GB |
| Memoria que necesita el kNN (estimada) | 86 MB | 305 MB | 858 MB |
| Latencia kNN, cliente p50 / p95 | 8.6 / 10.3 ms | 8.7 / 11.3 ms | 8.8 / 10.8 ms |
| Latencia kNN, Elasticsearch p50 / p95 | 5 / 7 ms | 5 / 7 ms | 4 / 5 ms |
| Con filtro de estado, p50 / p95 | 5.3 / 6.9 ms | 5.6 / 7.4 ms | 10.9 / 14.0 ms |
| Con filtro de categoría (1 % del índice), p50 / p95 | 6.4 / 10.2 ms | 7.0 / 11.0 ms | 14.7 / 19.2 ms |
| Consultas por segundo (8 hilos) | 556 | 551 | 328 |
| Recall@10 (num_candidates 100 / 200 / 400) | 0.835 / 0.846 / 0.848 | 0.980 / 0.999 / 1.000 | 0.805 / 0.806 / 0.806 |
| Recall@10 con reordenamiento float32 (200) | **0.978** (p50 10 ms) | — | **0.991** (p50 13 ms) |
| Búsqueda exacta sin HNSW (`script_score`) | 27 ms | 31 ms | 146 ms |

El índice de 1M se midió con los 32 segmentos que dejó la carga (sin fusionar). En frío, la primera pasada
tuvo p50 de 17 ms; con la caché caliente, 8.8 ms.

## Hallazgos

1. **La latencia casi no crece con el tamaño.** De 100 000 a 1 000 000 de vectores el kNN sigue en ~9 ms desde
   el cliente; HNSW recorre un grafo cuyo costo crece de forma logarítmica. Lo que sí crece es el costo de
   **filtrar** (de 6 a 15 ms con una categoría del 1 %) y baja el rendimiento con concurrencia (556 → 328
   consultas por segundo), porque hay más segmentos y más datos en la caché.

2. **Sin HNSW no escala.** La búsqueda exacta pasa de 27 ms a 146 ms (crece lineal con N): con 10 millones
   rondaría 1.5 s por consulta. Por eso se usa un índice aproximado.

3. **int8 ahorra memoria pero pierde exactitud en familias muy parecidas.** Cuantizar reduce la memoria del
   kNN a la cuarta parte (86 MB frente a 305 MB con 100k). Con estos datos sintéticos, donde las variantes
   de una familia están muy juntas, el recall se estanca en ~0.81–0.85 aunque se pidan más candidatos: el
   límite es la cuantización, no el grafo (sin cuantizar llega a 0.999). Con el catálogo real la coincidencia
   es de 97.4 % (evaluacion-vectores.md). **Solución medida**: pedir 5 veces más vecinos con int8 y
   reordenarlos con los vectores float32 originales (Elasticsearch los conserva): recall 0.978 con 100k y
   0.991 con 1M, por 13 ms.

4. **Con 512 MB de heap, 1M de vectores no se pueden fusionar en un segmento.** El `forcemerge` terminó en
   `java.lang.OutOfMemoryError: Java heap space` y Elasticsearch se reinició (el índice de la tienda no se
   afectó y el de prueba se recuperó completo). La carga y las consultas sí funcionan; lo que no cabe es
   reconstruir el grafo completo de una vez. Además, la carga solo admite ~51 MB de escrituras en curso
   (10 % del heap): lotes de más de 300 vectores o más de 2 hilos reciben 429.

5. **El 70 % del disco es el `_source`.** El vector se guarda también como texto JSON en el documento:
   1M ocupa 14 GB, de los que solo 3.7 GB son el campo vectorial. TiendaYa lo necesita hoy porque reutiliza
   el vector del índice al reindexar (si el texto no cambió, no llama al modelo). A gran escala convendría
   excluir el vector del `_source` y guardar los vectores en otro lado (por ejemplo, junto al producto).

## Qué significa para TiendaYa

- **Hoy (69 productos) y hasta ~1 millón**: Elasticsearch basta y sobra. El kNN responde en menos de 15 ms
  con filtros, y todo cabe en la máquina de desarrollo con 512 MB de heap.
- **Para pasar de ~1 millón** en un nodo: subir el heap (para fusionar segmentos y aguantar más escrituras),
  activar el reordenamiento float32 si importa la exactitud, y quitar el vector del `_source`.
- **Memoria del kNN por vector (int8)**: ~900 bytes (768 del vector + grafo). Proyección: 10M ≈ 8.6 GB;
  50M ≈ 43 GB. Ese es el número que decide cuándo un solo nodo ya no alcanza y hay que repartir en shards,
  o cuándo una base vectorial dedicada empieza a compensar (fase 8, ADR-004).
