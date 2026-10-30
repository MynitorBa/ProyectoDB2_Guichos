# Vectores en TiendaYa: implementación (Entrega final)

Documento técnico de la búsqueda semántica y las recomendaciones por similitud. La decisión de usar
Elasticsearch y no una base vectorial dedicada está en el [ADR-004](45-ADR-004-busqueda-vectorial.md); las
mediciones, en [evaluacion-vectores.md](evidencia/evaluacion-vectores.md) y
[escala-vectores.md](evidencia/escala-vectores.md).

## 1. Qué es un vector aquí

Cada producto se convierte en una lista de 768 números (su **vector** o *embedding*) a partir de su texto:
nombre, categorías, descripción y atributos. El modelo está entrenado para que textos con significado parecido
den vectores cercanos, aunque no compartan palabras: «audífonos inalámbricos» queda cerca de «AirPods Pro»,
y «herramienta para hacer agujeros» cerca de «taladro percutor». La cercanía se mide con la **similitud
coseno** (1 = mismo significado; 0 = sin relación).

Buscar «los más cercanos» entre millones de vectores comparando uno por uno es lento (146 ms con 1 M). Por
eso se usa un índice **HNSW**: un grafo donde cada vector conoce a sus vecinos, y la búsqueda salta de vecino
en vecino hacia la zona correcta (~9 ms con 1 M). Es aproximado: puede perder algún vecino a cambio de la
velocidad (recall@10 de 0.974 con el catálogo real).

## 2. Componentes

```
                 texto del producto                        texto buscado
                        │                                        │
   outbox (busqueda) ───┤                                        │
                        ▼                                        ▼
   search_index_service.adjuntar_vectores          search_service.vector_consulta
     ¿cambió el texto? (huella)                       ¿está en Redis? (1 día)
        no → reutiliza el vector del índice              sí → lo usa
        sí → embeddings_client.generar ─────┐            no → embeddings_client.generar
                                            ▼
                               embeddings_service (:8002)
                               mpnet multilingüe, 768 dims
                                            │
                                            ▼
                   Elasticsearch: índice productos_v2_* (alias productos)
                   campo vector: dense_vector, coseno, int8_hnsw
                                            │
          ┌──────────────────┬──────────────┴───────┬───────────────────────┐
          ▼                  ▼                      ▼                       ▼
  similares_service   search_service.buscar   para_ti_service      duplicados_service
  (página producto)   (catálogo, híbrida)     (inicio)             (solicitudes)
```

### 2.1 Servicio de embeddings (`embeddings_service/app.py`)

- FastAPI aparte en el puerto **8002** (los tests levantan el suyo en 8092). Lo inicia `start-dev.ps1`.
- Modelo `sentence-transformers/paraphrase-multilingual-mpnet-base-v2` con **fastembed** (ONNX Runtime, sin
  PyTorch). Se descarga una vez (~1 GB) a `%LOCALAPPDATA%\TiendaYa\modelos`, fuera de OneDrive.
- El modelo se carga en segundo plano al arrancar (~2.5 s con caché). `GET /health` dice si está listo;
  `POST /embeddings {"textos": [...]}` (hasta 64) devuelve vectores normalizados, o 503 mientras carga.
- No guarda estado: se puede reiniciar en cualquier momento.

El backend lo usa por `app/services/embeddings_client.py`: lotes de 32, timeout de `EMBEDDINGS_TIMEOUT`
(10 s) y circuito en `core/salud.py` (motor `embeddings`). Si el puerto no responde, el circuito se abre de
inmediato y las llamadas siguientes devuelven `None` sin esperar.

### 2.2 El vector en el índice de búsqueda (mapping v2)

`database/elasticsearch/productos_v2.json` es el mapping de la Entrega 3 más tres campos:

| Campo | Tipo | Para qué |
|---|---|---|
| `vector` | `dense_vector`, 768 dims, coseno, `int8_hnsw` (m = 16, ef_construction = 100) | El kNN |
| `vector_texto_hash` | `keyword` | sha256 de «modelo + texto»: si no cambia, el vector se reutiliza |
| `vector_modelo` | `keyword` | Qué modelo generó el vector |

- **int8**: cada número del vector se guarda en 1 byte en lugar de 4. La memoria del kNN baja a la cuarta
  parte (86 MB frente a 305 MB con 100 000 vectores).
- **Reutilización**: al reindexar un producto (cambio de precio, stock, reseñas…) su texto casi nunca
  cambia; `adjuntar_vectores` lee el vector vigente con `mget` y solo llama al modelo si la huella es otra.
