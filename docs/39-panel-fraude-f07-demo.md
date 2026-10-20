# Panel integral de fraude y F07

## Alcance

El panel administrativo reúne siete indicadores explicables. Ninguno bloquea
compras, usuarios o vendedores automáticamente: todos son indicios sujetos a
revisión humana.

| Regla | Fuente | Señal |
|---|---|---|
| F01 | Neo4j | Concentración temporal de reseñas sobre un producto |
| F02 | Neo4j | Usuario que concentra sus reseñas en un vendedor |
| F03 | Neo4j | Pares de usuarios que reseñan productos comunes |
| F04 | MySQL; nombre del producto desde Neo4j | Reseña histórica cuya compra no pudo verificarse |
| F05 | Neo4j + MySQL | Comprador que coincide con el propietario actual del vendedor |
| F06 | MySQL | Entradas o ajustes positivos repetidos y su correlación temporal con ventas |
| F07 | MySQL | Compra pagada y reposición posterior con cantidad exactamente igual |

F01–F04 se abren desde sus tarjetas y muestran registros reales paginados.
Los contadores F01–F03 usan los mismos criterios que sus páginas; F03 cuenta
**pares de usuarios**, no grupos independientes. En la DEMO medium hay 32 pares
que cumplen el umbral de tres productos compartidos. F02 permanece en cero
porque ningún usuario concentra tres reseñas públicas verificadas en un único
vendedor; la vista muestra un estado vacío. F04 consulta las 95 reseñas no
verificadas directamente en MySQL. La falta de respaldo histórico no demuestra
que nunca existió una compra.
F05–F07 comparten una bandeja de expedientes con búsqueda, filtros por tipo,
prioridad, vigencia y estado humano, tamaños de página 10/20/50 y evidencia
JSON expandible. Los endpoints anteriores se conservaron para compatibilidad.

## Regla F07

La fuente autoritativa es MySQL. Una coincidencia confirmada requiere:

1. Línea perteneciente a un pedido confirmado, en preparación, enviado o
   entregado (incluidos estados parciales).
2. Al menos un pago aprobado y ningún pago reembolsado para el pedido.
3. Movimiento posterior de tipo `entrada` o `ajuste`, positivo, sin `pedido_id`.
4. Misma oferta, misma cantidad y una distancia máxima de 30 días.
5. Emparejamiento 1:1: una línea y un movimiento no se reutilizan; ambos
   deben tener exactamente un candidato recíproco.

Cada análisis revisa movimientos positivos de los últimos 30 días y pagos
aprobados desde 30 días antes de ese comienzo. Así, una compra de hace 31 días
puede relacionarse con una entrada de hace dos días si la distancia real entre
ambas operaciones es como máximo 30 días.

Si una reposición admite varias compras candidatas, o una compra admite varias
reposiciones candidatas, se registra como ambigua
en el resultado de la ejecución pero no crea evidencia confirmada. La alerta
se agrupa por oferta, conserva decisiones y notas humanas al recalcularse y su
prioridad es informativa o baja. No se agregó `COINCIDE_CANTIDAD` a Neo4j:
duplicaría una inferencia que MySQL puede calcular con sus claves y estados
autoritativos, y no mejora las consultas aprobadas actualmente.

## API administrativa

- `GET /api/v1/reviews/admin/fraude/indicadores/{regla}`: F01–F04 paginado.
- `GET /api/v1/reviews/admin/fraude/alertas-paginadas`: F05–F07 paginado.
- `GET /api/v1/reviews/admin/fraude/alertas`: contrato anterior sin cambios.
- `POST /api/v1/reviews/admin/fraude/recalcular`: ejecución manual compartida.
- `PATCH /api/v1/reviews/admin/fraude/alertas/{id}`: revisión y notas humanas.

Todas las rutas requieren rol administrador.

## Datos DEMO

`seed_demo_large.py` genera cantidades y fechas variadas para F06. También
incorpora escenarios F07 deterministas:

- positivos exactos y posteriores;
- cantidad diferente;
- movimiento anterior a la compra;
- coincidencia ambigua con varias líneas o entradas candidatas;
- otra oferta y ventana posterior de más de 30 días.

Las consultas de F07 también excluyen pedidos cancelados, pagos sin aprobación
y reembolsos. El generador incremental actual utiliza líneas pagadas existentes
para sus escenarios; no creó nuevos pedidos rechazados o cancelados únicamente
para esta demostración. Esos filtros se comprueban por la consulta y pruebas de
regresión, y quedan pendientes como fixtures sintéticos explícitos.

La opción `--fraud-scenarios-only` agrega exclusivamente esos patrones sobre
una DEMO existente. Mantiene guardas de puertos/nombres, usa motivos únicos y
es idempotente. Debe usarse únicamente con `.env.demo` y `--confirm-demo`.

Antes de aplicarla sobre la DEMO medium se creó el respaldo externo:

`_backups/demo-f07/tiendaya_demo_pre_f07_20261019_104327.sql`

