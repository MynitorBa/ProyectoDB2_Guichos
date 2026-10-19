# TiendaYa — Guía de explicabilidad de fraude F01–F06 y sincronización

Fecha de auditoría: 19 de octubre de 2026

Entorno revisado: `DEMO` (`tiendaya_demo`)

Alcance: análisis de solo lectura. No se aplicó la reconciliación F04, no se ejecutaron cargas `seed-medium`/`seed-full`, no se modificaron reglas ni datos y F07 continúa sin implementar.

## 1. Cómo interpretar el módulo

El módulo de fraude es explicativo y no bloquea automáticamente ventas, pagos, reseñas o movimientos. Su propósito es mostrar señales que un administrador pueda revisar. Una alerta no equivale a fraude demostrado.

Las fuentes autoritativas siguen siendo:

- MySQL: usuarios, vendedores, ofertas, pedidos, pagos, reseñas, inventario, alertas persistentes y bitácora de ejecuciones.
- Neo4j: proyección para relaciones de compra, reseñas, recomendaciones y consultas de fraude relacional.
- MongoDB: catálogo documental.
- Redis: carritos y reservas temporales.
- Cassandra: analítica temporal reconstruible.
- Elasticsearch: índice de búsqueda reconstruible.

## 2. Reglas F01–F06

| Regla | Señal | Fuente y criterio actual | Evidencia mostrada | Persistencia / prioridad |
|---|---|---|---|---|
| F01 | Bombardeo de reseñas | Neo4j; al menos 5 reseñas públicas, aprobadas y verificadas sobre un producto dentro de 24 horas | Producto, cantidad, usuarios y ventana temporal | Indicador informativo calculado al consultar; no crea expediente MySQL |
| F02 | Usuario que reseña solamente a un vendedor | Neo4j; al menos 3 reseñas verificadas y un único vendedor destino | Usuario, vendedor, productos y número de reseñas | Indicador informativo calculado al consultar |
| F03 | Grupo coordinado de reseñadores | Neo4j; pares de usuarios con al menos 3 productos reseñados en común | Usuarios, productos compartidos y cantidad de coincidencias | Indicador informativo calculado al consultar |
| F04 | Reseña sin compra verificada | MySQL/Neo4j; reseña conservada como no verificada que todavía no posee evidencia válida de compra pagada | Reseña, usuario, producto, vendedor y estado de verificación | Indicador informativo. Antes de la reconciliación autorizada posteriormente: 52; el objetivo esperado es 35, pero esta auditoría no aplicó cambios |
| F05 | Autocompra del vendedor | MySQL + propiedad actual en Neo4j; el comprador coincide con el propietario actual del vendedor y existe una compra pagada dentro de los últimos 30 días | Comprador, vendedor, oferta, línea pagada, fecha y reseña vinculada | Expediente `tipo=autocompra` persistente en `alertas_fraude`; prioridad informativa en los casos DEMO actuales |
| F06 | Reposición atípica de inventario | MySQL; movimientos positivos manuales/por propietario y correlación temporal con ventas pagadas | Movimientos, cantidades, responsables, total positivo y pares venta–reposición | Expediente `tipo=inventario_atipico` persistente; prioridad baja o media según la evidencia |

### Indicadores históricos

Las 42 reseñas base proceden de `database/mysql/04_seed.sql`, cuyo encabezado las identifica como datos de prueba representativos. No son datos personales recolectados de usuarios reales. La DEMO conserva las 42: 17 cuentan con evidencia válida de compra y 25 permanecen como históricas no verificadas. Además, `seed-small` agregó 80 reseñas sintéticas, de las cuales 10 fueron diseñadas expresamente para permanecer sin verificación.

Las reseñas históricas no verificadas se conservan por trazabilidad, pero no se publican ni alimentan recomendaciones como si fueran compras demostradas.

## 3. Auditoría de F06

### Por qué se repite el valor 105

`backend/scripts/seed_demo_large.py` selecciona las primeras 20 ofertas del bloque sintético y genera tres movimientos positivos de tipo `ajuste` para cada una. Las cantidades son siempre 25, 35 y 45 unidades; por eso cada expediente suma exactamente **105 unidades**.

