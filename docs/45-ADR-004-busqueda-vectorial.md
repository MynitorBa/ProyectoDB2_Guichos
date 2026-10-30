# ADR-004 · Componente vectorial para la recomendación y la búsqueda semántica

| Campo | |
|---|---|
| Estado | Aceptada (Entrega final) |
| Componente | Representaciones vectoriales del catálogo |
| Decisión | Vectores en **Elasticsearch** (`dense_vector` + HNSW cuantizado a int8) calculados por un **servicio de embeddings propio**; sin base vectorial dedicada mientras no se cumplan las condiciones de migración medidas abajo |

## Contexto

El enunciado de la entrega final pide recomendación de productos por **similitud semántica de su
descripción** y una búsqueda semántica con representaciones vectoriales, «ya sea sobre una extensión de la
base relacional o sobre un componente vectorial dedicado».

Lo que el sistema tenía antes (medido con 35 consultas etiquetadas a mano,
[evidencia](evidencia/evaluacion-vectores.md)):

| Problema | Evidencia |
|---|---|
| La búsqueda de texto no entiende lenguaje natural | «herramienta para hacer agujeros en la pared» no encuentra el taladro. En consultas naturales, solo texto: P@5 = 0.07, MRR = 0.23 |
| Las recomendaciones dependen de compras | «Quienes compraron también compraron» (Neo4j) no recomienda nada para productos sin ventas |
| `more_like_this` (palabras en común) como similitud | Sin resultados para el 43 % de los productos; acierta el departamento en el 29 % de los casos |
| Duplicados en solicitudes de catálogo | «Audifonos Sony WH1000XM5» y «Audífonos Sony WH-1000XM5» no comparten palabras exactas |

## Alternativas consideradas

| Alternativa | Qué implica | Por qué no (o por qué sí) |
|---|---|---|
| **1. No introducir cambios** (texto + `more_like_this`) | Sin componentes nuevos | No cumple el requerimiento y tiene los problemas medidos arriba |
| **2. Extensión de la base relacional** | MySQL 8 no tiene tipo vectorial. MySQL 9 agrega `VECTOR` pero sin índice aproximado en la edición comunitaria; pgvector exige agregar PostgreSQL | Habría que sumar un motor relacional nuevo solo para vectores, o recorrer todos los vectores en cada consulta |
| **3. Base vectorial dedicada** (Qdrant, Milvus, Weaviate) | Un servicio más, un destino más del outbox y una segunda consulta para combinar con el texto y los filtros | Funciona, pero hoy suma costo operativo sin beneficio medible (ver condiciones de migración) |
| **4. Vectores en motores que ya existen**: Redis Stack, MongoDB Atlas Vector Search | Redis del proyecto es Redis 7 sin módulo de búsqueda; Atlas Vector Search no está en MongoDB 7 local | Exigen cambiar la distribución de un motor que ya cumple otro rol |
| **5. Elasticsearch `dense_vector`** (ya en la arquitectura desde la Entrega 3) | Un campo nuevo en el índice de productos (mapping v2) | **Elegida** |

Para generar los vectores se compararon tres modelos multilingües locales (fastembed / ONNX, sin PyTorch ni
servicios externos): MiniLM-L12 (384 dims), mpnet-base (768) y potion (estático). mpnet ganó en la
evaluación (MRR 0.745 frente a 0.664 de MiniLM).

## Decisión

- **Servicio de embeddings propio** (`embeddings_service/`, puerto 8002): carga
  `paraphrase-multilingual-mpnet-base-v2` una vez y responde vectores normalizados. El backend lo llama con
  timeout corto y circuito (`core/salud.py`); si no responde, nada se rompe.
- **Vector dentro del documento de búsqueda** (`productos_v2.json`): `dense_vector` de 768 dims, coseno,
  `int8_hnsw` (m = 16, ef_construction = 100). Solo se recalcula si cambia el texto del producto (huella
  `vector_texto_hash`); viaja por el mismo outbox que el resto del documento.
- **Cuatro funciones** sobre el mismo índice (detalle en el [documento técnico](46-vectores-implementacion.md)):
  «También te podría interesar» en la página de producto, búsqueda híbrida texto + vector, «Te podría
  interesar» en el inicio y aviso de duplicados en solicitudes de catálogo.

## Justificación

