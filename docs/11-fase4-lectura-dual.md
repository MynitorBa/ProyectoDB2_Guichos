# Evidencia de ejecución — Fase 4

> Documento histórico: la compatibilidad con `producto_id` descrita aquí fue
> retirada por la Fase 6B.

**Fecha:** 23 de agosto de 2026
**Alcance:** lectura dual MongoDB/MySQL e identidad comprable por oferta.

## Contrato implementado

- MongoDB continúa siendo propietario del documento descriptivo.
- MySQL aporta oferta, vendedor, precio e inventario.
- El catálogo elige primero una oferta activa con stock y luego el menor precio.
- El detalle devuelve todas las ofertas activas del producto.
- El carrito almacena `oferta_id`; `producto_id` permanece como compatibilidad.
- El checkout bloquea oferta e inventario con `SELECT FOR UPDATE`.
- Los pedidos nuevos crean subpedidos, snapshots de dirección, SKU y vendedor.
- El panel administrativo realiza escritura dual temporal de precio e inventario.

## Evidencia

- 65 productos devueltos por lectura dual.
- Fuente declarada por API: `mongodb+mysql`.
- 0 diferencias de precio, stock o vendedor durante la comparación inicial.
- Inicio de sesión, alta de oferta en carrito, lectura y eliminación: aprobados.
- 19 pruebas automatizadas aprobadas.
- Catálogo web renderizado con 8 productos de computadoras.

## Compatibilidad

Los clientes anteriores todavía pueden enviar `producto_id`; el backend lo
traduce a la oferta principal. Los clientes actualizados envían `oferta_id`.
Esta compatibilidad se retirará solo después de comprobar la Fase 5.

## Activación local

El proceso FastAPI debe reiniciarse para cargar el nuevo código. La migración
MySQL ya está aplicada e idempotente.
