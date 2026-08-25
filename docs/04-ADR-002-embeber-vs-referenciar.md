# ADR-002: Embeber y referenciar en el catálogo

**Estado:** reemplazado parcialmente por la decisión del 25 de agosto de 2026
**Fecha original:** 21 de agosto de 2026
**Actualización:** 24 de agosto de 2026

## Contexto

La colección real de MongoDB se llama `productos`. Para decidir qué guardar
en cada documento se consideraron frecuencia de lectura conjunta, crecimiento
potencial y ciclo de actualización. El modelo final también distingue el
producto general de cada oferta comercial.

## Imágenes: BLOB relacional con URL de lectura proyectada

Por requisito académico, el binario vuelve a almacenarse en MySQL
`producto_imagenes`. Cada fila referencia `producto_referencias.id`; MongoDB
solo conserva las URL de lectura ordenadas para no duplicar el BLOB:

```json
{
  "nombre": "Laptop ThinkPad X1",
  "imagenes": [
    "/api/v1/products/images/41",
    "/api/v1/products/images/42"
  ]
}
```

La Fase 6B retiró la tabla heredada ligada a `productos`. La migración 12 crea
otra tabla con el mismo nombre pero con el contrato final, ligada a
`producto_referencias` y con `LONGBLOB`, MIME y orden.

## Reseñas: autoridad relacional y resumen documental

Las reseñas completas permanecen en MySQL `resenas`. Deben pertenecer a un
usuario y a un producto válido, y un usuario solo puede reseñar una vez cada
producto. Estas reglas se expresan con:

- FK `resenas.usuario_id → usuarios.id`.
- FK `resenas.producto_referencia_id → producto_referencias.id`.
- UNIQUE `(usuario_id, producto_referencia_id)`.

MongoDB conserva únicamente una proyección compacta:

```json
{
  "resumen_resenas": {
    "promedio": 4.3,
    "total": 127
  }
}
```

La proyección no es autoridad. Actualmente el campo existe y los datos
iniciales están sembrados; el CRUD público de reseñas y un mecanismo dedicado
para recalcular el resumen siguen siendo trabajo funcional posterior.

## Vendedor, precio e inventario: autoridad MySQL

Una misma identidad documental puede tener ofertas de diferentes vendedores.
Por ello vendedor, precio, moneda, estado comercial e inventario no pertenecen
al producto general:

- `ofertas` vincula `producto_ref` con un vendedor y un SKU.
- `ofertas.precio_actual` contiene el precio vigente.
- `inventario` conserva stock por oferta y bodega.

El documento puede contener `precio`, `stock`, `vendedor_id` y
`vendedor_nombre` como proyección de lectura. Sin embargo, FastAPI enriquece el
catálogo con ofertas MySQL en una consulta por lote y el checkout usa
exclusivamente `oferta_id`. Un retraso de la proyección MongoDB no altera el
precio cobrado.

## Resumen

| Dato | Autoridad | Estrategia |
|---|---|---|
| Nombre, descripción, categoría y atributos | MongoDB `productos` | Documento flexible |
| Binario de imágenes | MySQL `producto_imagenes` | BLOB relacionado por FK |
| URL y orden de imágenes | MongoDB `productos.imagenes` | Proyección para lectura |
| Reseñas completas | MySQL `resenas` | Relacionadas por FK |
| Resumen de reseñas | MongoDB `resumen_resenas` | Proyección compacta |
| Vendedor, precio y estado comercial | MySQL `ofertas` | Relacional/transaccional |
| Stock | MySQL `inventario` | Por oferta y bodega |
| Precio, stock y vendedor en MongoDB | MongoDB `productos` | Proyección eventual mediante outbox |
