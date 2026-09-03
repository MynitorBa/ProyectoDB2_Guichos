# Paneles, envíos parciales y solicitudes de variantes

Actualización local del 2 de septiembre de 2026, sobre `variantes-dinamicas-catalogo`.
Este documento no implica que los cambios ya estén publicados en GitHub.

## Dónde encontrar los cambios

- Administrador: productos, categorías, usuarios, vendedores, pedidos, ventas y solicitudes abren fichas con URL propia. La ficha de producto separa datos/imágenes, variantes y ofertas. La categoría muestra sus campos y productos asociados; se conserva la edición del esquema, no se agrega un cambio libre del slug de categorías existentes.
- Vendedores es un directorio independiente de Usuarios. Incluye perfil comercial, ofertas y subpedidos filtrados por estado.
- Pedidos muestra el trabajo de preparación y entrega; Ventas muestra la perspectiva comercial del mismo pedido, no otra compra ni otra tabla de ventas.
- Vendedor: pestaña **Mis ofertas**, con precio, estado, stock físico, reservado y disponible; permite editar exclusivamente sus ofertas activas o pausadas. Una oferta retirada no se puede republicar desde aquí.
- Vendedor: **Solicitudes** permite proponer producto, variante con oferta inicial u oferta para una variante existente. El selector de productos es una ventana con imágenes, búsqueda y páginas. Al elegir un producto para una variante, sus atributos documentales y valores se precargan como punto de partida; se pueden editar, eliminar o ampliar, mientras precio y stock permanecen vacíos.
- Vendedor: **Mis pedidos → Abrir pedido** muestra únicamente sus líneas, cantidades enviadas/entregadas y pendientes. El enlace y la fila completa se pueden pulsar y usar con teclado. El comprador ve todos sus subpedidos en el detalle de compra.

## Reglas de variantes y ofertas

La propuesta de variante lleva producto, atributos dinámicos, precio y stock inicial. Mientras está pendiente no crea una variante pública ni reserva existencias. Al aprobar, se crea la variante documental, su referencia relacional mínima y la oferta del vendedor con inventario, historiales y evento outbox. Los SKU se generan con las funciones existentes; no los escribe el vendedor.

Si otra solicitud ya creó esa combinación, la aprobación reutiliza la variante. Se mantiene la protección contra una segunda oferta activa del mismo vendedor para la misma variante. Las imágenes continúan perteneciendo al producto y almacenadas en MySQL; una solicitud de oferta no agrega imágenes por oferta.

Editar stock significa indicar el **nuevo saldo físico total**, no sumar esa cifra al saldo anterior. El disponible para comprar descuenta las reservas. No se permite un físico menor que lo reservado. Cada ajuste registra movimiento, historial de saldo y outbox; un cambio de precio registra el historial de precios. La versión de la oferta impide sobrescribir silenciosamente una compra o edición concurrente.

## Envíos y estados

Cada subpedido admite varios envíos. Una línea de cinco unidades puede despacharse como tres y luego dos. Cada envío se confirma entregado por separado. Las cantidades se capturan y validan como unidades enteras: el formulario bloquea decimales y la API vuelve a rechazarlos como protección. No se puede superar lo comprado ni agregar líneas de otro subpedido/vendedor.

El estado general se recalcula desde cantidades: confirmado, preparando, enviado_parcial, enviado, entregado_parcial y entregado. Solo se completa cuando todas las unidades de todos los vendedores activos están entregadas. El inventario se descuenta en checkout; enviar o confirmar entrega **no lo descuenta otra vez**.

El administrador puede confirmar pedidos pendientes. Puede cancelar pedidos confirmados/en preparación antes del primer envío: repone las existencias una sola vez. Después puede registrar un reembolso **simulado**, únicamente si existe pago aprobado. No se implementa pasarela bancaria, devolución posterior al envío ni devoluciones parciales en esta actualización. Cancelar y reembolsar no son pasos obligatorios del proceso de entrega.

## Cambios en MySQL

Migración `database/mysql/17_fulfillment_variant_requests.sql`:

| Objeto | Cambio / relaciones |
| --- | --- |
| `pedido_envios` | Nueva cabecera de envío; FK a `pedido_vendedores.id`; `creado_por` y `entregado_por` referencian `usuarios.id`. Estado, referencia de guía opcional y fechas. |
| `pedido_envio_lineas` | Cantidades por envío; PK compuesta `(envio_id, pedido_linea_id)`; FK a `pedido_envios.id` y `pedido_lineas.id`; CHECK cantidad positiva. La API valida que la línea pertenece al mismo subpedido. |
| `pedidos.estado` | Enum ampliado con preparación y estados parciales. |
| `pedido_vendedores.estado` | Mismos estados adicionales para avance por vendedor. |
| `solicitudes_catalogo.tipo` | Agrega `variante_nueva` y adapta CHECK de datos. Usa atributos y FK de variante ya existentes; no duplica la variante en otra tabla. |