SHA-256:
`C284A3DAD01019448CE76F4AA55B12C413364DC3904B6620B6D86A9FBC710A76`

## Resultado de validación (19 de octubre de 2026)

- Análisis manual final #8: 500 ms.
- F01: 1; F02: 0; F03: 32 pares; F04: 95. Un proceso FastAPI DEMO
  iniciado antes de los últimos cambios mostraba 20 en la tarjeta y 130 en
  el detalle. Al reiniciar exclusivamente ese proceso, ambos quedaron en 32.
- F05: 9 expedientes.
- F06: 32 expedientes.
- F07: 2 expedientes activos con coincidencia única; uno anterior pasó a
  histórico al ampliarse la consulta de compras elegibles.
- Ambigüedades F07 excluidas: 7.
- Movimientos DEMO tras escenarios controlados: 2,679 (sin cambiar pedidos,
  pagos, usuarios ni reseñas).
- Huellas duplicadas: 0.
- El expediente #15 conserva la decisión humana `descartada` después de
  recalcular.
- Reseñas: 742 (647 verificadas y 95 no verificadas).
- Pruebas enfocadas de automatización, F07 y guardas DEMO: 21 aprobadas.
- Compilación de frontend: correcta.
- La suite completa de 198 pruebas recolectadas no quedó certificada en esta
  fase: un primer intento sin la configuración DEMO apuntó a puertos de la
  instancia principal y no completó. No se interpreta como fallo de lógica.
- Paginación MySQL DEMO: 44 expedientes en cinco páginas de 10, sin solape
  entre las dos primeras; el filtro F07 activo devuelve dos y la búsqueda
  numérica por oferta responde.
- MySQL, MongoDB, Redis, Cassandra, Neo4j y Elasticsearch: los seis contenedores
  DEMO saludables. MongoDB y Cassandra quedaron reconciliados (2,376 compras
  pagadas, 1,717 resúmenes semanales por producto y 2,343 por vendedor/producto).
- Con autorización específica posterior, se confirmó que la línea sintética
  2,517 no existe en MySQL y se eliminó exclusivamente su nodo `Compra` y sus
  tres relaciones de Neo4j DEMO. El respaldo restaurable está fuera de Git en
  `_backups/neo4j-f07/neo4j_demo_compra_2517_20261019.json`, con SHA-256
  `D067BB6FDD9931B1AB5C9B0D6DE6712F8909EA9E135014B182389B13657CF4D3`.
  Neo4j conserva 2,376 compras, todas elegibles según MySQL, y cero huérfanas.
- `verify_setup.py` ahora marca Neo4j como `OK`. El resultado global aún indica
  dos ofertas MySQL sin precio/estado temporal vigente, una incidencia ajena a
  la limpieza del grafo.
- Tras cerrar Brave y Discord, Windows recuperó 8.81 GB libres y las
  aplicaciones DEMO quedaron disponibles en 5175, 8005 y 8006, sin levantar
  procesos duplicados. El login administrativo y el panel real se verificaron.
- En el navegador: F02 mostró estado vacío, F03 pares con evidencia, F04
  explicó la falta de compra verificable y F07 mostró dos expedientes activos
  y uno histórico. La búsqueda por producto redujo F07 a un expediente y la
  paginación general avanzó de la página 1 a la 2 de 3 (44 expedientes).
  El vendedor fue redirigido fuera de `/admin?section=fraud`; la API devolvió
  403 para vendedor y usuario sin sesión.
- Regresión no destructiva: 34 pruebas aprobadas y una prueba de escritura
  excluida deliberadamente. El resto de la suite de 198 pruebas recolectadas
  no se ejecutó sobre la DEMO viva por incluir escrituras y reconstrucciones.
- Compilación final del frontend (`npm run build`): correcta.

La instancia principal no fue iniciada ni modificada durante esta validación.

## Cierre de consistencia temporal DEMO (19 de octubre de 2026)

Se identificaron las ofertas DEMO #149 (Producto DEMO 0030, vendedor #7,
Q1,135) y #150 (Producto DEMO 0031, vendedor #8, Q1,183). Ambas estaban
activas desde el 19 de octubre a las 10:08:15, pero carecían de historial de
precio y de estado. No tenían líneas de pedido ni eventos Outbox propios. El
generador buscaba ofertas por SKU aunque el mismo SKU podía pertenecer a
vendedores distintos: confundió estas ofertas con las #96 y #97. Se corrigió
esa resolución en `seed_demo_large.py` para usar la pareja variante/vendedor y
se añadió una prueba de regresión; no se volvió a ejecutar el seed.