- **Sin servicio de embeddings**: el producto se indexa igual, sin vector. `reconciliar_desfasados` (cada 10
  minutos) busca los activos sin vector y los completa cuando el servicio vuelve.
- **Compatibilidad**: si el alias apunta a un índice v1 (por ejemplo, el DEMO sin migrar), no se envían
  vectores (el mapping estricto los rechazaría) y la búsqueda es solo de texto.
- **Migración**: `scripts/reindex_search.py` detecta que el índice vigente no es v2 y crea uno nuevo
  reutilizando vectores; el alias cambia de forma atómica, sin cortar la búsqueda.

### 2.3 Documentos borrados (hallazgo de la fase 6)

Cada reindexado deja la versión anterior del documento marcada como borrada hasta que Lucene fusiona
segmentos, y el grafo HNSW la sigue recorriendo. Con 245 borrados frente a 66 vivos, algunas consultas kNN
devolvían **cero resultados** con 50 o 100 candidatos. `depurar_borrados()` purga cuando pasan del 20 %
(`MAX_BORRADOS`), junto con la reconciliación. Elasticsearch retiene unos segundos los borrados recientes
(*soft deletes*), que salen en la siguiente pasada.

## 3. Las cuatro funciones

### 3.1 «También te podría interesar» (página de producto)

`GET /api/v1/products/{id}/similares?excluir=a,b&limite=8` → `similares_service.similares`

1. Lee el vector del producto del índice (no llama al modelo) y busca sus vecinos activos.
2. Excluye el propio producto y los que ya muestra la sección de compras (`excluir`), para no repetir.
3. Hidrata precio y stock desde MySQL; solo muestra productos disponibles.
4. **Caché**: los 24 vecinos se guardan en Redis una hora (`similares:{producto}`). Los vecinos cambian con
   el catálogo, no con cada visita.
5. **Respaldo**: sin Elasticsearch o sin vector, los más vendidos de su categoría (`origen: mas_vendidos`).

En la página va **debajo** de «Las personas que han comprado este artículo también han comprado estos otros:»
(Neo4j). Se complementan: las compras sugieren **complementos** (laptop → mouse); los vectores sugieren
**alternativas** (laptop → otras laptops) y funcionan con productos que nadie ha comprado.

### 3.2 Búsqueda híbrida (catálogo)

`GET /api/v1/search` con orden por relevancia → `search_service.buscar`

1. El texto buscado se convierte en vector (`vector_consulta`), guardado en Redis un día
   (`vector_consulta:{huella}`): la segunda vez no se llama al modelo.
2. Una sola consulta a Elasticsearch combina tres partes:
   - la búsqueda de texto de la Entrega 3 (errores, sinónimos, prefijos) con su puntaje;
   - una **base fija de 1000 puntos** para las coincidencias de texto **estrictas** (todas las palabras,
     frase, prefijo o SKU), para que siempre queden primero;
   - el kNN con **umbral 0.45** y peso 40, que reordena las coincidencias y agrega relacionados.
3. Cada resultado lleva `coincidencia: 'texto' | 'semantica'`; el catálogo muestra el separador
   «Relacionados con tu búsqueda» antes de los segundos.
4. Si ningún producto coincide de forma estricta, se muestran los relacionados por significado
   (`alternativa: 'semanticos'`) y, si tampoco hay, los populares de antes.
5. Ordenando por precio u otro criterio no se mezclan relacionados (solo cuentan las coincidencias); el
   respaldo por significado sí aplica cuando no hay ninguna.
6. Sin servicio de embeddings: solo texto (`semantica: false`). Sin Elasticsearch: el respaldo de la
   Entrega 3 y el plan B.

Por qué así (fase 7): con la base para **toda** coincidencia de texto, las coincidencias parciales con error
quedaban primero («novela de fantasía» → «**Nivel** láser»). Limitarla a las estrictas subió el MRR de las
consultas naturales de 0.61 a 0.67 sin perder nada en las exactas. El umbral 0.45 es el más bajo con el que
ninguna de 6 consultas sin sentido devuelve resultados.

El resaltado (`highlight_query`) usa solo la consulta de texto: resaltar con el kNN costaba 188 ms (44 ms
sin él).

### 3.3 «Te podría interesar» (inicio)

`GET /api/v1/products/para-ti?vistos=a,b` y `POST /api/v1/products/{id}/visto` → `para_ti_service`