No se cambia la propiedad de datos: MongoDB conserva producto/atributos/variantes; MySQL conserva identidad comercial, ofertas, precio, inventario, pedidos, pagos, imágenes y solicitudes. Outbox sigue comunicando cambios comerciales de forma asíncrona.

Los subpedidos antiguos enviados/entregados reciben un envío marcado `legado`, sin inventar fechas que no fueron registradas. El script no vuelve a crearlos al ejecutarse otra vez. Los saldos comerciales históricos no se vuelven a descontar.

También alinea el estado de los subpedidos cuando el pedido global ya estaba cancelado o reembolsado, conservando los envíos históricos. Esta reconciliación no repone stock ni modifica pagos antiguos: no se supone que las cancelaciones previas usaron el nuevo flujo.

## Cómo actualizar una instalación existente

Primero tener la rama actualizada y Docker/MySQL/MongoDB disponibles. Para una instalación que ya tiene variantes dinámicas y la migración 16 aplicada, cerrar temporalmente la API y ejecutar desde la raíz del repositorio:

```powershell
cd backend
.\venv\Scripts\python.exe scripts\apply_fulfillment.py
.\venv\Scripts\python.exe scripts\verify_setup.py
cd ..\frontend
npm.cmd run build
cd ..
```

Después reiniciar la API/frontend con el lanzador habitual y recargar el navegador. `scripts/setup.ps1` incluye esta migración para instalaciones completas; `scripts/start-dev.ps1` la aplica antes de iniciar la aplicación. No ejecutar todos los seeds para actualizar: podrían alterar datos de prueba propios.

Antes del DDL se guarda un respaldo JSON en `backups/fulfillment/`. Es un respaldo de las tablas afectadas, no un dump completo de ambas bases. Para una instalación importante conservar además su respaldo completo. MySQL no ofrece rollback transaccional de toda esta migración DDL; si falla, revisar el error y volver a ejecutar el script, no borrar tablas.

## Pruebas recomendadas para el equipo

1. Abrir un producto en Admin y verificar atributos e imágenes precargados; entrar a sus variantes y ofertas. Abrir una categoría y revisar sus productos asociados.
2. Entrar con vendedor, abrir Mis ofertas, cambiar un precio y sumar existencias escribiendo el nuevo total. Verificar catálogo, historial y movimiento de inventario. Abrir dos pestañas: una edición con versión antigua debe pedir recarga.
3. Proponer variante con atributos (por ejemplo RAM), precio y stock. Confirmar que no aparece públicamente antes de aprobar. Aprobar como admin y comprobar variante, oferta e inventario. Repetir aprobación no debe duplicar nada.
4. Solicitar oferta con el selector visual y elegir la variante exacta. Verificar que una oferta propia duplicada se rechaza.
5. Crear una compra de prueba con cinco unidades de un vendedor y dos de otro. Enviar tres, entregar ese envío, enviar las dos restantes. El global no debe quedar entregado hasta que el segundo vendedor complete su parte.
6. Intentar enviar más unidades de las pendientes y acceder a pedidos/ofertas de otro vendedor: debe rechazarse.
7. Cancelar un pedido de prueba sin envíos; verificar reposición única e historial. Un pedido ya enviado no debe permitir esa cancelación. Los reembolsos son simulados y requieren pago aprobado.
8. Consultar el pedido como comprador y comprobar ambos vendedores y sus cantidades. Revisar también una ficha desde Ventas.

## Verificación técnica

Las pruebas nuevas están en `backend/tests/test_fulfillment_vendor_workspace.py`. Usan una transacción exterior que revierte los datos SQL de prueba y eliminan exclusivamente la variante MongoDB creada para la prueba. No cambian los pedidos reales para simular envíos.

```powershell
cd backend
.\venv\Scripts\python.exe -m pytest -q
.\venv\Scripts\python.exe scripts\verify_setup.py
```

La prueba automatizada no sustituye revisar UX con el equipo. Las pantallas de listas y fichas, los permisos HTTP y la compilación del frontend se verifican adicionalmente. No se afirma que esto incluya devoluciones, logística externa ni pagos reales.

Evidencia local: 71 pruebas automatizadas aprobadas; compilación Vite correcta; GET autenticados de fichas administrativas, envíos, ofertas y solicitudes respondieron 200; acceso del vendedor a pedidos administrativos respondió 403. Se revisaron en navegador el listado y ficha de pedido, producto con atributos/ofertas, panel de vendedor y selector visual. `verify_setup.py` confirmó integridad SQL/MongoDB y outbox sincronizado. Repetir la migración creó cero envíos adicionales.
