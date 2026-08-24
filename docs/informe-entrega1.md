# Informe Entrega 1 — TiendaYa

**Bases de Datos 2 · UNIS · Segundo Semestre 2026**
**Estado verificado:** 24 de agosto de 2026

## 1. Arquitectura políglota

TiendaYa utiliza MySQL 8 y MongoDB 7 detrás de una API FastAPI. La separación
no se hace por tecnología sino por semántica:

- MongoDB `productos`: nombre, descripción, categoría, atributos variables e
  imágenes.
- MySQL: usuarios, vendedores, ofertas, precios, inventario, pedidos, pagos,
  carrito, reseñas, notificaciones y outbox.
- MongoDB `producto_eventos`: historial documental y eventos proyectados.

MongoDB responde qué es el producto. MySQL responde quién lo vende, a qué
precio, en qué moneda y con cuánto inventario. El catálogo combina ambas
fuentes; el checkout usa únicamente MySQL para las decisiones transaccionales.

## 2. Modelo relacional y normalización

El esquema final contiene 22 tablas. Las decisiones principales de 3FN son:

- `usuarios` y `roles` se relacionan N:M mediante `usuario_rol`.
- `vendedores` separa el perfil comercial de la cuenta de usuario.
- `ofertas` separa el producto general de la propuesta de cada vendedor.
- `oferta_precios_historial` separa el precio vigente de sus intervalos
  históricos.
- `inventario` pertenece a `(oferta, bodega)` y los movimientos referencian la
  fila exacta de inventario.
- `pedido_vendedores` separa la preparación y entrega de cada vendedor dentro
  de un pedido global.
- `producto_referencias` mantiene la identidad SQL del documento y una FK a
  su categoría; las ofertas referencian esa identidad sin duplicar el catálogo.

`pedido_lineas` y `pedido_direcciones` contienen snapshots. No representan una
violación de 3FN: el nombre, SKU, vendedor, precio y dirección almacenados son
hechos históricos del contrato, diferentes del estado vigente de esas
entidades.

El ER completo está en [`02-diagrama-ER.md`](02-diagrama-ER.md).

## 3. Heterogeneidad documental

Una computadora, una camisa, un libro y un alimento requieren atributos de
tipos y nombres diferentes. Una tabla única produciría decenas de columnas no
aplicables; EAV perdería tipos e índices útiles; una tabla por categoría
obligaría a cambiar el esquema y usar `UNION` para búsquedas transversales.

MongoDB permite que cada documento conserve exactamente sus atributos:

```javascript
// Computadora
db.productos.findOne(
  { "categoria.slug": "computadoras" },
  { nombre: 1, atributos: 1, imagenes: 1 }
)

// Libro
db.productos.findOne(
  { "categoria.slug": "libros" },
  { nombre: 1, atributos: 1, imagenes: 1 }
)
```

La colección real se llama `productos`; no existe una colección activa llamada
`catalogo`.

## 4. Embeber frente a referenciar

| Dato | Ubicación | Motivo |
|---|---|---|
| Imágenes | Embebidas en MongoDB | Se leen junto al producto y su volumen es acotado |
| Reseñas completas | MySQL `resenas` | Pertenencia a usuario/producto y unicidad mediante FK/UNIQUE |
| Resumen de reseñas | MongoDB | Proyección compacta para tarjetas del catálogo |
| Vendedor, precio y estado | MySQL `ofertas` | Autoridad comercial y consistencia transaccional |
| Stock | MySQL `inventario` | Bloqueo y prevención de sobreventa |

Los campos comerciales presentes en MongoDB son proyecciones eventuales. El
catálogo los reemplaza con los valores de ofertas MySQL antes de responder.

## 5. Índices y consultas MongoDB

Los índices relevantes se crean en `database/mongo/02_indexes.js` y también se
aseguran al arrancar FastAPI:

