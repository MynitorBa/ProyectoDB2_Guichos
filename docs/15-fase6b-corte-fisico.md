# Evidencia de ejecución — Fase 6B, corte físico

**Fecha:** 24 de agosto de 2026
**Resultado:** completado y verificado.

## Respaldo y precondiciones

Antes del corte se validaron:

- 65 referencias mínimas con documento correspondiente en MongoDB.
- 16 imágenes heredadas presentes en los documentos MongoDB.
- Cero inventarios o elementos de carrito sin oferta.
- Cero líneas históricas sin oferta, subpedido o snapshots requeridos.
- Cero reseñas sin `producto_referencia_id`.
- Cero movimientos sin `inventario_id`.

Se creó el respaldo lógico:

```text
backups/phase6b_cutover_20260824_100038.json
```

El directorio `backups/` está ignorado por Git porque puede contener datos de
la instancia local.

## Objetos retirados

- Tabla descriptiva SQL `productos`.
- Tabla `producto_imagenes`, tras verificar sus 16 imágenes en MongoDB.
- Procedimiento heredado `sp_crear_pedido`.
- `carrito_items.producto_id`.
- `inventario.producto_id`.
- `movimientos_inventario.producto_id`.
- `pedido_lineas.producto_id`.
- `resenas.producto_id`.

## Contrato definitivo

- MongoDB `productos` es autoridad del contenido documental del producto.
- MySQL `producto_referencias` conserva la identidad mínima usada por reseñas.
- MySQL `ofertas` conserva vendedor, SKU, precio monetario, moneda y estado.
- MySQL `inventario` pertenece a una oferta y bodega.
- `movimientos_inventario` referencia la fila exacta de inventario.
- Carrito y checkout compran exclusivamente mediante `oferta_id`.
- Las líneas de pedido conservan oferta, subpedido y snapshots históricos
  obligatorios.

## Evidencia automatizada

- Migración física: 6 sentencias ejecutadas correctamente.
- Pruebas: **27 aprobadas**, 0 fallos.
- MySQL: 65 referencias, 65 ofertas, 31 subpedidos y corte físico confirmado.
- MongoDB: 65 productos, 477 eventos y cero referencias huérfanas.
- Proyecciones del outbox sincronizadas.
- Compilación Vite: completada correctamente.
- FastAPI permaneció disponible al finalizar.

Las 33 advertencias de pytest corresponden a APIs deprecadas de fecha/hora y
a una opción futura de `pytest-asyncio`; no representan fallos funcionales.
