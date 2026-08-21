# Modelo Relacional y Normalización — TiendaYa

## Por qué el esquema está en Tercera Forma Normal (3NF)

Cuando diseñé el modelo relacional de TiendaYa decidí llevar todas las tablas a 3NF porque el sistema maneja datos transaccionales críticos: órdenes, pagos, inventario y usuarios. En este tipo de datos, las anomalías de actualización tienen consecuencias reales — si el nombre de un vendedor estuviera repetido en cada producto, cambiar la razón social implicaría actualizar cientos de filas con riesgo de inconsistencia. La 3NF elimina exactamente ese problema.

## Dependencias transitivas que eliminé

### Vendedores separados de productos

El caso más claro fue la información de vendedores. En un primer borrador, la tabla `productos` tenía columnas como `vendedor_nombre`, `vendedor_email` y `vendedor_telefono` directamente. Eso viola 3NF porque `vendedor_email` depende de `vendedor_id`, no de `producto_id`. Si el vendedor cambia su teléfono, hay que tocar todas sus filas en `productos`.

La solución fue crear la tabla `vendedores` con su propia PK (`vendedor_id`) y que `productos` solo guarde la FK. Ahora un cambio en el contacto del vendedor es una sola actualización en un solo lugar.

### Categorías con jerarquía propia

Algo similar pasó con categorías. Las 8 categorías del catálogo (electrónica, ropa, hogar, libros, deportes, alimentos, juguetes, herramientas) tienen su propia descripción y pueden tener una categoría padre para subcategorías. Si hubiera embebido `categoria_nombre` y `categoria_descripcion` dentro de `productos`, habría una dependencia transitiva `producto_id → categoria_id → categoria_nombre`. La tabla `categorias` con columna `padre_id` auto-referenciada resuelve esto limpiamente.

### Métodos de pago normalizados

La tabla `pagos` referencia `metodos_pago` en lugar de guardar strings como `"tarjeta de crédito"` repetidos. Así puedo cambiar la descripción de un método de pago sin tocar la tabla de pagos.

### Direcciones como entidad separada

Un usuario puede tener múltiples direcciones. Si hubiera puesto `calle`, `ciudad`, `pais` directamente en `usuarios`, no podría representar eso sin repetir al usuario. La tabla `direcciones` con FK a `usuarios` resuelve el problema y además permite que `pedidos` referencie la dirección de envío usada en ese momento.

## La tabla puente `usuario_rol` y la relación N:M

La relación entre usuarios y roles es muchos a muchos: un usuario puede tener rol `cliente` y rol `vendedor` al mismo tiempo, y un rol puede estar asignado a miles de usuarios. En MySQL no existe un tipo de columna que represente un arreglo de FKs, así que la única forma correcta de modelar N:M en relacional es con una tabla intermedia.

`usuario_rol(usuario_id, rol_id)` tiene como PK compuesta ambas columnas, lo que garantiza que no se repita la misma asignación. Si pusiera los roles como columna en `usuarios` — por ejemplo `roles VARCHAR(200)` con valores separados por comas — no podría hacer joins eficientes ni garantizar integridad referencial.

## Por qué `precio_unitario` en `pedido_lineas` NO viola 3NF

Este es el punto más importante de entender. La tabla `pedido_lineas` guarda `precio_unitario` aunque ese precio también existe en `productos.precio`. A primera vista parece redundancia, pero es una **desnormalización deliberada con semántica propia**.

El precio en `productos` es el precio *actual*. El precio en `pedido_lineas` es el precio *al momento de la compra*. Son dos datos distintos. Si un producto pasa de Q150 a Q200 la semana siguiente, la orden que se hizo cuando valía Q150 debe seguir mostrando Q150 — eso es un requisito legal y de negocio, no un error de diseño.

En términos formales, `precio_unitario` en `pedido_lineas` depende funcionalmente de `(pedido_id, producto_ref)` que es la PK de esa tabla. No hay dependencia transitiva a través de otra columna no-clave. La 3NF sigue intacta.

Lo mismo aplica para `producto_nombre` en `pedido_lineas`: es un snapshot histórico que protege la legibilidad de órdenes antiguas aunque el producto sea renombrado o eliminado del catálogo.

## Resumen de tablas y su rol en el modelo

| Tabla | Propósito | Relación clave |
|---|---|---|
| `usuarios` | Cuenta de acceso | 1:N con direcciones, N:M con roles |
| `roles` | Catálogo de permisos | N:M con usuarios vía `usuario_rol` |
| `usuario_rol` | Tabla puente N:M | PK compuesta (usuario_id, rol_id) |
| `direcciones` | Direcciones físicas | N:1 con usuarios |
| `vendedores` | Perfil de vendedor | 1:N con productos |
| `categorias` | Jerarquía de categorías | Auto-referencia (padre_id) |
| `productos` | Catálogo en MySQL | FK a vendedor y categoría |
| `producto_imagenes` | URLs de imágenes | 1:N con productos |
| `inventario` | Stock actual | 1:1 con productos |
| `movimientos_inventario` | Auditoría de stock | N:1 con inventario |
| `pedidos` | Órdenes de compra | N:1 con usuario y dirección |
| `pedido_lineas` | Ítems de una orden | N:1 con pedido, snapshot de producto |
| `pagos` | Registro de cobros | N:1 con pedido y método de pago |
| `metodos_pago` | Catálogo de métodos | 1:N con pagos |
| `resenas` | Opiniones de clientes | N:1 con usuario y producto |
| `carritos` | Carrito activo | 1:1 con usuario |
| `carrito_items` | Ítems del carrito | N:1 con carrito |