| Criterio | Argumento |
|---|---|
| Patrón de consulta | Lo que se necesita es **kNN con filtros** (solo activos, solo una tienda, excluir productos) y **combinado con texto** en la misma consulta. Elasticsearch hace las dos cosas en una sola petición, con los mismos filtros y facetas que ya tenía la búsqueda. Con una base dedicada serían dos consultas, filtros duplicados y la mezcla de resultados en el backend. |
| Consistencia | El vector viaja dentro del mismo documento que el nombre, el precio visible y el estado: no puede haber un producto buscable con un vector viejo de otro producto, ni un vector de un producto inactivo. Una base aparte sería otra proyección eventual con su propio desfase. |
| Escalabilidad | Medido con 1 millón de vectores en un nodo con 512 MB de heap ([evidencia](evidencia/escala-vectores.md)): kNN p50 de 8.8 ms y p95 de 10.8 ms, 328 consultas por segundo con 8 hilos y recall@10 de 0.99 con reordenamiento float32. La latencia casi no cambia entre 100 000 y 1 000 000. |
| Costo operativo | Ningún motor nuevo: un campo en un índice que ya existía y un servicio de embeddings sin estado (se reinicia sin perder nada). int8 reduce la memoria del kNN a la cuarta parte (86 MB frente a 305 MB con 100 000 vectores). |
| Calidad | Búsqueda híbrida: MRR 0.82 frente a 0.62 de solo texto, sin perder nada en búsquedas exactas (MRR 1.0). Similares por vector: aciertan el departamento en el 72 % de los casos frente al 29 % de `more_like_this`. |

## Cuándo migrar a una base vectorial dedicada

Una base vectorial dedicada **no es más rápida por sí misma**: el kNN de Elasticsearch ya responde en ~9 ms con
un millón de vectores. Su beneficio real aparece cuando la carga vectorial **compite** con la búsqueda de texto
en los mismos nodos, o cuando la memoria de los vectores encarece el clúster. Las condiciones, con los números
medidos en este proyecto:

| # | Condición | Umbral (medido o proyectado) | Por qué |
|---|---|---|---|
| 1 | **Memoria de los vectores** | ~900 bytes por vector con int8 (768 del vector + ~130 del grafo). 10 M de productos ≈ 8.6 GB; 50 M ≈ 43 GB por copia | Si no caben en la caché de páginas de los nodos de búsqueda, el kNN lee de disco y la latencia se dispara. Una base dedicada con cuantización binaria o vectores en disco reduce ese costo |
| 2 | **Tráfico semántico sostenido** | Más de ~300 consultas kNN por segundo por nodo (medido: 556 con 100 000 vectores y 328 con 1 M) | A partir de ahí el tráfico vectorial le quita CPU y caché a la búsqueda de texto. Separarlo protege la búsqueda principal |
| 3 | **Ritmo de escritura de vectores** | Más de ~1 600 vectores por segundo sostenidos por nodo (medido con 512 MB de heap), o reindexar decenas de millones al cambiar de modelo | Recalcular el catálogo completo bloquearía la indexación de cambios normales |
| 4 | **Mantenimiento del índice** | Con 512 MB de heap, fusionar 1 M de vectores en un segmento hizo caer el nodo por falta de memoria | Si fusionar o reconstruir el grafo exige más memoria de la que conviene dar a los nodos de búsqueda |
| 5 | **Funciones que Elasticsearch no da** | Varios vectores por producto (imagen + texto), colecciones por vendedor o filtros con cardinalidad muy alta | Las bases dedicadas están hechas para ese modelo |

**Primer paso antes de cambiar de tecnología**: separar los vectores en nodos o en un clúster de Elasticsearch
propio, porque es la misma tecnología que el equipo ya opera. Solo si con eso el costo de memoria sigue siendo
el problema (condición 1), conviene una base dedicada. La arquitectura ya lo permite sin rehacer nada: el
outbox tiene un destino por componente (Entrega 3), así que agregar un destino `vectores` es una ruta nueva
con su propio reintento y su propio circuito.

Con el catálogo actual (69 productos) y aun con 1 millón de productos, ninguna condición se cumple.

## Consecuencias

**Beneficios**
- Búsqueda en lenguaje natural: «algo para escuchar música sin cables» encuentra AirPods y audífonos Sony.
- Recomendaciones para productos sin ventas, que complementan (no reemplazan) las de Neo4j.
- Aviso de duplicados antes de que lleguen al catálogo.
- Todo sigue funcionando si el servicio de embeddings o Elasticsearch caen: solo se pierde la parte
  semántica (búsqueda de texto, más vendidos o ningún aviso).

**Limitaciones asumidas**
- **Un servicio más** (embeddings, ~1 GB en disco para el modelo, 2.5 s de carga). Si cae, las búsquedas
  nuevas no tienen vector; las repetidas usan el vector guardado en Redis.
- **El umbral de similitud (0.45) es un compromiso**: deja pasar algún resultado dudoso (una silla con
  0.50 para «portatil liviana») a cambio de no inventar resultados para consultas sin sentido.
- **int8 pierde exactitud** en familias de productos muy parecidos (recall 0.81 con datos sintéticos de
  1 M); a esa escala se activaría el reordenamiento float32 (+~5 ms).
- **Cambiar de modelo exige reindexar** todo el catálogo (índice nuevo y cambio de alias, sin cortar el
  servicio), porque vectores de modelos distintos no se pueden comparar.
- **Los documentos borrados estorban al kNN**: tras muchas reindexaciones el kNN podía devolver cero
  resultados. Se purgan cuando pasan del 20 % (cada 10 minutos).
