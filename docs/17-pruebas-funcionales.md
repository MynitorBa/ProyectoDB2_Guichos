# Pruebas funcionales integrales

Fecha de ejecución: 24 de agosto de 2026
Entorno: aplicación local, MySQL y MongoDB de desarrollo.

## Resultado general

- Backend: **34 pruebas automatizadas aprobadas**.
- Frontend: **compilación de producción aprobada** (2,634 módulos).
- API: salud, autenticación, catálogo, pedidos, paneles, historial y exportación operativos.
- Integración MongoDB + MySQL: 65 productos comprobados y 0 discrepancias de lectura dual.
- Datos funcionales: el pedido de prueba `#96` se conserva intencionalmente y el inventario de la oferta `#8` quedó en 44 unidades.

## Matriz funcional

| Área | Resultado | Evidencia principal |
|---|---|---|
| Inicio y catálogo | Aprobado | 65 productos, paginación, categorías, destacados y búsqueda exacta. |
| Detalle de producto | Aprobado | Precio, inventario, vendedor, atributos e imágenes cargan correctamente. |
| Autenticación | Aprobado | Comprador, vendedor y administrador inician sesión con sus permisos. |
| Protección de rutas | Aprobado | Comprador redirigido fuera de `/admin`; API devuelve 403 al rol incorrecto. |
| Perfil y direcciones | Aprobado | Datos y dos direcciones visibles; validación de campos obligatorios activa. |
| Carrito | Aprobado | Agregar producto, contador y cálculos de subtotal, IVA y total correctos. |
| Checkout | Aprobado | Pedido `#96`, snapshots, pago, subpedido, movimiento y outbox creados. |
| Inventario | Aprobado | Oferta `#8`: 45 → 44; la suite de pruebas no modificó ese valor. |
| Factura PDF | Aprobado | HTTP 200, `application/pdf`, nombre correcto y 2,804 bytes. |
| Pedidos del comprador | Aprobado parcial | Lista y detalle global funcionan; falta mostrar los subpedidos por vendedor. |
| Panel vendedor | Aprobado | Solo muestra sus subpedidos y bloquea pedidos ajenos con HTTP 403. |
| Estados del vendedor | Corregido | La versión nueva expone `confirmado`, `preparando`, `enviado`, `entregado`. |
| Notificaciones | Aprobado | Aviso de nueva venta y marcado como leído comprobados. |
| Panel administrador | Aprobado | Estadísticas, productos, categorías, usuarios, ventas y pedidos cargan. |
| Exportación de ventas | Aprobado | Excel HTTP 200, MIME XLSX correcto, 9,326 bytes. |
| Historial de producto | Aprobado | 8 eventos y reconstrucción histórica en versión 8. |
| Registro | Aprobado parcial | Validaciones de formulario comprobadas; no se creó una cuenta residual. |
| Correo de factura | No ejecutado | SMTP no está configurado; se evitó enviar correo externo real. |

## Defectos encontrados y corregidos

### 1. Limpieza destructiva de pruebas de checkout

La fixture eliminaba todos los pedidos con ID mayor que 30. Esto podía borrar pedidos reales creados durante el uso local. Ahora registra y elimina exclusivamente los IDs creados por cada prueba, y restaura su inventario y proyección MongoDB.

Comprobación posterior:

- Antes: 31 pedidos, máximo ID 96, stock oferta 8 = 44.
- Después de las 34 pruebas: los mismos 31 pedidos, ID 96 presente y stock = 44.

### 2. Estado “En preparación” ausente

La API del vendedor consultaba el enum del pedido global y el frontend usaba `en_preparacion`, mientras el subpedido realmente utiliza `preparando`. Se corrigieron ambos lados y se añadió una prueba específica.

La instancia temporal con el código nuevo respondió:

```text
confirmado, preparando, enviado, entregado
```
### 3. Prueba de migración incompatible con el uso real

Una prueba exigía exactamente 29 movimientos de inventario. Una compra legítima elevó el total a 30 y causó un falso fallo. Ahora se valida el mínimo migrado y, principalmente, que todas las referencias mantengan integridad.

