# Historial de cambios de productos

## Alcance real

TiendaYa conserva eventos en MongoDB `producto_eventos` para auditar y
reconstruir cambios documentales y proyecciones operativas. Es una
implementación híbrida:

- MongoDB `productos` es el estado documental actual.
- MySQL `ofertas`, `oferta_precios_historial` e `inventario` son autoridad de
  precio y disponibilidad transaccional.
- `producto_eventos` permite reconstrucción y auditoría, pero no sustituye la
  autoridad MySQL de precio ni inventario.

## Tipos de evento

| Tipo | Origen |
|---|---|
| `PRODUCTO_CREADO` | Creación del documento |
| `PRECIO_ACTUALIZADO` | Cambio de precio MySQL proyectado por outbox |
| `DESCRIPCION_ACTUALIZADA` | Cambio documental |
| `DISPONIBILIDAD_CAMBIADA` | Cambio de stock/estado proyectado por outbox |
| `ATRIBUTOS_ACTUALIZADOS` | Cambio del subdocumento `atributos` |
| `PRODUCTO_DESCONTINUADO` | Retiro lógico del producto |

Cada evento conserva `producto_id` —el ObjectId representado como texto—,
`tipo_evento`, valores anteriores y nuevos, usuario, fecha y versión.

## Inserción y garantía disponible

El servicio de historial inserta nuevos documentos y el flujo normal no
actualiza eventos existentes. Sin embargo, la instancia actual **no configura
un rol MongoDB limitado a `insert` y `find`**, por lo que no se afirma
inmutabilidad impuesta por permisos del motor.

Para los eventos nacidos del outbox sí existe una garantía adicional: el
índice único disperso `uidx_evento_outbox` sobre `outbox_id` evita que un
reintento inserte dos veces el mismo evento.

Si se necesitara inmutabilidad regulatoria, habría que crear un usuario de
aplicación específico sin permisos `update`/`delete`, separar las tareas
administrativas y auditar esos permisos como parte del despliegue.

## Reconstrucción por replay

`reconstruir_estado(producto_id, fecha)` consulta los eventos hasta la fecha,
los ordena por `version` y aplica:

1. `PRODUCTO_CREADO` como estado inicial.
2. Cambios de precio, descripción, disponibilidad o atributos.
3. El retiro lógico cuando aparece `PRODUCTO_DESCONTINUADO`.

La función devuelve la versión aplicada y la fecha convertida a Guatemala
(UTC-6). Para el volumen actual —65 productos y decenas de eventos por
producto— se usa replay completo sin snapshots.

## Límites de la reconstrucción

- Solo reconstruye los campos incluidos efectivamente en los eventos.
- El precio contractual de una compra se consulta en
  `pedido_lineas.precio_unitario`.
- El historial de precio autoritativo se consulta en
  `oferta_precios_historial`.
- Un fallo del worker puede retrasar el evento MongoDB, pero no altera el
  precio ni el stock confirmados en MySQL.

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
`backend/tests/test_phase5_outbox.py`.
