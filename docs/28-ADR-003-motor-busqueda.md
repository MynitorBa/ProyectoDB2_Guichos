# ADR-003 · Motor de búsqueda para el catálogo

| Campo | |
|---|---|
| Estado | Aceptada (Entrega 3) |
| Componente | Búsqueda de productos del catálogo |
| Decisión | Incorporar **Elasticsearch 8.15** como índice de búsqueda; MongoDB queda como fuente del catálogo y respaldo |

## Contexto

La búsqueda del catálogo comparaba texto de forma exacta: `catalog_service.listar_productos`
filtraba con `$regex` sobre `nombre` y `sku`, cargaba **todos** los documentos de MongoDB,
los enriquecía con precios de MySQL y paginaba en memoria. El problema se midió antes de
decidir, con 17 consultas representativas (`backend/scripts/comparar_busqueda.py`,
[evidencia](evidencia/busqueda-linea-base.md)):

| Necesidad del portal | `$regex` (anterior) | `$text` de MongoDB |
|---|---|---|
| Errores ortográficos (`macbok`, `samsng`) | No | No (solo acierta si *otra* palabra coincide) |
| Palabras sin tilde (`audifonos`, `cafe`) | No | Sí |
| Sinónimos (`telefono` → celulares) | No | No |
| Prefijos mientras se escribe (`sams`) | Sí | No |
| Orden de palabras (`inspiron dell`) | No | Sí |
| Relevancia | No hay | Pobre (`zapatillas nike` pone primero un balón) |
| Facetas con conteo | No hay | No (requiere agregaciones aparte) |
| **Aciertos en el top 3** | **6/17** | **10/17** |

El enunciado exige tolerancia a variaciones ortográficas, ordenamiento por relevancia,
autocompletado o corrección y facetas calculadas por el motor.

## Alternativas consideradas

1. **No introducir cambios** (`$regex`). Sin costo operativo, pero no cumple tolerancia,
   relevancia ni facetas; además escanea toda la colección en cada búsqueda.
2. **Índice `$text` de MongoDB** (ya existía, sin uso). Resuelve tildes y orden de
   palabras, pero no tolera errores, no tiene sinónimos ni prefijos, su relevancia es
   rudimentaria y las facetas serían agregaciones adicionales sin relación con el puntaje.
3. **MySQL FULLTEXT**. El catálogo vive en MongoDB desde la Entrega 1; habría que duplicarlo
   en MySQL, y FULLTEXT tampoco ofrece búsqueda difusa ni sinónimos.
4. **Elasticsearch / OpenSearch**. Motor de búsqueda dedicado: analizadores por idioma,
   búsqueda difusa, sinónimos, n-gramas, *completion suggester*, *phrase suggester*,
   puntaje BM25 configurable y agregaciones. OpenSearch es una bifurcación equivalente.

## Decisión

Se adopta **Elasticsearch 8.15** (la opción de referencia del curso; OpenSearch sería
equivalente) como **proyección de solo lectura** del catálogo:

- **Mapping estricto y deliberado** (`database/elasticsearch/productos_v1.json`):
  analizador español sin tildes con *stemmer* ligero, sinónimos solo al consultar, edge
  n-gramas para prefijos, *shingles* para «¿Quisiste decir…?», atributos `nested` para
  facetas por categoría, campo `completion` para el autocompletado.
- **Elasticsearch decide qué productos y en qué orden; MySQL decide el precio.** Cada
  página de resultados se hidrata con las ofertas de MySQL, así que el motor nunca muestra
  un precio o stock propio.
- **MongoDB sigue siendo la fuente del catálogo** y el respaldo: si Elasticsearch no
  responde en 1.5 s, la búsqueda continúa con `$regex` y lo indica (`degradado: true`).

## Justificación

| Criterio | Argumento |
|---|---|
| Patrón de consulta | Búsqueda de texto libre con relevancia y facetas es exactamente el caso de uso de un índice invertido; ningún motor del sistema lo resolvía. Resultado medido: **17/17** aciertos frente a 6/17 ([evidencia](evidencia/busqueda-comparacion.md)). |
| Consistencia | No es fuente de verdad: es una proyección reconstruible. Se alimenta por el outbox con documentos armados desde el **estado actual** (idempotente e independiente del orden) y con versión externa para que un dato viejo no pise uno nuevo. Se acepta una ventana de consistencia eventual de ~1–3 s, que no afecta precios porque se hidratan desde MySQL. |
| Escalabilidad | La búsqueda deja de cargar toda la colección en memoria; las facetas se calculan dentro del motor con agregaciones. El índice va detrás de un alias, por lo que se puede reindexar sin interrupción. |
| Costo operativo | Un servicio más (~1 GB de RAM con 512 MB de heap) y un mecanismo de sincronización. Se mitiga con: reindexado completo/incremental por script, reconciliación periódica, panel de salud y degradación automática a MongoDB. |

## Consecuencias

**Beneficios**
- Tolerancia a errores, tildes, sinónimos, prefijos y orden de palabras; relevancia con
  desempate por ventas, calificación y stock.
- Facetas disyuntivas con conteos (categoría, vendedor, precio, atributos variables).
- Autocompletado y corrección ortográfica; búsqueda dentro de cada tienda.
- Latencia de ~9 ms por consulta (tras usar `127.0.0.1`: `localhost` agregaba ~40 ms en Windows).

**Limitaciones asumidas**
- Consistencia eventual: un cambio de catálogo tarda unos segundos en ser buscable.
- Las ediciones de catálogo se escriben primero en MongoDB y después se encola su evento en
  MySQL; si el proceso cae entre ambos pasos, la reconciliación cada 10 min lo corrige.
- Palabras de 4 letras o menos no se corrigen (con un error de margen, `tala` coincidiría
  con «tela» o «bala»); esas búsquedas las cubre el prefijo.
- Sin autenticación en esta entrega (se configura en la entrega final).

Detalle técnico: [`29-busqueda-elasticsearch.md`](29-busqueda-elasticsearch.md).
