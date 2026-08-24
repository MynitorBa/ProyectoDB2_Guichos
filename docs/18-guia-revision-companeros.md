# Guía de revisión para el equipo

## Rama que deben probar

```text
revision-modelo-relacional-ferxo
```

Esta rama propone la revisión del modelo relacional y la separación definitiva entre el catálogo documental de MongoDB y las operaciones comerciales de MySQL. Todavía no debe fusionarse con `master`: primero necesitamos que el equipo la instale, pruebe y confirme si está de acuerdo con las decisiones del modelo.

## Resumen de la arquitectura propuesta

- **MongoDB** responde qué es el producto: nombre, descripción, categoría, atributos variables, imágenes, visibilidad y proyección resumida para el catálogo.
- **MySQL** responde quién lo vende y bajo qué condiciones: oferta, vendedor, SKU, precio, moneda, inventario, pedidos, pagos y movimientos.
- `producto_referencias.producto_ref` conecta MySQL con el `_id` del documento en MongoDB. No es una foreign key SQL porque el documento se encuentra en otro motor; su integridad se controla mediante validaciones y migraciones.
- Una oferta representa una opción comprable de un vendedor. Varios vendedores pueden ofrecer el mismo producto con precios y existencias diferentes.
- El carrito y checkout utilizan `oferta_id`, no el identificador genérico del producto.

## Cambios realizados

### Modelo relacional

- La antigua tabla SQL `productos` fue retirada después de migrar sus responsabilidades.
- Se incorporó `producto_referencias` como registro local de las referencias hacia MongoDB.
- Se incorporaron `ofertas` y `oferta_precios_historial`.
- `inventario` ahora pertenece a una oferta y conserva cantidades disponibles y reservadas.
- Los movimientos de inventario referencian el inventario y mantienen foreign keys hacia pedido y usuario cuando corresponda.
- Se agregaron `pedido_vendedores` para separar dentro de un pedido las operaciones de cada vendedor.
- Las líneas del pedido conservan snapshots de oferta, SKU, vendedor, nombre y precio.
- Se agregó `pedido_direcciones` para conservar la dirección utilizada en el momento de la compra.
- Reseñas, carrito, notificaciones y pagos fueron adaptados al nuevo modelo.
- Se reforzaron foreign keys, índices e integridad referencial.

### Sincronización MySQL–MongoDB

- MySQL es la fuente autoritativa para precios e inventario.
- Se agregó `outbox_eventos` para guardar en la misma transacción los cambios que deben proyectarse hacia MongoDB.
- Un worker procesa los eventos de forma idempotente y actualiza la proyección del catálogo.
- El catálogo realiza lectura dual: obtiene el documento desde MongoDB y completa oferta, precio, vendedor e inventario desde MySQL.
- Las comprobaciones actuales reportan 65 productos y 0 discrepancias heredadas.

### Backend y reglas funcionales

- El catálogo, carrito, detalle de producto y checkout trabajan con ofertas.
- El checkout bloquea y descuenta inventario de MySQL dentro de la transacción.
- Cada compra genera pago, líneas, snapshots, movimiento de inventario, subpedidos por vendedor y evento outbox.
- El vendedor solamente consulta y modifica sus propios subpedidos.
- Los estados permitidos para el vendedor son: `confirmado`, `preparando`, `enviado` y `entregado`.
- Un vendedor recibe HTTP 403 al intentar modificar un pedido ajeno.
- El administrador conserva acceso a estadísticas, productos, categorías, usuarios, ventas y pedidos globales.
- La factura PDF continúa disponible desde los pedidos del comprador.

### Frontend

- Las tarjetas, catálogo y detalle utilizan la oferta seleccionada.
- El carrito conserva `oferta_id` como identidad comprable.
- El detalle permite visualizar las distintas ofertas disponibles para un producto.
- El panel del vendedor trabaja con su sección del pedido y muestra “En preparación”.
- Se actualizaron los flujos de checkout para el contrato nuevo de la API.

### Migraciones, instalación y documentación

- Se agregaron migraciones incrementales desde la corrección inicial de integridad hasta la Fase 7.
- Las migraciones incluyen validaciones previas y abortan si detectan referencias inválidas.
- Se agregaron scripts PowerShell para aplicar y completar las fases.
- `scripts/setup.ps1` instala desde cero y aplica el modelo vigente.
- `scripts/start-dev.ps1` inicia la aplicación.
- Se actualizaron el modelo relacional, diagrama ER, arquitectura, ADRs, referencias SQL–MongoDB e informe de entrega.

