# Evidencia de ejecución — Fase 6A

> Documento histórico: la compatibilidad física que permanecía en esta etapa
> fue retirada por la Fase 6B.

**Fecha:** 23 de agosto de 2026
**Resultado:** duplicación retirada de la operación sin eliminar datos.

## Cambios de autoridad

- `ofertas.precio_actual` es el único precio operativo y monetario.
- `ofertas.vendedor_id` identifica al vendedor de la oferta.
- `inventario.oferta_id` identifica las existencias comprables.
- `pedido_vendedores` determina pertenencia, subtotal y estado por vendedor.
- `pedido_lineas.producto_nombre`, `sku_snapshot` y
  `vendedor_nombre_snapshot` conservan la representación histórica.
- MongoDB suministra el nombre documental actual para el carrito y el nombre se
  fija como snapshot al confirmar el checkout.

## Dependencias retiradas

- Cambiar un precio ya no escribe `productos.precio`.
- Resolver una oferta no consulta precio ni vendedor de `productos`.
- El panel del vendedor no une pedidos mediante `productos.vendedor_id`.
- Un vendedor cambia el estado de su fila en `pedido_vendedores`, no el estado
  global de todo el pedido.
- Las notificaciones de venta usan `pedido_vendedor_id`.
- Ranking, listado y exportación de ventas usan subpedidos y snapshots.
- La reconciliación de stock recorre `ofertas` e `inventario`, no `mysql_id`.

## Compatibilidad que permanece

No se eliminaron tablas, columnas ni FKs. `productos.id` sigue presente porque
`inventario`, `carrito_items`, `movimientos_inventario`, reseñas y líneas
históricas todavía conservan referencias antiguas. La creación administrativa
genera una fila de compatibilidad mientras esas columnas sean obligatorias.

El parámetro `producto_id` del carrito y checkout sigue aceptándose para
clientes antiguos, pero se traduce inmediatamente a una oferta. El frontend
actual envía `oferta_id`.

## Evidencia

- 24 pruebas automatizadas aprobadas.
- Prueba concurrente de última unidad aprobada.
- Pruebas que alteran precio y vendedor legados confirman que la operación no
  cambia su resultado.
- Verificador: 65 ofertas, 65 inventarios, cero referencias huérfanas y
  proyecciones MongoDB sincronizadas.
- Smoke autenticado: panel de vendedor, estadísticas administrativas, ventas,
  catálogo y frontend respondieron correctamente.
- Compilación Vite de 2634 módulos completada.

## Condiciones antes de la Fase 6B

1. Mantener un periodo de observación con el modelo 6A.
2. Crear respaldo verificable de ambos motores.
3. Migrar las FKs restantes a `ofertas` o referencias documentales.
4. Decidir el diseño relacional definitivo de reseñas.
5. Probar restauración y reversión.
6. Ejecutar la eliminación física en una migración separada y explícita.