No se trata de una constante fija dentro de la regla F06. Es un patrón homogéneo del generador DEMO. `backend/app/services/fraud_detection_service.py` suma individualmente los movimientos reales de cada oferta y coloca ese resultado en `unidades_positivas`.

Los motivos de los expedientes también se calculan con los datos de cada candidato, pero el texto utiliza una plantilla. Debido a que los 20 escenarios poseen los mismos conteos y cantidades, las justificaciones resultan muy parecidas.

### Verificación de suma, responsables y huellas

- Expedientes F06 activos revisados: 20.
- Ofertas afectadas: 66 a 85.
- En cada oferta: `25 + 35 + 45 = 105`.
- Las 20 sumas reales coinciden con `evidencia.unidades_positivas`.
- Los tres movimientos de cada caso son ajustes manuales sin `pedido_id`.
- El usuario responsable es el propietario actual del vendedor en los 20 casos.
- Huellas distintas: 20 de 20. La huella SHA-256 incluye tipo, usuario, vendedor, producto y oferta; no hay expedientes duplicados por identidad.

Las horas siguientes son las almacenadas por MySQL en la DEMO. Cada fila representa los tres movimientos de la oferta; los motivos son `Ajuste positivo DEMO F06 #1`, `#2` y `#3`, en ese orden.

| Alerta | Oferta | Vendedor / propietario sintético | Producto | Movimientos | Cantidades | Primera → última fecha | Pares salida–reposición |
|---:|---:|---|---|---|---|---|---:|
| 10 | 66 | DEMO Tienda 000 / usuario 16 | Producto DEMO 0000 | 259, 260, 261 | 25, 35, 45 | 17-oct 07:17 → 19-oct 07:17 | 3 |
| 11 | 67 | DEMO Tienda 001 / usuario 17 | Producto DEMO 0001 | 262, 263, 264 | 25, 35, 45 | 17-oct 06:17 → 19-oct 06:17 | 0 |
| 12 | 68 | DEMO Tienda 002 / usuario 18 | Producto DEMO 0002 | 265, 266, 267 | 25, 35, 45 | 17-oct 05:17 → 19-oct 05:17 | 0 |
| 13 | 69 | DEMO Tienda 003 / usuario 19 | Producto DEMO 0003 | 268, 269, 270 | 25, 35, 45 | 17-oct 04:17 → 19-oct 04:17 | 0 |
| 14 | 70 | DEMO Tienda 004 / usuario 20 | Producto DEMO 0004 | 271, 272, 273 | 25, 35, 45 | 17-oct 03:17 → 19-oct 03:17 | 0 |
| 15 | 71 | DEMO Tienda 005 / usuario 21 | Producto DEMO 0005 | 274, 275, 276 | 25, 35, 45 | 17-oct 02:17 → 19-oct 02:17 | 0 |
| 16 | 72 | DEMO Tienda 006 / usuario 22 | Producto DEMO 0006 | 277, 278, 279 | 25, 35, 45 | 17-oct 01:17 → 19-oct 01:17 | 0 |
| 17 | 73 | DEMO Tienda 007 / usuario 23 | Producto DEMO 0007 | 280, 281, 282 | 25, 35, 45 | 17-oct 00:17 → 19-oct 00:17 | 0 |
| 18 | 74 | DEMO Tienda 000 / usuario 16 | Producto DEMO 0008 | 283, 284, 285 | 25, 35, 45 | 16-oct 23:17 → 18-oct 23:17 | 0 |
| 19 | 75 | DEMO Tienda 001 / usuario 17 | Producto DEMO 0009 | 286, 287, 288 | 25, 35, 45 | 16-oct 22:17 → 18-oct 22:17 | 0 |
| 20 | 76 | DEMO Tienda 002 / usuario 18 | Producto DEMO 0010 | 289, 290, 291 | 25, 35, 45 | 16-oct 21:17 → 18-oct 21:17 | 0 |
| 21 | 77 | DEMO Tienda 003 / usuario 19 | Producto DEMO 0011 | 292, 293, 294 | 25, 35, 45 | 16-oct 20:17 → 18-oct 20:17 | 0 |
| 22 | 78 | DEMO Tienda 004 / usuario 20 | Producto DEMO 0012 | 295, 296, 297 | 25, 35, 45 | 16-oct 19:17 → 18-oct 19:17 | 0 |
| 23 | 79 | DEMO Tienda 005 / usuario 21 | Producto DEMO 0013 | 298, 299, 300 | 25, 35, 45 | 16-oct 18:17 → 18-oct 18:17 | 0 |
| 24 | 80 | DEMO Tienda 006 / usuario 22 | Producto DEMO 0014 | 301, 302, 303 | 25, 35, 45 | 16-oct 17:17 → 18-oct 17:17 | 0 |
| 25 | 81 | DEMO Tienda 007 / usuario 23 | Producto DEMO 0015 | 304, 305, 306 | 25, 35, 45 | 16-oct 16:17 → 18-oct 16:17 | 0 |
| 26 | 82 | DEMO Tienda 000 / usuario 16 | Producto DEMO 0016 | 307, 308, 309 | 25, 35, 45 | 16-oct 15:17 → 18-oct 15:17 | 0 |
| 27 | 83 | DEMO Tienda 001 / usuario 17 | Producto DEMO 0017 | 310, 311, 312 | 25, 35, 45 | 16-oct 14:17 → 18-oct 14:17 | 0 |
| 28 | 84 | DEMO Tienda 002 / usuario 18 | Producto DEMO 0018 | 313, 314, 315 | 25, 35, 45 | 16-oct 13:17 → 18-oct 13:17 | 0 |
| 29 | 85 | DEMO Tienda 003 / usuario 19 | Producto DEMO 0019 | 316, 317, 318 | 25, 35, 45 | 16-oct 12:17 → 18-oct 12:17 | 0 |