## Correcciones encontradas durante las pruebas

- Las pruebas de checkout antes eliminaban cualquier pedido con ID mayor que 30. Ahora solo limpian los pedidos creados por la propia prueba.
- Se corrigió la diferencia entre `en_preparacion` y el valor real `preparando` de los subpedidos.
- Una prueba exigía exactamente 29 movimientos de inventario y fallaba después de una compra válida. Ahora comprueba integridad y el mínimo migrado.

## Instalación para una copia nueva

Requisitos: Git, Docker Desktop activo, Node.js 20 o superior y PowerShell.

```powershell
git clone https://github.com/MynitorBa/ProyectoDB2_Guichos.git
cd ProyectoDB2_Guichos
git switch revision-modelo-relacional-ferxo
powershell -ExecutionPolicy Bypass -File ".\scripts\setup.ps1"
```

Para ejecuciones posteriores:

```powershell
powershell -ExecutionPolicy Bypass -File ".\scripts\start-dev.ps1"
```

Servicios esperados:

- Frontend: http://localhost:5173
- API: http://localhost:8000/docs
- Adminer: http://localhost:8080
- Mongo Express: http://localhost:8081

## Pruebas que debe realizar el equipo

### Instalación y datos

- [ ] La instalación desde cero termina sin errores.
- [ ] MySQL, MongoDB, backend y frontend quedan activos.
- [ ] El catálogo muestra productos, precios, vendedores y existencias.
- [ ] No aparecen errores de conexión en la consola del navegador.

### Comprador

- [ ] Iniciar sesión como comprador.
- [ ] Buscar y filtrar productos.
- [ ] Abrir un producto y comprobar sus ofertas.
- [ ] Agregar una oferta al carrito y cambiar la cantidad.
- [ ] Completar un checkout.
- [ ] Confirmar subtotal, IVA y total.
- [ ] Abrir el pedido generado y descargar su factura PDF.
- [ ] Confirmar que el inventario disminuyó exactamente en la cantidad comprada.

### Vendedor

- [ ] Iniciar sesión como vendedor.
- [ ] Confirmar que solamente aparecen sus ventas.
- [ ] Revisar la notificación de una compra nueva.
- [ ] Cambiar su subpedido entre confirmado, preparando, enviado y entregado.
- [ ] Confirmar que no puede modificar los pedidos de otro vendedor.

### Administrador

- [ ] Iniciar sesión como administrador.
- [ ] Revisar estadísticas y ventas recientes.
- [ ] Abrir productos, categorías y usuarios.
- [ ] Consultar el historial de un producto y reconstruirlo en una fecha anterior.
- [ ] Cambiar el estado global de un pedido.
- [ ] Exportar el reporte de ventas en Excel.

### Regresión automatizada

```powershell
cd backend
.\venv\Scripts\python.exe -m pytest tests -q
cd ..\frontend
npm run build
```

Resultado de referencia:

```text
31 passed
Frontend built successfully
```

## Decisiones que el equipo debe revisar

Por favor confirmen si están de acuerdo con lo siguiente:

1. MongoDB conserva la definición documental del producto y MySQL las ofertas comerciales.
2. Precio e inventario tienen a MySQL como fuente autoritativa.
3. `producto_ref` es una referencia entre motores validada por la aplicación, no una FK SQL.
4. El carrito compra una oferta concreta mediante `oferta_id`.
5. Un pedido puede dividirse en varios subpedidos, uno por vendedor.
6. El patrón outbox se utiliza para proyectar cambios de MySQL hacia MongoDB.
7. Reseñas permanecen en MySQL y MongoDB solamente conserva su resumen para el catálogo.

## Pendientes aplazados

- Mostrar al comprador el seguimiento separado de cada vendedor.
- Configurar una cuenta SMTP empresarial y validar el envío real de facturas.

## Formato sugerido para reportar resultados

```text
Nombre:
Instalación desde cero: OK / Error
Catálogo y ofertas: OK / Error
Carrito y checkout: OK / Error
Panel vendedor: OK / Error
Panel administrador: OK / Error
Pruebas automatizadas: resultado
¿De acuerdo con el modelo propuesto?: Sí / No / Cambios sugeridos
Detalle de errores o sugerencias:
```