```javascript
db.productos.createIndex({ sku: 1 }, { unique: true, name: "uidx_sku" })
db.productos.createIndex(
  { "categoria.slug": 1, disponible: 1, precio: -1 },
  { name: "idx_catalogo_categoria_disponible_precio" }
)
db.productos.createIndex(
  { nombre: "text", descripcion: "text" },
  { name: "idx_texto_nombre_descripcion", default_language: "spanish" }
)
db.producto_eventos.createIndex(
  { producto_id: 1, timestamp: -1 },
  { name: "idx_eventos_producto_timestamp" }
)
db.producto_eventos.createIndex(
  { outbox_id: 1 },
  { unique: true, sparse: true, name: "uidx_evento_outbox" }
)
```

El panel administrativo utiliza `$facet`, `$group`, `$sort`, `$limit` y
`$project` para obtener estadísticas documentales en una sola agregación.

## 6. Referencia MySQL–MongoDB

El ObjectId se representa como `CHAR(24)` en `producto_referencias`, `ofertas`,
`pedido_lineas`, `carrito_items` y `outbox_eventos`. MySQL impone la relación
de ofertas y categorías mediante FKs; solo el salto entre
`producto_referencias.producto_ref` y MongoDB requiere controles de aplicación:

- FKs internas en MySQL.
- Validación durante migraciones.
- `backend/scripts/verify_setup.py` para detectar referencias huérfanas.
- Snapshots históricos que mantienen legibles las órdenes.

La identidad comprable es `oferta_id`; el frontend, carrito y checkout ya no
aceptan el antiguo `producto_id` SQL.

## 7. Checkout y prevención de sobreventa

El servicio de checkout ejecuta una sola transacción MySQL:

1. Valida usuario y dirección.
2. Bloquea ofertas e inventarios en orden estable con `FOR UPDATE`.
3. Verifica stock disponible.
4. Crea pedido, subpedidos, snapshot de dirección y líneas.
5. Descuenta inventario y registra movimientos.
6. Registra pago y mensajes en `outbox_eventos`.
7. Confirma mediante `COMMIT`.

La prueba `test_concurrencia_ultima_unidad` lanza dos compras simultáneas sobre
una sola unidad y comprueba que exactamente una tiene éxito.

## 8. Outbox e historial

Los cambios de precio e inventario se confirman primero en MySQL junto con un
mensaje outbox. El worker reclama mensajes, actualiza MongoDB, registra el
evento y marca el mensaje procesado. `outbox_id` único hace idempotente el
reintento.

`producto_eventos` se usa como historial y permite replay completo para el
volumen actual. La aplicación inserta eventos y no los modifica en su flujo
normal, pero no se ha configurado un rol MongoDB que prohíba `update` y
`delete`; por tanto, la inmutabilidad no se presenta como garantía del motor.

El precio histórico autoritativo también se conserva relacionalmente en
`oferta_precios_historial`, mientras que el precio contractual queda congelado
en `pedido_lineas.precio_unitario`.

## 9. Evidencia reproducible

Ejecutar desde `backend`:

```powershell
.\venv\Scripts\python.exe -m pytest tests -q
.\venv\Scripts\python.exe scripts\verify_setup.py
```

Resultado verificado el 24 de agosto de 2026:

- 27 pruebas aprobadas y 0 fallos.
- 65 referencias mínimas y 65 ofertas.
- 65 documentos en MongoDB `productos`.
- 31 subpedidos por vendedor.
- 477 eventos de producto.
- Cero referencias huérfanas.
- Proyecciones de oferta sincronizadas.
- Compilación Vite completada.
- Corte físico 6B confirmado.

Las advertencias de `datetime.utcnow()` y `pytest-asyncio` son deprecaciones
futuras, no fallos funcionales.

## 10. Reproducción del esquema

El setup crea el esquema base, migra los documentos, ejecuta los backfills y
aplica las fases hasta `10_phase6b_cutover.sql`. El DDL inicial conserva la ruta
de migración como evidencia; el estado final no contiene las tablas
transicionales `productos` ni `producto_imagenes`.

La evidencia detallada del corte está en
[`15-fase6b-corte-fisico.md`](15-fase6b-corte-fisico.md).