### Mecanismos de activación

Los mecanismos se superponen; no deben sumarse como grupos exclusivos:

| Mecanismo observado | Expedientes |
|---|---:|
| Tres o más ajustes manuales repetidos | 20 |
| Dos o más aumentos del propietario y al menos 25 unidades | 20 |
| Volumen positivo acumulado de al menos 25 unidades | 20 |
| Al menos un par salida–reposición | 1 |
| Lista `pares_salida_reposicion` vacía | 19 |
| Tres pares salida–reposición | 1 (oferta 66) |

La oferta 66 es la única que combina ajustes con tres ventas pagadas y confirmadas seguidas por reposiciones dentro de la ventana de tres días. Las ofertas 69 y 71 se activan por ajustes repetidos, propietario y volumen; no poseen pares correlacionados.

La correlación F06 es temporal. **No exige que la cantidad de la reposición sea exactamente igual a la cantidad vendida.** Esa comparación exacta corresponde a la propuesta F07 y no está implementada.

### Matiz de estado humano y señal técnica

Se observó que la alerta 15 (oferta 71) conserva `estado=descartada` y, a la vez, `activa=1` después de una ejecución posterior. `estado` representa la decisión humana registrada; `activa` indica que la señal volvió a encontrarse. El panel debe explicarlos por separado para no presentar una alerta descartada como si nunca hubiera reaparecido.

## 4. Auditoría de F05

El generador creó diez autocompras intencionales, pero la consulta usa una ventana móvil exacta de 30 días. Al momento de la auditoría, el caso más antiguo ya estaba algunos minutos fuera de la ventana; por eso se observan nueve expedientes y no diez.

