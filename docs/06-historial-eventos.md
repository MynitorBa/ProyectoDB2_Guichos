# Historial de Cambios de Productos — Event Sourcing

## Por qué usé event sourcing para el catálogo

Uno de los requisitos del proyecto es poder responder preguntas como "¿cuánto costaba este producto el 15 de julio?" o "¿cuándo se cambió la descripción?". En un modelo CRUD normal, cuando actualizo el precio de un producto simplemente hago `UPDATE productos SET precio = 850 WHERE _id = ...` y el precio anterior desaparece para siempre. El historial se pierde.

La solución que implementé es **event sourcing** sobre la colección `producto_eventos` en MongoDB. En lugar de mutar el documento del producto, cada cambio genera un nuevo documento de evento que describe qué cambió, cuándo y quién lo hizo. El documento del producto en `catalogo` sigue existiendo como vista de lectura, pero la fuente de verdad es el log de eventos.

## Tipos de eventos

La colección `producto_eventos` solo acepta estos seis tipos de documento:

| Tipo | Cuándo se genera |
|---|---|
| `PRODUCTO_CREADO` | Primera publicación del producto por el vendedor |
| `PRECIO_ACTUALIZADO` | El vendedor modifica el precio de venta |
| `DESCRIPCION_ACTUALIZADA` | Cambio en nombre, descripción textual o categoría |
| `DISPONIBILIDAD_CAMBIADA` | El producto pasa de activo a inactivo o viceversa |
| `ATRIBUTOS_ACTUALIZADOS` | Cambio en el subdocumento `atributos` (ej. nueva talla disponible) |
| `PRODUCTO_DESCONTINUADO` | El producto se retira permanentemente del catálogo |

## La garantía append-only

La colección `producto_eventos` no tiene operaciones de `UPDATE` ni `DELETE` en ninguna parte del código. Los documentos se insertan con `insertOne()` y nunca se tocan después. Para hacer esto explícito a nivel de base de datos, la colección está configurada con un rol de aplicación que solo tiene permiso de `insert` y `find` — no `update` ni `delete`.

Esto significa que el log de eventos es inmutable por construcción. Si un vendedor "corrige" un precio que ingresó mal, eso genera un nuevo evento `PRECIO_ACTUALIZADO`, no una modificación del evento anterior. El evento incorrecto queda en el log como registro de lo que pasó, y el evento corrector documenta la corrección.

## Estrategia de reconstrucción: replay completo (sin snapshots)

Elegí replay completo en lugar de snapshot + replay por una razón de escala concreta. Con 65 productos en el seed y un volumen esperado de decenas de eventos por producto en el período del proyecto universitario, el replay completo es perfectamente eficiente. Un producto con 50 eventos en su historial se reconstruye en microsegundos iterando el array.

Los snapshots añaden complejidad: hay que decidir cada cuántos eventos crear uno, hay que manejar la invalidación del snapshot cuando llegan nuevos eventos, y hay que almacenar el snapshot mismo. Para el volumen de este proyecto, ese overhead no se justifica.

La función `reconstruir_estado(producto_id, hasta_fecha)` en Python itera los eventos ordenados por `timestamp` y aplica cada uno secuencialmente hasta llegar a la fecha solicitada.

## Ejemplo concreto: ciclo de vida de una laptop

El producto `ThinkPad X1 Carbon` tiene el ObjectId `6821f3a2c4b7e9d001234567` y estos 7 eventos en orden cronológico:

```json
[
  {
    "tipo": "PRODUCTO_CREADO",
    "timestamp": "2026-05-10T09:00:00Z",
    "datos": {
      "nombre": "ThinkPad X1 Carbon",
      "precio": 9500.00,
      "atributos": { "procesador": "Intel i5-1235U", "ram_gb": 8, "almacenamiento_gb": 256, "pulgadas": 14 },
      "disponible": true
    }
  },
  {
    "tipo": "PRECIO_ACTUALIZADO",
    "timestamp": "2026-05-25T14:30:00Z",
    "datos": { "precio_anterior": 9500.00, "precio_nuevo": 8999.00 }
  },
  {
    "tipo": "ATRIBUTOS_ACTUALIZADOS",
    "timestamp": "2026-06-01T10:00:00Z",
    "datos": { "ram_gb": 16 }
  },
  {
    "tipo": "DESCRIPCION_ACTUALIZADA",
    "timestamp": "2026-06-15T16:45:00Z",
    "datos": { "nombre": "ThinkPad X1 Carbon Gen 12" }
  },
  {
    "tipo": "DISPONIBILIDAD_CAMBIADA",
    "timestamp": "2026-07-01T00:00:00Z",
    "datos": { "disponible": false, "motivo": "stock agotado" }
  },
  {
    "tipo": "DISPONIBILIDAD_CAMBIADA",
    "timestamp": "2026-07-20T08:00:00Z",
    "datos": { "disponible": true, "motivo": "reabastecimiento" }
  },
  {
    "tipo": "PRECIO_ACTUALIZADO",
    "timestamp": "2026-08-01T12:00:00Z",
    "datos": { "precio_anterior": 8999.00, "precio_nuevo": 9200.00 }
  }
]
```

### Lo que devuelve `reconstruir_estado` según la fecha consultada

**`hasta_fecha = "2026-05-20"`** — solo el evento de creación se aplica:
```json
{ "nombre": "ThinkPad X1 Carbon", "precio": 9500.00, "ram_gb": 8, "disponible": true }
```

**`hasta_fecha = "2026-06-10"`** — se aplicaron creación + precio + atributos:
```json
{ "nombre": "ThinkPad X1 Carbon", "precio": 8999.00, "ram_gb": 16, "disponible": true }
```

**`hasta_fecha = "2026-07-15"`** — se aplicaron todos los anteriores + descripción + primera disponibilidad:
```json
{ "nombre": "ThinkPad X1 Carbon Gen 12", "precio": 8999.00, "ram_gb": 16, "disponible": false }
```

**Estado actual (todos los eventos):**
```json
{ "nombre": "ThinkPad X1 Carbon Gen 12", "precio": 9200.00, "ram_gb": 16, "disponible": true }
```

Esta capacidad de "viaje en el tiempo" es lo que hace valiosa la arquitectura de eventos. Sin ella, no habría forma de responder con certeza cuánto costaba un producto en una fecha específica.
