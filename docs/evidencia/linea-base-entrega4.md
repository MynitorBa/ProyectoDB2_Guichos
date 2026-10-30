# Línea base de la Entrega 4

Rama `inicio-entrega4`, creada el 30 de octubre de 2026 desde `planb_pre_entrega4`
(commit `07a2576`, idéntico en GitHub). Motores principales en Docker.

## Estado del sistema antes de empezar

| Verificación | Resultado |
|---|---|
| `pytest tests -q` | 288 aprobadas, 4 omitidas, 3 fallidas |
| `scripts/verificar_consistencia.py` | I1–I7 se cumplen |

Las 3 fallas ya existían antes del plan B y no son de esta entrega: `test_checkout_flash_convierte_reserva_y_descuenta_pool`
y las dos de `test_fulfillment_vendor_workspace` («No se identificó el inventario de la promoción flash / de esta
venta»), relacionadas con el cambio de bodegas `018935a` sobre los datos de la base principal.

## Modelo de embeddings: viabilidad en el equipo

Se usa **fastembed** (ONNX Runtime, sin PyTorch): se instaló sin problemas en Windows con Python 3.12
(`fastembed 0.9.1`). Los modelos se descargan una vez desde Hugging Face y luego funcionan sin internet.

Prueba rápida con 5 productos y 5 consultas en lenguaje natural, donde la respuesta correcta no comparte
palabras con la consulta (por ejemplo, «herramienta para hacer agujeros en la pared» → taladro):

| Modelo (multilingüe) | Dimensiones | Tamaño | Aciertos | Carga | Por texto |
|---|---|---|---|---|---|
| paraphrase-multilingual-MiniLM-L12-v2 | 384 | 0.22 GB | 3/5 | 1.0 s | 1.5 ms |
| paraphrase-multilingual-mpnet-base-v2 | 768 | 1.0 GB | 4/5 | 24 s | 4.9 ms |
| potion-multilingual-128M (estático) | 256 | 0.5 GB | 2/5 | 12.7 s | < 0.1 ms |

Conclusión: el modelo será **configurable**. La muestra es pequeña; la elección final se toma con la
evaluación sobre el catálogo real (fase 7). Cambiarlo después solo exige reindexar con un índice nuevo y
mover el alias, sin cortar el servicio.

## Búsqueda híbrida: umbral y latencia (fase 4)

Similitud coseno de la consulta con su mejor producto (modelo mpnet, índice v2 con `int8_hnsw`):

| Consulta | Mejores resultados (similitud) |
|---|---|
| algo para escuchar música sin cables | AirPods 0.56, Audífonos Sony 0.54, Bocina JBL 0.41 |
| zapatos de fútbol | Tenis Nike 0.65, Zapato Oxford 0.64, Balón Nike 0.54 |
| samsung | Galaxy A54 0.62, Redmi Note 0.53, Motorola Edge 0.53 |
| teléfono con buena cámara | Galaxy A54 0.47, Motorola Edge 0.46 |
| hefkjdshafh | 0.33 como máximo |
| xyz | 0.41 como máximo |
| tractor agrícola (no hay en el catálogo) | 0.29 como máximo |

Las consultas sin sentido o sin productos relacionados no pasan de **0.41**; las útiles quedan entre
0.46 y 0.77. Se fijó el umbral en **0.45** (`UMBRAL_SEMANTICO`). Todavía pasan resultados dudosos
cerca del umbral (por ejemplo, una silla ergonómica con 0.50 para «portatil liviana»); el umbral se
revisa con el conjunto de evaluación de la fase 7.

Latencia de `search_service.buscar` (catálogo de 69 productos, una sola máquina):

| Caso | Tiempo |
|---|---|
| Solo texto | 22–31 ms |
| Híbrida, vector de la consulta ya en Redis | 23–68 ms |
| Calcular el vector de una consulta nueva (modelo en CPU) | 170–230 ms, una sola vez por consulta |
| Híbrida con resaltado sobre la consulta kNN (antes de `highlight_query`) | 188 ms dentro de Elasticsearch |
| Híbrida con `highlight_query` solo de texto | 44 ms dentro de Elasticsearch |

El resaltado intentaba usar también la consulta kNN y era el costo dominante; se limitó al texto.

## Duplicados en solicitudes de catálogo (fase 6)

Similitud por vector entre una propuesta (nombre, descripción y categoría) y su vecino más cercano:

| Tipo | Propuesta | Vecino más cercano | Similitud |
|---|---|---|---|
| Mismo producto | Laptop Dell Inspiron 15 | Laptop Dell Inspiron 15 | 0.961 |
| Mismo producto | Dell Inspiron 15 3520 laptop | Laptop Dell Inspiron 15 | 0.854 |
| Mismo producto | Audifonos Sony WH1000XM5 | Audífonos Sony WH-1000XM5 | 0.838 |
| Mismo producto | Licuadora Oster 600 W | Licuadora Oster 600W | 0.818 |
| Mismo producto | Samsung Galaxy A54 5G 128GB | Samsung Galaxy A54 | 0.886 |
| Misma familia | Audífonos Bose QuietComfort 45 | Audífonos Sony WH-1000XM5 | 0.788 |
| Misma familia | Laptop HP Envy 13 | Laptop HP Pavilion 14 | 0.724 |
| Misma familia | Samsung Galaxy S23 Ultra | Samsung Galaxy A54 | 0.707 |
| Distinto | Bicicleta de montaña aro 29 | Casco ciclismo MTB | 0.678 |
| Distinto | Taza de cerámica con diseño maya | Café molido artesanal | 0.584 |

El mismo producto queda entre 0.82 y 0.96 y la misma familia hasta 0.79, pero no hay un corte limpio: frente a
la propuesta de la Dell, la ASUS VivoBook (otro producto) da 0.835. Con solo el nombre, sin descripción, el
nombre idéntico da 0.795. Por eso:

- el aviso tiene dos niveles (posible ≥ 0.80, muy probable ≥ 0.90) y **nunca bloquea**: decide el administrador;
- se suma el parecido del nombre (palabras en común o letra por letra sin espacios ni signos), con umbrales
  0.80 y 0.95. «WH1000XM5» frente a «WH-1000XM5» da 1.00; Galaxy S23 Ultra frente a Galaxy A54, 0.76.

## Hallazgo: documentos borrados y kNN vacío

Durante la fase 6 algunas consultas kNN devolvieron **cero resultados** con 50 o 100 candidatos y resultados
correctos con 400. El índice tenía 245 documentos borrados (versiones viejas de productos reindexados) frente a
unos 66 vivos. El grafo HNSW sigue recorriendo esas versiones; si los vecinos más cercanos están borrados, se
descartan y el kNN puede quedar vacío. Tras purgarlos (`_forcemerge?only_expunge_deletes=true`) las mismas
consultas funcionaron con 50 candidatos.

Corrección: `search_index_service.depurar_borrados()` purga cuando los borrados pasan del 20 % y corre con la
reconciliación periódica (cada 10 minutos). Además, los kNN de la búsqueda híbrida y de «Te podría interesar»
usan 100 candidatos.
