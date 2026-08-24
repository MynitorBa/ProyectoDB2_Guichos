# Plan de migración incremental y reversible

**Estado:** Fases 1 a 6B implementadas y verificadas. El worker del outbox se
inicia y se detiene junto con el backend. El corte físico se completó el 24 de
agosto de 2026 con respaldo y pruebas integrales satisfactorias.

## Fase 0 — Congelar y medir el estado actual

- Crear tag Git del modelo relacional inicial.
- Respaldar MySQL y MongoDB.
- Registrar conteos, checksums lógicos y referencias cruzadas.
- Conservar el DDL inicial como evidencia de la Entrega 1.
- Ejecutar las pruebas actuales antes de cambiar el esquema.

Criterio de salida: 65 productos relacionados correctamente entre MySQL y MongoDB y cero referencias huérfanas.

## Fase 1 — Completar integridad sin cambiar comportamiento

- Incorporar `notificaciones` a `database/mysql/01_schema.sql`.
- Añadir sus FKs e índices.
- Añadir FKs faltantes de movimientos de inventario.
- Dejar de crear tablas desde `backend/app/main.py`.
- Corregir nombres del diagrama ER para que coincidan con el DDL real.

Esta fase no mueve datos y puede validarse independientemente.

## Fase 2 — Crear tablas nuevas en paralelo

Crear sin eliminar las tablas actuales:

- `ofertas`.
- `oferta_precios_historial`.
- `pedido_vendedores`.
- `pedido_direcciones`.
- `outbox_eventos`.

Agregar nuevas columnas de transición:

- `inventario.oferta_id` nullable.
- `pedido_lineas.oferta_id` nullable.
- `pedido_lineas.pedido_vendedor_id` nullable.
- Snapshots adicionales de SKU y vendedor.

La aplicación todavía continúa funcionando con `productos` durante esta fase.

## Fase 3 — Backfill reproducible

**Completada el 23 de agosto de 2026.** Resultado: 65 ofertas y precios
vigentes, 65 inventarios relacionados, 31 subpedidos, 30 snapshots de
dirección y 44 líneas históricas completas. La segunda ejecución produjo los
mismos conteos, confirmando la idempotencia.

Por cada fila actual de `productos`:

1. Validar `producto_ref` contra MongoDB.
2. Crear una oferta con vendedor, SKU, precio y estado actuales.
3. Crear el intervalo inicial en `oferta_precios_historial`.
4. Relacionar inventario con la oferta creada.

Por cada pedido existente:

1. Agrupar líneas por vendedor.
2. Crear un `pedido_vendedores` por grupo.
3. Asignar `oferta_id` y `pedido_vendedor_id` a las líneas.
4. Copiar snapshots faltantes.
5. Crear el snapshot de dirección desde la dirección actualmente asociada.

Advertencia: para pedidos históricos, el snapshot inicial de dirección representa la información disponible al momento de la migración; no puede probarse que nunca fue editada antes.

## Fase 4 — Lectura dual controlada

**Implementada el 23 de agosto de 2026.** El catálogo y el detalle combinan
MongoDB con ofertas MySQL; carrito y checkout usan `oferta_id` y conservan
compatibilidad temporal con `producto_id`. El panel administrativo sincroniza
ambos modelos mientras se prepara el outbox de la Fase 5.

- Catálogo: producto desde MongoDB y oferta/precio/inventario desde MySQL.
- Detalle: documento más lista de ofertas.
- Carrito: utilizar `oferta_id`, no `producto_id` como identidad comprable.
- Checkout: operar con oferta e inventario MySQL.
- Comparar temporalmente la respuesta nueva contra los datos anteriores y registrar diferencias.

No se escribe todavía exclusivamente en el modelo nuevo.

## Fase 5 — Escritura nueva con outbox

**Implementada el 23 de agosto de 2026.** Precio, inventario, vendedor y estado
se modifican primero en MySQL y generan un mensaje dentro de la misma
transacción. Un worker idempotente actualiza después la proyección de MongoDB y
su historial. Checkout ya no escribe disponibilidad directamente en MongoDB.
Los reintentos, la recuperación de mensajes y la atomicidad del cambio de
precio están cubiertos por pruebas automatizadas.