| Alerta | Comprador = propietario actual | Vendedor | Oferta / producto | Línea / pedido | Cantidad pagada | Fecha | Reseña vinculada |
|---:|---|---:|---|---|---:|---|---|
| 1 | usuario 17 | 8 | 91 / Producto DEMO 0025 | 70 / 56 | 2 | 24-sep-2026 | `v:25`, aprobada y verificada |
| 2 | usuario 19 | 10 | 93 / Producto DEMO 0027 | 72 / 58 | 2 | 22-sep-2026 | `v:27`, aprobada y verificada |
| 3 | usuario 21 | 12 | 87 / Producto DEMO 0021 | 66 / 52 | 2 | 28-sep-2026 | `v:21`, aprobada y verificada |
| 4 | usuario 21 | 12 | 95 / Producto DEMO 0029 | 74 / 60 | 2 | 20-sep-2026 | `v:29`, aprobada y verificada |
| 5 | usuario 23 | 14 | 89 / Producto DEMO 0023 | 68 / 54 | 2 | 26-sep-2026 | `v:23`, aprobada y verificada |
| 6 | usuario 16 | 7 | 90 / Producto DEMO 0024 | 69 / 55 | 1 | 25-sep-2026 | `v:24`, aprobada y verificada |
| 7 | usuario 18 | 9 | 92 / Producto DEMO 0026 | 71 / 57 | 1 | 23-sep-2026 | `v:26`, aprobada y verificada |
| 8 | usuario 20 | 11 | 94 / Producto DEMO 0028 | 73 / 59 | 1 | 21-sep-2026 | `v:28`, aprobada y verificada |
| 9 | usuario 22 | 13 | 88 / Producto DEMO 0022 | 67 / 53 | 1 | 27-sep-2026 | `v:22`, aprobada y verificada |

Todos los casos poseen pedido entregado y pago aprobado. Hay nueve huellas distintas y no se detectaron expedientes duplicados.

Las justificaciones similares son esperables porque el fixture repite deliberadamente la misma forma de fraude y el servicio utiliza una plantilla común. La evidencia individual —comprador, vendedor, oferta, línea, pedido, fecha y reseña— sí cambia.

### Limitación de propiedad histórica

F05 compara al comprador con el **propietario actual** del vendedor proyectado en Neo4j. El sistema no conserva todavía una vigencia histórica de propiedad. Si una tienda cambió de dueño, una compra pasada podría atribuirse al propietario actual aunque no fuera dueño el día de la transacción. Por eso la evidencia declara `propiedad_historica_verificada=false` y el expediente es explicativo, no una condena automática.

## 5. Alertas de sincronización y Outbox

### Qué muestra cada indicador

| Indicador | Significado |
|---|---|
| Pendiente | Evento confirmado en MySQL que todavía no ha sido reclamado por el worker del destino |
| Procesando | Evento reclamado temporalmente por un worker |
| Error | Intento fallido recuperable; se reprograma con espera exponencial de hasta 300 segundos |
| Fallido | Se agotaron 10 intentos; requiere una decisión/reintento administrativo |
| Procesado | Proyección confirmada correctamente; el contador es histórico mientras la fila permanezca en Outbox |
| Más antiguo | Edad del evento no resuelto más antiguo entre pendiente, procesando y error |
| En pausa | Protección en memoria del proceso para un destino que está fallando; no es una bandera persistente global |

Los destinos independientes son:

- `mongo`: proyección documental.
- `busqueda`: Elasticsearch.
- `cassandra`: analítica temporal.
- `neo4j`: grafo de compras, reseñas y fraude.
- `redis`: invalidaciones/proyecciones temporales aplicables.

El Outbox escribe una fila por destino dentro de la transacción MySQL que origina el cambio. Cada destino posee su propio worker, por lo que la caída de uno no detiene a los demás. El reclamo usa bloqueo con `SKIP LOCKED`, recupera reclamos abandonados después de cinco minutos y las proyecciones están diseñadas para ser idempotentes.

### Endpoints y panel

- `GET /api/v1/admin/sync/outbox`: resumen, errores y fallidos.
- `GET /api/v1/admin/sync/outbox/eventos`: detalle paginado.
- `POST /api/v1/admin/sync/outbox/reintentar`: reintento manual; no fue utilizado en esta auditoría.
- `GET /api/v1/admin/sync/busqueda`: salud del índice Elasticsearch.
- `POST /api/v1/admin/sync/busqueda/reindexar`: reindexación; no fue utilizada.

`frontend/src/components/admin/SyncHealthSection.jsx` refresca Outbox cada 5 segundos y la salud de búsqueda cada 10 segundos.