## Pendientes reales

1. Reiniciar el backend activo del puerto 8000 para que cargue la corrección del estado `preparando`. El código nuevo ya fue comprobado en un servidor temporal.
2. Incluir `pedido_vendedores` en el detalle que recibe el comprador y mostrar un bloque de envío/estado por vendedor. Actualmente solo se presenta el estado global.
3. Configurar una cuenta SMTP de la empresa antes de probar el envío real de facturas por correo.

## Comandos de regresión

Desde la raíz del repositorio:

```powershell
.\backend\venv\Scripts\python.exe -m pytest backend\tests -q
cd frontend
npm run build
```

## Actualización del historial por ofertas — 26 de agosto de 2026

- Migración aditiva `14_offer_temporal_history.sql` aplicada dos veces para
  comprobar idempotencia.
- 70/70 ofertas con estado temporal vigente.
- 70/70 inventarios con saldo temporal vigente.
- Endpoint diario comprobado con un producto que posee dos ofertas: devuelve
  dos series y ocho puntos dentro del rango disponible.
- Reconstrucción puntual comprobada sobre el mismo producto: devuelve sus dos
  ofertas con precio, vendedor, estado y stock.
- Caso de dos cambios de precio de una misma oferta durante un día: conserva
  el segundo cambio al cierre del día.
- Backend: **49 pruebas aprobadas**.
- Frontend: compilación de producción aprobada (2,636 módulos).

---

## Actualización Entrega 2 — 18 de septiembre de 2026

Entorno: todos los servicios Docker activos y saludables (MySQL 8, MongoDB 7,
Redis 7.2-alpine, Cassandra 4.1.12).

### Resultado general

- Backend: **86 pruebas automatizadas aprobadas** (86 passed in 14.24s).
- Setup integral: `scripts/verify_setup.py` finaliza con `[OK] Setup completo.`
- Cassandra analítica: **73 líneas pagadas proyectadas** desde MySQL.
- Corrección de datos: 2 filas huérfanas en `pedido_envio_lineas` eliminadas
  (envío 5 apuntaba a líneas de otro vendedor tras la migración de `pedido_vendedores`).

### Nuevos archivos de prueba — Entrega 2

| Archivo | Tests | Descripción |
|---|---|---|
| `test_flash_sales.py` | 5 | Atomicidad y expiración de ventas flash en Redis |
| `test_redis_cart.py` | 3 | CRUD, concurrencia y TTL del carrito Redis |
| `test_cassandra_analytics.py` | 3 | Analítica temporal, zona horaria Guatemala, idempotencia |
| `test_checkout.py` (ampliado) | 9 | Integración completa con Redis, precio y concurrencia |

### Pruebas de fraude — evidencia de ejecución

Todas las siguientes pruebas pasaron en la ejecución del 18 de septiembre de 2026.