- Crear productos documentales en MongoDB.
- Crear ofertas e inventario en una transacción MySQL.
- Cambios de precio pasan por el servicio de ofertas.
- Cambios que deban reflejarse en MongoDB generan outbox.
- Worker idempotente publica eventos y marca mensajes procesados.
- Los cambios de disponibilidad dejan de actualizar MongoDB directamente desde checkout.

## Fase 6 — Retirar duplicación

### Fase 6A — Retiro lógico

**Implementada el 23 de agosto de 2026.** La operación dejó de leer o escribir
`productos.precio`, `productos.vendedor_id` y `productos.estado`. Resolución de
ofertas, panel de vendedor, notificaciones y reportes administrativos usan
`ofertas`, `pedido_vendedores` y snapshots de líneas. La tabla `productos`
permanece como compatibilidad para FKs antiguas y para crear registros durante
la transición.

### Fase 6B — Referencias finales y corte físico

**Parte aditiva implementada el 24 de agosto de 2026.** Se creó
`producto_referencias`, se relacionaron las 42 reseñas mediante FK y los 29
movimientos ahora identifican la fila exacta de inventario. La migración creó
un respaldo, fue repetida de forma idempotente y no eliminó compatibilidad.

**Corte físico completado el 24 de agosto de 2026.** Se verificaron primero 65
referencias y 16 imágenes contra MongoDB y se creó un respaldo lógico. Después
se retiraron `productos`, `producto_imagenes`, el procedimiento
`sp_crear_pedido` y las columnas `producto_id` de carrito, inventario,
movimientos, líneas y reseñas. Las 27 pruebas, el verificador MySQL/MongoDB y
la compilación Vite finalizaron correctamente. La evidencia está en
`docs/15-fase6b-corte-fisico.md`.

## Fase 7 — Alinear documentación y evidencias

**Completada el 24 de agosto de 2026.** Se actualizaron el modelo relacional,
el ER, los ADR, la arquitectura, el historial, las referencias cruzadas y el
informe de Entrega 1.

- La colección se nombra consistentemente `productos`.
- Ya no se afirman permisos append-only ni scripts de reconciliación inexistentes.
- Reseñas se documenta como autoridad SQL con resumen proyectado.
- Vendedor, precio e inventario se documentan como autoridad MySQL.
- Los marcadores de capturas fueron sustituidos por comandos y resultados reproducibles.
- El estado inicial, las migraciones y el corte final tienen evidencia versionada.

### Extensión de integridad de referencias

**Aplicada y validada el 24 de agosto de 2026.** Después de revisar el ER se
añadió una migración aditiva para convertir dos relaciones lógicas en
restricciones reales de MySQL:

- `producto_referencias.categoria_id → categorias.id`.
- `ofertas.producto_ref → producto_referencias.producto_ref`.

El backfill obtiene `categoria.slug` de cada documento MongoDB, exige que el
slug exista en MySQL y crea un respaldo antes de alterar el esquema. La API
solo permite crear productos con categorías SQL activas y desactiva, en vez de
eliminar, categorías que ya tienen productos o subcategorías.

El resultado fue de 65 referencias categorizadas, 65 ofertas enlazadas, cero
huérfanos y cero divergencias de categoría entre motores. Pasaron las 30
pruebas, el verificador integral, la compilación Vite y la comprobación de
salud de la API. Consulte `docs/16-fase7-integridad-referencias.md`.

## Estrategia de reversión

Durante las Fases 1 a 5:

- Las tablas antiguas permanecen intactas.
- Las columnas nuevas son aditivas y inicialmente nullable.
- El backfill es idempotente mediante claves únicas.
- La aplicación puede regresar temporalmente a la ruta anterior.

Después del corte físico, la reversión requiere restaurar el respaldo
`phase6b_cutover_20260824_100038.json`; la eliminación quedó aislada en
`10_phase6b_cutover.sql`.

## Validaciones obligatorias antes del corte

- Cero ofertas sin producto MongoDB.
- Cero inventarios sin oferta.
- Cero líneas de pedido sin oferta o parte de vendedor.
- Totales históricos de pedidos sin cambios.
- Precios cobrados históricos sin cambios.
- Conteos de productos e imágenes equivalentes.
- Una sola vigencia de precio abierta por oferta.
- Prueba concurrente de última unidad aprobada.
- Prueba de cambio de precio concurrente aprobada.
- Prueba de reintento del outbox aprobada.
- Reconstrucción histórica de precio y disponibilidad aprobada.
