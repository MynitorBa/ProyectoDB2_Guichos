# Evidencia de ejecución — Fase 6B aditiva

> Documento histórico de la etapa reversible previa al corte físico.

**Fecha:** 24 de agosto de 2026
**Resultado:** nuevas referencias instaladas y validadas antes del corte físico.

## Decisión confirmada

Las reseñas permanecen en MySQL y pertenecen al producto general, no a una
oferta. Para conservar integridad relacional se creó:

```text
producto_referencias
- id PK
- producto_ref CHAR(24) UNIQUE -> ObjectId lógico de MongoDB
- fecha_creacion
```

MongoDB sigue siendo propietario del nombre, descripción, categoría, atributos
e imágenes. La tabla mínima solo proporciona una identidad SQL estable.

## Backfill realizado

- 65 de 65 productos registrados en `producto_referencias`.
- 42 de 42 reseñas enlazadas mediante `producto_referencia_id` obligatorio.
- 29 de 29 movimientos enlazados mediante `inventario_id` obligatorio.
- 16 de 16 imágenes SQL comprobadas previamente en MongoDB.
- Cero referencias mínimas huérfanas contra MongoDB.

Un movimiento referencia `inventario.id`, no solo la oferta, porque una oferta
puede manejar existencias en diferentes bodegas.

## Seguridad y reversión

Antes de modificar la base, el ejecutor crea un respaldo JSON en `backups/`.
La migración es idempotente y aborta si encuentra productos sin documento
MongoDB, reseñas sin identidad o movimientos sin inventario. En esta etapa
aditiva las columnas y FKs anteriores seguían presentes, por lo que la
aplicación todavía podía regresar a la ruta de compatibilidad.

## Evidencia automatizada

- Migración ejecutada repetidamente con los mismos conteos.
- 27 pruebas automatizadas aprobadas.
- Checkout comprueba que cada salida registra `inventario_id`.
- Verificador MySQL/MongoDB completo aprobado.
- API, catálogo, frontend y compilación Vite aprobados.

## Continuación: corte físico

El corte físico fue autorizado y ejecutado posteriormente:

1. retirar `producto_id` de carrito, inventario, movimientos y líneas;
2. retirar `producto_id` legado de reseñas;
3. retirar `producto_imagenes`, ya representada en MongoDB;
4. retirar la tabla descriptiva `productos`;
5. conservar únicamente `producto_referencias`;
6. retirar el procedimiento SQL de checkout basado en producto.

La ejecución y sus resultados quedaron registrados en
[`15-fase6b-corte-fisico.md`](15-fase6b-corte-fisico.md).