| Prueba | Archivo | Qué demuestra |
|---|---|---|
| `test_cien_compradores_compiten_por_diez_unidades` | `test_flash_sales.py` | 100 hilos concurrentes → exactamente 10 ganadores, 90 rechazados; `disponibles == 0` |
| `test_reintento_del_mismo_usuario_es_idempotente` | `test_flash_sales.py` | El reintento del mismo usuario devuelve el token original sin gastar otro cupo |
| `test_reserva_vencida_devuelve_cupo` | `test_flash_sales.py` | Reserva expirada libera exactamente 1 unidad al pool (`disponibles == 1`) |
| `test_reserva_nunca_sobrevive_al_final_de_la_promocion` | `test_flash_sales.py` | `expira_ts == finaliza_en` cuando `segundos_reserva` excede el tiempo restante |
| `test_redis_se_reconstruye_desde_el_estado_durable` | `test_flash_sales.py` | Tras borrar Redis, el estado se rehidrata desde MySQL con disponibles y reservas correctas |
| `test_crud_renueva_ttl_y_aisla_usuarios` | `test_redis_cart.py` | Usuario B no ve el carrito de Usuario A; TTL ≤ `REDIS_CART_TTL` |
| `test_cien_incrementos_concurrentes_no_se_pierden` | `test_redis_cart.py` | 100 `agregar_item` concurrentes → `cantidad == 100` sin pérdidas |
| `test_carrito_expira_por_inactividad` | `test_redis_cart.py` | Carrito eliminado automáticamente tras TTL; `carrito_existe` devuelve `False` |
| `test_checkout_exige_confirmar_precio_cambiado` | `test_checkout.py` | `precios_esperados != precio_actual` → `CheckoutError(PRICE_CHANGED)` |
| `test_checkout_rechaza_confirmacion_de_precio_que_volvio_a_cambiar` | `test_checkout.py` | Confirmación vieja no acepta un segundo cambio de precio → `PRICE_CHANGED` |
| `test_checkout_acepta_precio_actual_confirmado` | `test_checkout.py` | Confirmación con precio vigente pasa; pedido creado al precio de MySQL |
| `test_checkout_flash_convierte_reserva_y_descuenta_pool` | `test_checkout.py` | Precio flash Q1.00 usado; reserva → `convertida`; `unidades_vendidas == 1`; pool decrementado |
| `test_concurrencia_ultima_unidad` | `test_checkout.py` | 2 hilos, 1 unidad → exactamente 1 éxito, 1 `INSUFFICIENT_STOCK`; stock final = 0 |

### Cobertura por componente de Entrega 2

| Componente | Estado | Evidencia |
|---|---|---|
| Carrito Redis (TTL, Lua, aislamiento) | Aprobado | 3 pruebas; `test_redis_cart.py` |
| Ventas flash Redis (Lua atómica) | Aprobado | 5 pruebas; `test_flash_sales.py` |
| Checkout con precio Redis vs MySQL | Aprobado | 3 pruebas de precio; `test_checkout.py` |
| Checkout con reserva flash | Aprobado | 1 prueba integral; `test_checkout.py` |
| Concurrencia última unidad (SELECT FOR UPDATE) | Aprobado | 1 prueba; `test_checkout.py` |
| Cassandra — zona horaria Guatemala | Aprobado | `test_week_is_monday_in_guatemala` |
| Cassandra — backfill idempotente | Aprobado | `test_backfill_is_idempotent_and_matches_mysql`; 73 líneas |
| Cassandra — outbox despacha analítica | Aprobado | `test_outbox_dispatches_analytics_without_mongo` |
| Flash sale worker | Verificado | `flash_sale_worker.py` activa, expira y finaliza promociones cada segundo |
| Setup integral | Aprobado | `verify_setup.py` → `[OK] Setup completo.` |

### Defecto encontrado y corregido — 18 de septiembre de 2026

**Filas huérfanas en `pedido_envio_lineas`**

`apply_fulfillment.py` se ejecutó en dos fases: la primera creó el envío 5 para
`pedido_vendedor` 5 (vendor 3) con las líneas 6, 7, 8 y 9. Una migración posterior
movió las líneas 6 y 9 al `pedido_vendedor` 91 (vendor 2). La segunda ejecución de
`apply_fulfillment.py` creó correctamente el envío 37 para `pedido_vendedor` 91, pero
las líneas 6 y 9 permanecieron también en el envío 5, causando que `verify_setup.py`
detectara "envíos enlazados a líneas de otro vendedor" y "cantidades enviadas mayores
que las compradas".

Corrección aplicada: `DELETE FROM pedido_envio_lineas WHERE envio_id=5 AND pedido_linea_id IN (6,9)`.
Tras la corrección, `verify_setup.py` finaliza con `[OK] Setup completo.`

### Comandos de regresión Entrega 2

```powershell
# Desde la raíz del repositorio
.\backend\venv\Scripts\python.exe -m pytest backend\tests -q
# Solo pruebas de Entrega 2
.\backend\venv\Scripts\python.exe -m pytest backend\tests\test_flash_sales.py backend\tests\test_redis_cart.py backend\tests\test_cassandra_analytics.py backend\tests\test_checkout.py -v
# Verificación integral de todos los servicios
cd backend
.\venv\Scripts\python.exe scripts\verify_setup.py
```