Antes de modificar MySQL DEMO se creó un volcado completo y restaurable fuera
de Git, en
`_backups/temporal-offers/tiendaya_demo_pre_temporal_20261019_1810.sql`
(2,383,818 bytes; SHA-256
`B6E353B15FD46E6B8F40EE2C5E0146E728F73B5B5A8368DBDC40F2B9B3D9629C`).
Se verificó el hash y se restauró en un esquema temporal aislado de 40 tablas.
La corrección transaccional insertó únicamente cuatro filas de historial: el
precio y estado ya registrados de cada oferta, con su fecha de creación real
como inicio de vigencia. No cambió pedidos, pagos, ofertas ni otros motores.
`verify_setup.py` pasó después de la reparación: 430 ofertas y 430 historiales
vigentes de precio y estado.

La regresión adicional encontró defectos ajenos a esas cuatro filas. Las
ofertas #149 y #150 también carecen de inventario. Trece líneas de pedido
apuntan a una oferta cuyo vendedor difiere del vendedor del subpedido (IDs
404, 499, 798, 893, 1044, 1139, 1438, 1533, 1684, 1891, 2014, 2211 y
2334); seis subtotales de subpedido no coinciden con la suma de sus líneas
(subpedidos #162, #191, #219, #228, #233 y #236). La auditoría de consistencia
I1–I6 pasó, pero I7 informó siete proyecciones de stock divergentes en
Elasticsearch. Ninguno de esos datos fue modificado ni reindexado. El
verificador de setup no detecta actualmente las ofertas sin inventario.

Se ejecutaron 35 pruebas no destructivas aprobadas, cuatro pruebas de escritura
aprobadas exclusivamente contra el esquema MySQL temporal restaurado y 19
pruebas adicionales de lectura DEMO: 16 aprobadas y tres fallidas por las
inconsistencias descritas. Total de esta fase: 55 aprobadas, tres fallidas;
dos pruebas de escritura fueron excluidas deliberadamente. La suite completa
recolecta 199 pruebas, pero no se ejecutó íntegra: varios casos reconstruyen
MongoDB, Cassandra, Neo4j, Elasticsearch o Redis, y no existe aún aislamiento
completo de esos motores con margen suficiente de RAM. No corresponde lanzarla
contra la DEMO viva ni contra PRINCIPAL.

Tras la reparación, el panel mantuvo F01=1, F02=0, F03=32, F04=95, F05=9,
F06=32 y F07=2 activos; siete coincidencias F07 permanecen ambiguas. Las
huellas de alertas siguen sin duplicados y la decisión humana del expediente
#15 se conservó. Los seis contenedores DEMO permanecieron saludables; la
instancia PRINCIPAL siguió detenida y sin cambios. El margen de RAM al cierre
descendió a 5.77 GB. Recomendación: **NO-GO para cerrar la fase como plenamente
consistente** hasta auditar y corregir por separado inventario, líneas de
pedido, subtotales y proyecciones, y disponer de aislamiento para la suite
completa. No se hizo commit ni push.

## Presentación de evidencias F01–F07 (19 de octubre de 2026)

El panel administrativo ahora abre fichas legibles en lugar de imprimir JSON:

- F01 lista todas las reseñas de cada producto en una sección desplegable con
  desplazamiento interno; F02 lista las reseñas concentradas en la tienda; F03
  compara lado a lado las reseñas de cada par de usuarios y producto común.
  Neo4j sigue seleccionando los patrones, mientras MySQL completa en lote
  nombres, estrellas, fechas y comentarios autoritativos de la página visible.
- F04 muestra comentario, calificación, moderación, evidencia disponible y
  faltante. Se conserva la advertencia de que la falta de verificación no
  demuestra que nunca existió una compra.
- F05 recupera por IDs las líneas de pedido, estado de pago, importe de la
  línea y reseñas vinculadas; la propiedad de la tienda se identifica
  expresamente como **actual**, no histórica.
- F06 presenta tabla de movimientos con responsable y una comparación
  temporal de salidas pagadas y reposiciones, sin exigir cantidades iguales.
- F07 muestra solo los pares 1:1 confirmados, con comprador, línea, pedido,
  movimiento, cantidad, fechas y tiempo transcurrido. Los candidatos ambiguos
  se mencionan únicamente como excluidos.

Las etiquetas «Reseñas históricas no verificadas» de F01–F03 describen el
segmento consultado; son distintas de la vigencia histórica de un expediente
F05–F07. La vigencia y la decisión humana aparecen por separado. Los datos
técnicos permanecen en la API, pero no ocupan la vista habitual. No cambiaron
las reglas, umbrales, contadores, filtros de Neo4j, estados ni notas.

Validación de esta mejora: `npm run build` correcto; 28 pruebas focalizadas
aisladas aprobadas y una prueba de edición de reseñas excluida porque requiere
MySQL en el puerto principal 3306. Se comprobó en el navegador de la DEMO
original el login, F03, F04, F05, F06 y F07; F01 y F02 estaban vacíos en ese
momento y su presentación quedó cubierta por pruebas de enriquecimiento. Las
consultas HTTP fueron de lectura; no se recalcularon ni moderaron alertas y no
se modificaron datos DEMO. Este resultado no certifica la integridad completa
del dataset DEMO, cuyas limitaciones se documentan arriba.
