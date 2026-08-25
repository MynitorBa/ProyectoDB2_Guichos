# Modelo relacional definitivo — TiendaYa

**Estado:** vigente después de la extensión de catálogo del 25 de agosto de 2026.

## Alcance de MySQL

MySQL es la autoridad de los datos cuya consistencia debe protegerse con
transacciones y llaves foráneas: usuarios, roles, vendedores, ofertas,
precios, inventario, pedidos, pagos, carrito, reseñas y notificaciones. El
contenido descriptivo del producto vive en MongoDB; MySQL conserva
`producto_referencias` como identidad relacional, clasificación controlada y
los binarios de imagen solicitados para la entrega.

El esquema final contiene 24 tablas. Se reproduce aplicando el DDL base y las
migraciones `05` a `12`; `10_phase6b_cutover.sql` retira las estructuras de
transición y `11_phase7_reference_integrity.sql` cierra las relaciones entre
categorías, referencias y ofertas. `12_catalog_images_categories.sql` agrega
imágenes BLOB y la clasificación N:M.

## Decisiones de normalización

### Usuarios, roles y vendedores

`usuarios` y `roles` se relacionan N:M mediante `usuario_rol`, evitando listas
de roles dentro de una columna. `vendedores` contiene el perfil comercial y
referencia una sola cuenta de usuario. NIT, nombre comercial y verificación no
se repiten en cada oferta.

### Producto documental frente a oferta comercial

MongoDB responde **qué es el producto**: nombre, descripción, categorías y
atributos heterogéneos. MySQL responde **quién lo vende, a qué
precio y con cuánto inventario**:

- `producto_referencias`: ObjectId documental y categoría SQL validada.
- `producto_referencia_categorias`: categorías N:M y marca de la principal.
- `producto_imagenes`: binario, MIME y orden bajo una FK a la referencia.
- `ofertas`: vendedor, SKU, precio vigente, moneda, estado y versión; su
  `producto_ref` referencia el registro anterior.
- `oferta_precios_historial`: intervalos de vigencia del precio.
- `inventario`: existencias por oferta y bodega.
- `movimientos_inventario`: entradas, salidas, ajustes, reservas y liberaciones.

La unicidad operativa del inventario es `(oferta_id, bodega)`. Un movimiento
referencia `inventario.id`, porque una misma oferta puede existir en varias
bodegas.

### Pedidos de múltiples vendedores

`pedidos` representa la compra global. `pedido_vendedores` divide esa compra
por vendedor y permite estados de entrega independientes. Cada
`pedido_lineas` pertenece a un subpedido y a una oferta.

Las líneas conservan `producto_ref`, `sku_snapshot`, `producto_nombre`,
`vendedor_nombre_snapshot` y `precio_unitario`. Estos campos no duplican el
estado actual: son hechos históricos del contrato de compra. Por la misma
razón, `pedido_direcciones` conserva la dirección utilizada aunque el cliente
edite después su libreta en `direcciones`.

### Precio vigente e histórico

`ofertas.precio_actual` es la autoridad para catálogo y checkout.
`oferta_precios_historial` registra cada intervalo con `vigente_desde` y
`vigente_hasta`, y permite una sola fila vigente por oferta. El checkout
bloquea oferta e inventario en MySQL y copia el precio cobrado a
`pedido_lineas.precio_unitario` dentro de la misma transacción.

### Reseñas

Las reseñas completas permanecen en MySQL porque deben pertenecer a un usuario
y a un producto válido. `resenas.producto_referencia_id` referencia
`producto_referencias.id` y la clave única `(usuario_id,
producto_referencia_id)` impide reseñas duplicadas del mismo usuario. MongoDB
solo contiene `resumen_resenas` como proyección de lectura para el catálogo.

### Outbox transaccional

`outbox_eventos` almacena mensajes pendientes creados dentro de la misma
transacción que modifica precio, oferta o inventario. El worker de FastAPI
actualiza después las proyecciones MongoDB y usa el identificador del outbox
como clave de idempotencia. No es una bitácora genérica: es el mecanismo de
entrega confiable entre MySQL y MongoDB.

## Catálogo de tablas

| Área | Tablas | Responsabilidad |
|---|---|---|
| Identidad | `usuarios`, `roles`, `usuario_rol`, `direcciones` | Cuentas, permisos y libreta de direcciones |
| Comercio | `vendedores`, `categorias`, `producto_referencias`, `producto_referencia_categorias`, `producto_imagenes`, `ofertas`, `oferta_precios_historial` | Perfil comercial, navegación, identidad mínima, imágenes y precio |
| Inventario | `inventario`, `movimientos_inventario` | Stock actual y trazabilidad de cambios |
| Pedidos | `pedidos`, `pedido_vendedores`, `pedido_direcciones`, `pedido_lineas` | Compra global, partes por vendedor y snapshots |
| Pagos | `metodos_pago`, `pagos` | Medio, monto y resultado del pago |
| Interacción | `carritos`, `carrito_items`, `resenas`, `notificaciones` | Intención de compra, opiniones y avisos |
| Integración | `outbox_eventos` | Sincronización confiable hacia MongoDB |

## Integridad y 3FN

- Las entidades maestras tienen PK propia y los hechos operativos las
  referencian mediante FK.
- Los atributos no clave dependen de la clave de su tabla y no de otra columna
  no clave.
- Las excepciones aparentes son snapshots históricos con semántica propia, no
  copias del estado vigente.
- No quedan FKs operativas hacia la tabla eliminada `productos`.
- `producto_referencias.categoria_id` referencia `categorias.id` y
  `ofertas.producto_ref` referencia `producto_referencias.producto_ref`.
- El único salto que MySQL no puede imponer es
  `producto_referencias.producto_ref` hacia `MongoDB.productos._id`; se valida
  desde la aplicación y con `backend/scripts/verify_setup.py`.

La evidencia del corte y los conteos verificados está en
[`15-fase6b-corte-fisico.md`](15-fase6b-corte-fisico.md). La extensión de
integridad y su validación están documentadas en
[`16-fase7-integridad-referencias.md`](16-fase7-integridad-referencias.md).
