# Evidencia de ejecución — Fase 3

> Documento histórico: describe el estado aditivo anterior al corte físico 6B.

**Fecha:** 23 de agosto de 2026
**Alcance:** backfill aditivo del modelo producto/oferta.

## Controles previos

- 65 productos MySQL con `producto_ref` válido.
- 65 documentos correspondientes en MongoDB.
- 65 inventarios sin oferta.
- 30 pedidos, 44 líneas y 31 grupos pedido–vendedor.
- Cero referencias huérfanas entre MySQL y MongoDB.

## Resultado

| Estructura | Antes | Después |
|---|---:|---:|
| Ofertas | 0 | 65 |
| Precios vigentes | 0 | 65 |
| Inventarios relacionados | 0 | 65 |
| Subpedidos por vendedor | 0 | 31 |
| Snapshots de dirección | 0 | 30 |
| Líneas con oferta, subpedido y snapshots | 0 | 44 |

La migración se ejecutó por segunda vez y los conteos no cambiaron. El SQL
usa una transacción con precondiciones y poscondiciones; cualquier cobertura
incompleta provoca `ROLLBACK`.

Antes de cada ejecución, `apply_phase3_backfill.py` genera un respaldo JSON en
`backups/`. Esa carpeta se ignora en Git porque contiene datos operativos.

## Pruebas

- 15 pruebas de backend aprobadas.
- Checkout normal, falta de stock y concurrencia de última unidad aprobados.
- Integridad de oferta, precio, inventario, subpedidos y snapshots aprobada.
- API saludable y catálogo web con 8 productos de computadoras visible.

## Limitación histórica

Los snapshots de dirección de pedidos anteriores representan la información
disponible el día del backfill. No es posible demostrar si una dirección fue
editada antes de esta migración.
