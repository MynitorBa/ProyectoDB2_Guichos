# ADR-002: Embeber y referenciar en el catálogo

**Estado:** aceptado y actualizado tras la Fase 6B
**Fecha original:** 21 de agosto de 2026
**Actualización:** 24 de agosto de 2026

## Contexto

La colección real de MongoDB se llama `productos`. Para decidir qué guardar
en cada documento se consideraron frecuencia de lectura conjunta, crecimiento
potencial y ciclo de actualización. El modelo final también distingue el
producto general de cada oferta comercial.

## Imágenes: embebidas

Las imágenes se leen junto con nombre y descripción, su cantidad por producto
es acotada y cambian como parte de la publicación. Por eso se almacenan como un
array dentro del documento:

```json
{
  "nombre": "Laptop ThinkPad X1",
  "imagenes": [
    { "url": "/static/products/x1-1.jpg", "orden": 0 },
    { "url": "/static/products/x1-2.jpg", "orden": 1 }
  ]
}
```

La Fase 6B verificó las 16 imágenes heredadas y retiró
`producto_imagenes` de MySQL.

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
| Imágenes | MongoDB `productos.imagenes` | Array embebido |
| Reseñas completas | MySQL `resenas` | Relacionadas por FK |
| Resumen de reseñas | MongoDB `resumen_resenas` | Proyección compacta |
| Vendedor, precio y estado comercial | MySQL `ofertas` | Relacional/transaccional |
| Stock | MySQL `inventario` | Por oferta y bodega |
| Precio, stock y vendedor en MongoDB | MongoDB `productos` | Proyección eventual mediante outbox |
