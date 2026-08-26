# Historial de cambios de productos

## Alcance real

TiendaYa conserva eventos en MongoDB `producto_eventos` para auditar y
reconstruir cambios documentales. Es una implementación híbrida:

- MongoDB `productos` es el estado documental actual.
- MySQL `ofertas`, `oferta_precios_historial`,
  `oferta_estados_historial`, `inventario` e
  `inventario_saldos_historial` son autoridad de precio, estado comercial y
  disponibilidad transaccional.
- `producto_eventos` no duplica precio ni inventario; esos cambios se leen de
  los intervalos autoritativos de MySQL.

## Tipos de evento

| Tipo | Origen |
|---|---|
| `PRODUCTO_CREADO` | Creación del documento |
| `DESCRIPCION_ACTUALIZADA` | Cambio documental |
| `ATRIBUTOS_ACTUALIZADOS` | Cambio del subdocumento `atributos` |
| `ESTADO_PRODUCTO_CAMBIADO` | Activación o inactivación documental |
| `PRODUCTO_DESCONTINUADO` | Retiro lógico del producto |

Cada evento conserva `producto_id` —el ObjectId representado como texto—,
`tipo_evento`, valores anteriores y nuevos, usuario, fecha y versión.

## Inserción y garantía disponible

El servicio de historial inserta nuevos documentos y el flujo normal no
actualiza eventos existentes. Sin embargo, la instancia actual **no configura
un rol MongoDB limitado a `insert` y `find`**, por lo que no se afirma
inmutabilidad impuesta por permisos del motor.

El outbox sincroniza proyecciones operativas, pero ya no copia esos cambios al
historial documental. El índice heredado `uidx_evento_outbox` se conserva para
compatibilidad e idempotencia durante despliegues incrementales.

Si se necesitara inmutabilidad regulatoria, habría que crear un usuario de
aplicación específico sin permisos `update`/`delete`, separar las tareas
administrativas y auditar esos permisos como parte del despliegue.

## Reconstrucción por replay

`reconstruir_estado(producto_id, fecha)` consulta los eventos hasta la fecha,
los ordena por `version` y aplica:

1. `PRODUCTO_CREADO` como estado inicial.
2. Cambios documentales de descripción, atributos o estado.
3. El retiro lógico cuando aparece `PRODUCTO_DESCONTINUADO`.

La respuesta de `GET /api/v1/admin/products/{id}/state-at` combina ese replay
documental con los intervalos MySQL vigentes en el instante solicitado. Por
eso devuelve una lista `ofertas` y no un único precio del producto. Cada
oferta incluye vendedor, SKU, precio, estado y saldo de inventario históricos.

## Histórico diario de precios por oferta

`GET /api/v1/admin/products/{id}/price-history` acepta los parámetros
opcionales `desde` y `hasta` en formato `YYYY-MM-DD`. La consulta devuelve una
serie independiente por oferta, incluidas las que hoy están pausadas o
descontinuadas.

Si una oferta cambia de precio varias veces durante un mismo día, el punto de
ese día es el último precio que estaba vigente a las `23:59:59` en horario de
Guatemala. La pantalla administrativa presenta estas series en una gráfica y
permite filtrar el rango.

La restricción `uq_oferta_vendedor_producto` impide que un mismo vendedor
tenga dos ofertas diferentes para el mismo producto. Distintos vendedores sí
producen líneas independientes.

La función devuelve la versión aplicada y la fecha convertida a Guatemala
(UTC-6). Para el volumen actual —65 productos y decenas de eventos por
producto— se usa replay completo sin snapshots.

## Límites de la reconstrucción

- Solo reconstruye los campos incluidos efectivamente en los eventos.
- El precio contractual de una compra se consulta en
  `pedido_lineas.precio_unitario`.
- El historial de precio autoritativo se consulta en
  `oferta_precios_historial`.
- El estado/SKU/vendedor histórico se consulta en
  `oferta_estados_historial`; el saldo histórico se consulta en
  `inventario_saldos_historial`.
- Para instalaciones existentes, la migración registra como intervalo inicial
  el estado y saldo encontrados durante el backfill. A partir de ese corte,
  cada cambio realizado por la aplicación conserva intervalos exactos.
- Un fallo del worker puede retrasar la proyección actual en MongoDB, pero no
  altera el precio, el estado comercial ni el stock confirmados en MySQL.

## Índices

```javascript
db.producto_eventos.createIndex(
  { producto_id: 1, timestamp: -1 },
  { name: "idx_eventos_producto_timestamp" }
)

db.producto_eventos.createIndex(
  { outbox_id: 1 },
  { unique: true, sparse: true, name: "uidx_evento_outbox" }
)
```

Las pruebas de replay, completitud e idempotencia están en
`backend/tests/test_product_history.py` y
`backend/tests/test_phase5_outbox.py`. El muestreo diario y la reconstrucción
combinada se prueban en `backend/tests/test_offer_temporal_history.py`.
## Línea de tiempo administrativa unificada

La pantalla de historial combina dos fuentes autoritativas y permite filtrar
por fecha y fuente:

- **MongoDB (`producto_eventos`)**: creación, descripción, atributos y estado
  documental del producto.
- **MySQL**: precio por oferta (`oferta_precios_historial`), estado comercial
  (`oferta_estados_historial`) e inventario (`inventario_saldos_historial`).

El API ordena todos los eventos por su instante real en horario de Guatemala.
Los cambios de precio e inventario ya no se duplican en MongoDB. El script
`repair_mongo_product_history.py` respalda y retira eventos operativos heredados
o fechados antes de la creación del producto.
