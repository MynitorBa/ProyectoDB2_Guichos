# ADR-002: Decisiones de embeber vs. referenciar en MongoDB

**Estado:** Aceptado  
**Fecha:** 2026-08-21  
**Autor:** Estudiante — Bases de Datos 2, UNIS

---

## Contexto

Al diseñar el esquema de la colección `catalogo` en MongoDB tuve que tomar tres decisiones concretas de modelado: cómo manejar las imágenes de productos, las reseñas, y el nombre del vendedor. Cada una tiene criterios distintos y la respuesta correcta no es la misma para los tres casos.

Los tres criterios que usé para decidir son:
1. **Frecuencia de acceso:** ¿Se lee siempre junto con el producto, o de forma independiente?
2. **Volumen de datos:** ¿La subdocumentación puede crecer sin límite y superar los 16 MB del documento?
3. **Tasa de cambio independiente:** ¿El dato cambia con su propio ciclo, o solo cuando cambia el producto?

---

## Decisión 1: Imágenes embebidas en el documento de producto

### Análisis

- **Frecuencia de acceso:** Cada vez que muestro un producto — en listado, en ficha de detalle, en el carrito — necesito las imágenes. No existe un caso de uso donde lea un producto sin querer sus imágenes. Hacer una query separada para obtenerlas sería desperdicio puro.
- **Volumen:** Un producto tiene entre 1 y 5 imágenes típicamente. Cada imagen es solo una URL (string corto) y metadatos (`es_principal`, `orden`). El array completo pesa menos de 1 KB. No hay riesgo de acercarse al límite de 16 MB del documento BSON.
- **Tasa de cambio:** Las imágenes cambian cuando el vendedor actualiza su publicación — el mismo evento que modifica el producto. No tienen un ciclo de vida independiente.

### Decisión: Embeber

```json
{
  "nombre": "Laptop ThinkPad X1",
  "imagenes": [
    { "url": "https://cdn.tiendaya.gt/img/thinkpad-x1-1.jpg", "es_principal": true, "orden": 1 },
    { "url": "https://cdn.tiendaya.gt/img/thinkpad-x1-2.jpg", "es_principal": false, "orden": 2 }
  ]
}
```

Los tres criterios favorecen embeber: acceso siempre conjunto, volumen acotado, cambio sincronizado.

---

## Decisión 2: Reseñas referenciadas (con resumen embebido)

### Análisis

- **Frecuencia de acceso:** La ficha de producto muestra el promedio y la cantidad de reseñas siempre. El detalle completo de reseñas (texto, autor, fecha) solo se carga cuando el usuario hace scroll o hace clic en "ver todas". Son dos accesos con frecuencias distintas.
- **Volumen:** Un producto popular puede acumular cientos o miles de reseñas. Cada reseña tiene texto largo, respuestas del vendedor, votos de utilidad. Si embutiera todo eso en el documento principal, un producto con 500 reseñas podría superar los 16 MB con facilidad. Es el caso clásico de **crecimiento no acotado**.
- **Tasa de cambio:** Las reseñas se escriben de forma independiente al producto — un cliente puede dejar una reseña sin que el vendedor haga nada. Son escrituras concurrentes que no deberían bloquear al documento del producto.

### Decisión: Referenciar — colección `resenas` separada, con resumen embebido

Las reseñas individuales viven en su propia colección con FK lógica al `producto_id`. Pero para no tener que hacer un join en cada carga de catálogo, embebo un pequeño resumen en el documento del producto:

```json
{
  "nombre": "Laptop ThinkPad X1",
  "resumen_resenas": {
    "promedio": 4.3,
    "total": 127,
    "actualizado_en": "2026-08-20T18:00:00Z"
  }
}
```

Este resumen se recalcula con un job asíncrono cada cierto tiempo. No es tiempo real, pero el catálogo no necesita precisión al segundo. Las reseñas completas se cargan desde `resenas` solo cuando el usuario las pide.

---

## Decisión 3: Vendedor referenciado por ID, con nombre denormalizado

### Análisis

- **Frecuencia de acceso:** El catálogo siempre muestra el nombre del vendedor junto al producto ("Vendido por ElectroShop GT"). Es un dato que aparece en el listado, no solo en la ficha de detalle.
- **Tasa de cambio:** El nombre de la tienda del vendedor cambia rara vez — es un evento excepcional, no cotidiano. Un vendedor no renombra su tienda cada semana.
- **Perfil completo del vendedor:** El resto de los datos del vendedor (NIT, teléfono, descripción, verificado, historial) no se necesitan en el catálogo — están en MySQL y se consultan solo en la página de perfil del vendedor.

### Decisión: Referenciar con desnormalización parcial del nombre

El documento de producto guarda `vendedor_id` (FK lógica a MySQL) y `vendedor_nombre` como dato desnormalizado:

```json
{
  "nombre": "Laptop ThinkPad X1",
  "vendedor_id": 42,
  "vendedor_nombre": "ElectroShop GT"
}
```

Esto evita un join en cada consulta de catálogo sin arriesgar inconsistencia grave: si el vendedor cambia de nombre, hay que actualizar sus documentos en MongoDB, pero es una operación de mantenimiento infrecuente, no una anomalía cotidiana. El proceso de actualización está documentado y forma parte del job de reconciliación.

---

## Resumen de decisiones

| Dato | Estrategia | Razón principal |
|---|---|---|
| Imágenes | Embebido en producto | Siempre se leen juntas, volumen acotado |
| Reseñas completas | Colección separada `resenas` | Crecimiento no acotado, escritura independiente |
| Resumen de reseñas | Embebido (campo `resumen_resenas`) | Se necesita en cada carga de catálogo |
| Vendedor (nombre) | Desnormalizado en producto | Lectura frecuente, cambio infrecuente |
| Vendedor (perfil) | Referenciado por ID a MySQL | No se necesita en el catálogo |