En el snapshot DEMO auditado, los cinco destinos mostraron cero pendientes, procesando, errores, fallidos y procesados. Esto no significa que los contadores estén defectuosos: `seed-small` y sus backfills proyectaron directamente los datos y no dejaron filas históricas de Outbox. Elasticsearch estaba disponible con 105 documentos activos.

### Evolución del mecanismo

1. El Outbox original sincronizaba principalmente MySQL hacia MongoDB; Cassandra fue añadido después.
2. La migración 19 introdujo una fila por destino, reintentos con backoff, estado `fallido`, índices y administración por API.
3. La fase de resiliencia añadió recuperación, inyección controlada de fallas, pausa por destino y panel en vivo.
4. La implementación definitiva de Neo4j añadió destinos para compras/reseñas y eliminó la dependencia funcional de `COMPRO`.
5. La rama actual de fraude automático consume la arquitectura existente, pero no modifica el backend, la API, la interfaz ni la migración del Outbox.

No se ejecutaron reintentos, reindexaciones o reconstrucciones durante esta auditoría.

## 6. F07 — propuesta no implementada

F07 propone detectar coincidencias sospechosas entre una salida por venta y una entrada posterior con cantidades iguales o patrones equivalentes. Está descrita en `docs/35-propuesta-f07-coincidencia-inventario.md`, pero **no existe una regla activa, endpoint, expediente, prueba productiva ni automatización F07**.

F06 solamente correlaciona proximidad temporal y evalúa ajustes, propietario y volumen. No debe presentarse como si ya resolviera F07.

## 7. Propuesta para diversificar el generador DEMO

Esta propuesta no fue aplicada. Su objetivo es mejorar la explicabilidad sin alterar umbrales para fabricar alertas:

1. Usar una semilla determinista, pero distribuir cantidades F06 entre rangos distintos, por ejemplo 6–18, 20–45 y 50–90.
2. Separar escenarios: solo ajustes manuales, solo propietario, solo volumen, correlación temporal y controles negativos que queden debajo del umbral.
3. Alternar `entrada` y `ajuste`, motivos, usuarios responsables y vendedores; incluir movimientos de terceros que no son propietarios.
4. Variar fechas dentro de 30 días y colocar los casos válidos con margen suficiente para que no desaparezcan por minutos al presentar.
5. Preparar ofertas con cero, uno, dos y tres pares salida–reposición para explicar el umbral.
6. Incluir reposiciones con cantidades iguales y diferentes únicamente como datos de comparación; mientras F07 no exista, no etiquetarlas como detección F07.
7. Para F05, distribuir autocompras entre distintos días, cantidades y vendedores, añadir controles negativos y guardar en la evidencia el propietario observado en el momento del seed.
8. Evitar que todas las reseñas asociadas tengan la misma forma; combinar casos con y sin reseña sin dejar de exigir pago válido.
9. Registrar para cada escenario una etiqueta sintética y su resultado esperado, de modo que pueda verificarse falsos positivos y falsos negativos.
10. Mantener los perfiles `small`, `medium` y `full` idempotentes mediante `run_id`, sin tocar los datos base ni cambiar las reglas reales.

## 8. Conclusiones y pendientes

- Los 105 repetidos provienen del generador, no de un cálculo hardcodeado en F06.
- Las sumas, responsables, huellas y evidencias F06 son consistentes con MySQL DEMO.
- Los mecanismos F06 se solapan; 19 casos no tienen pares y solamente la oferta 66 posee tres.
- Los nueve expedientes F05 visibles son compras pagadas distintas; el décimo caso salió de la ventana móvil exacta.
- F05 tiene una limitación explícita: conoce al propietario actual, no la propiedad histórica al momento de compra.
- El panel de sincronización representa correctamente los estados del Outbox; el snapshot DEMO en cero se explica por carga/proyección directa.
- F07 permanece claramente separada y no implementada.
- Antes de `seed-medium`, conviene aprobar y aplicar la diversificación propuesta y decidir cómo presentar `estado` humano frente a `activa` técnica.
