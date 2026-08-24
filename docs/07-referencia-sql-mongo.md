# Referencias cruzadas entre MySQL y MongoDB

## Restricción intermotor

MySQL no puede declarar una llave foránea hacia `MongoDB.productos._id`.
TiendaYa representa ese ObjectId hexadecimal mediante `CHAR(24)` en puntos
controlados del esquema SQL:

- `producto_referencias.producto_ref`: identidad canónica SQL y salto hacia
  MongoDB; la misma fila referencia su categoría SQL.
- `ofertas.producto_ref`: FK interna hacia
  `producto_referencias.producto_ref`.
- `pedido_lineas.producto_ref`: referencia histórica de la compra.
- `carrito_items.producto_ref`: copia auxiliar de navegación.
- `outbox_eventos.producto_ref`: destino de la proyección.

## Identidad comprable

El cliente compra una **oferta**, no un documento MongoDB. El contrato del API
recibe `oferta_id` y el checkout:

1. Agrupa cantidades por oferta.
2. Bloquea ofertas activas con `SELECT ... FOR UPDATE`.
3. Bloquea el inventario principal de esas ofertas.
4. Verifica stock dentro de la transacción MySQL.
5. Obtiene de MongoDB el nombre documental para congelarlo; si MongoDB no está
   disponible, conserva el SKU de la oferta como nombre de respaldo.
6. Crea pedido, partes por vendedor, dirección y líneas con snapshots.
7. Descuenta inventario, registra movimientos, pago y eventos outbox.
8. Confirma todo mediante un solo `COMMIT`.

El precio se toma exclusivamente de `ofertas.precio_actual`; MongoDB no decide
cuánto cobrar.

## Snapshot histórico

`pedido_lineas` conserva:

```text
oferta_id
pedido_vendedor_id
producto_ref
sku_snapshot
producto_nombre
vendedor_nombre_snapshot
precio_unitario
cantidad
subtotal_linea
```

Nombre, vendedor, SKU y precio representan lo aceptado al comprar. La orden
permanece legible aunque cambien el documento, la oferta o el perfil comercial.
`pedido_direcciones` cumple la misma función para el destino de entrega.

## Integridad disponible

Dentro de MySQL existen FKs hacia `ofertas`, `pedido_vendedores`,
`producto_referencias`, `categorias`, `inventario`, usuarios y pedidos. Para
el único salto desde `producto_referencias.producto_ref` hacia MongoDB se
aplican controles de aplicación y verificación:

- Las migraciones abortan si un `producto_ref` no tiene documento.
- `backend/scripts/verify_setup.py` revisa `pedido_lineas`,
  `producto_referencias`, coincidencia de categoría y proyecciones de oferta.
- El corte 6B comprobó 65 referencias y 16 imágenes antes de retirar la tabla
  descriptiva SQL.
- Las pruebas concurrentes demuestran que dos compradores no pueden adquirir
  simultáneamente la última unidad.

No existe un script llamado `reconciliar_referencias.py`; el verificador real
es `backend/scripts/verify_setup.py` y devuelve código distinto de cero ante
huérfanos o divergencias.

## Referencia inversa

La tabla SQL `productos` y su supuesto `mongo_id` ya no existen. La referencia
inversa se resuelve consultando `producto_referencias.producto_ref`; las
ofertas se enlazan a esa identidad mediante FK. Esta separación evita
conservar en MySQL otra copia de nombre, descripción e imágenes. La categoría
sí se conserva como FK SQL para validar la taxonomía; MongoDB lleva slug y
nombre como snapshot de lectura.

## Consistencia eventual de proyecciones

Cuando cambia precio, stock, vendedor o estado, la transacción MySQL inserta un
mensaje en `outbox_eventos`. El worker actualiza la proyección MongoDB y añade
el evento de historial. Si MongoDB falla, el mensaje se reintenta; mientras
tanto catálogo y checkout continúan leyendo los valores comerciales desde
MySQL.
