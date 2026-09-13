# Analítica temporal con Cassandra

## Regla de negocio

Una venta entra en Cassandra solamente cuando su pago está confirmado. Las
semanas empiezan el lunes y terminan el domingo usando `America/Guatemala`.
Una cancelación con reembolso no elimina la historia: suma en
`ingresos_reembolsados` y deja cero en el ingreso neto correspondiente.

## Tablas diseñadas por consulta

### `ventas_producto_semana`

Partición: `(producto_ref, semana_inicio)`.

Responde al detalle cronológico de un producto durante una semana. Conserva
snapshots de producto, SKU, vendedor, precio y subtotal, además de oferta,
variante y promoción flash. `pedido_linea_id` evita perder filas cuando dos
ventas comparten el mismo instante.

### `resumen_productos_semana`

Partición: `semana_inicio` y fila por `producto_ref`.

Alimenta el panel administrativo y permite comparar la semana seleccionada con
la anterior sin hacer JOIN en tiempo de lectura. Incluye unidades, pedidos,
ofertas, vendedores, ventas flash e ingresos brutos, reembolsados y netos.

### `resumen_ofertas_vendedor_semana`

Partición: `(vendedor_id, semana_inicio)` y fila por `oferta_id`.

Alimenta el panel privado del vendedor. La API obtiene el `vendedor_id` desde
el usuario autenticado; no acepta otro vendedor indicado por el cliente.

## Flujo de consistencia

1. El checkout confirma pedido, líneas y pago en una transacción MySQL.
2. Esa misma transacción agrega `analytics.pedido_actualizado` al outbox.
3. El worker consume el evento y recalcula en Cassandra la semana afectada.
4. Cancelaciones y reembolsos emiten el mismo evento y actualizan los
   acumulados de forma idempotente.
5. Si Cassandra falla, el mensaje permanece pendiente y MySQL continúa siendo
   la fuente de verdad.

## Instalación y reconstrucción

La instalación normal ejecuta `scripts/setup.ps1`. Para revisar manualmente:

```powershell
cd backend
.\venv\Scripts\python.exe scripts\backfill_cassandra_analytics.py --dry-run
.\venv\Scripts\python.exe scripts\backfill_cassandra_analytics.py
.\venv\Scripts\python.exe scripts\verify_setup.py
```

El backfill real trunca únicamente las tres proyecciones derivadas y las
reconstruye desde MySQL; no modifica pedidos, pagos ni catálogo.

## API y permisos

- `GET /api/v1/analytics/health`: salud de Cassandra, solo administrador.
- `GET /api/v1/analytics/admin/trends?semana_inicio=AAAA-MM-DD`: estadísticas
  generales, solo administrador.
- `GET /api/v1/analytics/vendor/trends?semana_inicio=AAAA-MM-DD`: estadísticas
  del vendedor autenticado.

`semana_inicio` debe ser lunes. Ambos paneles comparan unidades con la semana
anterior y muestran una variación porcentual cuando existe una base comparable.
