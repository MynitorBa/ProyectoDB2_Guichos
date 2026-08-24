# Evidencia de ejecución — Fase 5

> Documento histórico de implantación; el outbox continúa activo en el modelo final.

**Fecha:** 23 de agosto de 2026
**Resultado:** escritura transaccional y proyección asíncrona verificadas.

## Responsabilidad de cada motor

- MySQL es la autoridad de ofertas, precios monetarios e inventario.
- MongoDB es la autoridad del documento descriptivo del producto.
- La copia de precio, disponibilidad y vendedor en MongoDB es una proyección
  para lectura del catálogo; no es la fuente usada para cobrar ni reservar.

## Flujo implementado

1. El servicio modifica la oferta o el inventario en MySQL.
2. En la misma transacción inserta un mensaje en `outbox_eventos`.
3. Si falla cualquiera de las dos escrituras, ambas se revierten.
4. El worker reclama mensajes pendientes y actualiza la proyección MongoDB.
5. El historial MongoDB usa `outbox_id` único para impedir duplicados.
6. El mensaje se marca `procesado`; si falla, queda `error` y se reintenta
   hasta cinco veces. Los mensajes abandonados en `procesando` se recuperan.

El checkout aplica esta secuencia al descontar existencias y dejó de escribir
stock directamente en MongoDB. Los cambios administrativos de precio, stock,
vendedor y estado utilizan el mismo mecanismo.

## Contratos importantes

- Cambiar un precio cierra la vigencia anterior, crea la nueva vigencia,
  incrementa la versión de la oferta e inserta el outbox en una transacción.
- Comprar reserva y descuenta inventario en MySQL antes de confirmar el pedido.
- Reprocesar un mensaje puede repetir la proyección, pero no duplica el evento
  histórico debido al índice único `uidx_evento_outbox`.
- La creación del documento continúa en MongoDB y la oferta/inventario se crea
  en una transacción MySQL. La eliminación física del modelo anterior queda
  fuera de esta fase.

## Evidencia automatizada

La suite completa contiene 22 pruebas aprobadas, incluidas:

- checkout exitoso, sin stock y carrito vacío;
- competencia por la última unidad;
- lectura dual y selección de oferta principal;
- publicación idempotente del outbox;
- recuperación de un mensaje fallido;
- atomicidad del cambio de precio, historial y outbox.

El verificador de instalación confirmó:

- 65 productos MongoDB y 65 productos de compatibilidad MySQL;
- 65 ofertas y 65 inventarios relacionados;
- cero referencias MySQL–MongoDB huérfanas;
- cero diferencias en la proyección de precio, stock y vendedor;
- índice único de idempotencia instalado;
- ningún mensaje agotado o atascado en el outbox.

## Reproducción

Desde `backend`:

```powershell
.\venv\Scripts\pytest.exe tests\ -v
.\venv\Scripts\python.exe scripts\verify_setup.py
```

La Fase 6 no debe eliminar todavía columnas antiguas sin un periodo de
observación, un respaldo y una migración destructiva separada y explícita.