1. **Semillas**: lo que hay en el carrito (peso 2) y lo último visto (1, 0.8, 0.64…), hasta 5.
   - Con sesión, los vistos están en Redis (`vistos:{usuario}`, 20 productos, 30 días) y sirven en cualquier
     dispositivo. El carrito se lee **sin renovar su TTL** (ver recomendaciones no es actividad del carrito).
   - Sin sesión, el navegador manda los suyos (`localStorage`, 10 productos).
2. **Una cláusula kNN por semilla** en la misma consulta, cada una con su peso; Elasticsearch suma los
   puntajes. Se descartó promediar los vectores: el promedio de una laptop y unos audífonos cae «en medio»
   y no se parece a ninguno.
3. Excluye lo visto y lo que está en el carrito. Resultado guardado 10 minutos por combinación de semillas.
4. Sin semillas o sin Elasticsearch: la sección no aparece.

### 3.4 Aviso de duplicados (solicitudes de catálogo)

`POST /api/v1/vendor/catalog-requests/products/duplicados` (mientras el vendedor escribe) y
`posibles_duplicados` en el detalle admin de solicitudes pendientes → `duplicados_service`

1. El texto de la propuesta se vectoriza igual que un producto del índice y se buscan sus vecinos.
2. Además se compara el **nombre**: el mayor entre las palabras en común y el parecido letra por letra sin
   espacios ni signos («WH1000XM5» = «WH-1000XM5»).
3. Niveles: **muy probable** (vector ≥ 0.90 o nombre ≥ 0.95) y **posible** (vector ≥ 0.80 o nombre ≥ 0.80).
4. **Es un aviso, nunca bloquea.** El vendedor puede ofrecer el producto existente («Solicitar oferta»); el
   administrador decide.

Por qué dos señales: el mismo producto da 0.82–0.96 por vector y uno de la misma familia llega a 0.79 (otra
laptop frente a la Dell, 0.835): no hay un corte limpio. Y con solo el nombre, hasta el nombre idéntico queda
en 0.795, porque el vector del índice incluye la descripción completa.

## 4. Si algo falla

| Falla | Qué pasa |
|---|---|
| Servicio de embeddings caído | Productos nuevos o editados se indexan sin vector y se completan después. Búsqueda: las consultas ya hechas usan su vector guardado en Redis; las nuevas, solo texto. Similares e inicio siguen funcionando (usan vectores ya indexados). Duplicados: sin aviso (hay que vectorizar la propuesta) |
| Elasticsearch caído | Similares → más vendidos de la categoría; búsqueda → MongoDB y plan B; inicio → sin sección; duplicados → sin aviso |
| Redis caído | Sin cachés: se consulta directo. Sin historial de vistos del servidor (queda el del navegador) |
| Producto sin vector todavía | Similares → más vendidos; no aparece en los kNN hasta la reconciliación |

## 5. Configuración

| Variable | Valor | Dónde |
|---|---|---|
| `EMBEDDINGS_URL` | `http://127.0.0.1:8002` | backend |
| `EMBEDDINGS_MODEL` | `sentence-transformers/paraphrase-multilingual-mpnet-base-v2` | backend y servicio (deben coincidir: forma parte de la huella) |
| `EMBEDDINGS_TIMEOUT` | 10 s | backend |
| `EMBEDDINGS_CACHE_DIR` | `%LOCALAPPDATA%\TiendaYa\modelos` | servicio |

Constantes de calibración (todas medidas en la fase 7): `UMBRAL_SEMANTICO = 0.45`, `BASE_TEXTO = 1000`,
`PESO_SEMANTICO = 40`, `CANDIDATOS_SEMANTICOS = 100` (`search_service`); umbrales de duplicados en
`duplicados_service`; `MAX_BORRADOS = 0.2` (`search_index_service`).

**Cambiar de modelo**: cambiar `EMBEDDINGS_MODEL` en el backend y en el servicio, y las `dims` del mapping
si cambian (nueva versión del mapping). Luego `reindex_search.py --recrear`: como la huella incluye el
modelo, todos los vectores se recalculan en el índice nuevo y el alias cambia al final.

## 6. Pruebas y evidencia

- 56 pruebas de integración: `test_embeddings_service.py`, `test_vectores_indice.py`, `test_similares.py`,
  `test_busqueda_semantica.py`, `test_para_ti.py`, `test_duplicados.py`. Cubren el camino feliz, cada
  respaldo y los casos medidos (por ejemplo, «novela de fantasía»).
- `backend/scripts/evaluar_vectores.py`: calidad con 35 consultas etiquetadas.
- `backend/scripts/benchmark_vectores.py`: escala con 100 000 y 1 000 000 de vectores.
