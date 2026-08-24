# ADR-001: Mover el catálogo de productos a MongoDB

**Estado:** Aceptado y actualizado tras la Fase 6B
**Fecha:** 2026-08-21  
**Autor:** Estudiante — Bases de Datos 2, UNIS

---

## Contexto

TiendaYa vende productos de 8 categorías completamente distintas: electrónica (computadoras, celulares, audio), ropa (camisas, pantalones, calzado), hogar, libros, deportes, alimentos, juguetes y herramientas. El problema concreto que enfrenté es que cada categoría tiene atributos propios que no tienen nada en común entre sí:

- Una **computadora** necesita: `procesador`, `ram_gb`, `almacenamiento_gb`, `pulgadas`, `sistema_operativo`
- Una **camisa** necesita: `talla`, `color`, `material`, `genero`, `tipo_cuello`
- Un **libro** necesita: `autor`, `isbn`, `paginas`, `editorial`, `idioma`
- Un **alimento** necesita: `peso_gr`, `calorias`, `ingredientes`, `fecha_vencimiento`, `refrigerado`
- Una **herramienta** necesita: `voltaje`, `potencia_w`, `marca`, `tipo_bateria`

Intenté modelar esto en MySQL y el resultado fue terrible: una tabla `productos` con más de 40 columnas donde el 70-80% de los valores son NULL dependiendo de la categoría. Una fila de libro tiene NULL en `ram_gb`, `talla`, `voltaje` y viceversa. Eso no es solo un problema estético — es un esquema que miente sobre la estructura de los datos.

---

## Alternativas evaluadas

### Alternativa 1: Modelo EAV en MySQL

Mantener un solo modelo relacional con una tabla `atributos_producto(producto_id, nombre_atributo, valor_texto)` en estilo EAV (Entity-Attribute-Value).

**Ventajas:** Todo queda en MySQL, sin infraestructura adicional.

**Problemas:** El modelo EAV destruye la capacidad de hacer consultas tipadas. Si quiero buscar laptops con más de 16 GB de RAM, tengo que hacer `WHERE nombre_atributo = 'ram_gb' AND CAST(valor_texto AS INT) > 16`. No puedo agregar índices útiles, no puedo validar tipos de datos, y los joins para reconstruir un producto completo son caros y frágiles. Con 65 productos de seed ya es complicado; con miles de productos sería inmanejable.

### Alternativa 2: Una tabla separada por categoría

Crear tablas como `productos_electronica`, `productos_ropa`, `productos_libros`, etc.

**Ventajas:** Cada tabla tiene exactamente las columnas que necesita, con tipos correctos e índices apropiados.

**Problemas:** Agregar una nueva categoría requiere un `ALTER TABLE` o crear una tabla nueva — es un cambio de esquema. Las consultas transversales (mostrar todos los productos de un vendedor sin importar categoría) requieren UNION de 8 tablas. El código de la API necesita conocer qué tabla consultar según la categoría, lo que genera lógica condicional difícil de mantener. Con el sistema de categorías jerárquico que manejo, esto se vuelve un árbol de decisión feo.

### Alternativa 3 (elegida): Catálogo en MongoDB, datos transaccionales en MySQL

Mover la colección de productos a MongoDB, donde cada documento puede tener un subdocumento `atributos` con la estructura exacta que necesita su categoría. Los datos que sí son homogéneos y transaccionales (órdenes, pagos, inventario, usuarios) permanecen en MySQL.

---

## Decisión

Adoptar un esquema **políglota**: MongoDB 7 para el contenido documental del
producto y MySQL 8 para identidad, ofertas, precios, inventario, pedidos y
demás datos transaccionales.

---

## Justificación

MongoDB es la opción correcta aquí por una razón concreta: el catálogo de productos tiene **variabilidad estructural genuina**, no variabilidad accidental. No es que yo no supe diseñar el esquema — es que una laptop y una camisa son objetos fundamentalmente distintos con atributos que no comparten semántica.

El modelo de documento de MongoDB permite que cada producto tenga exactamente los atributos que le corresponden:

```json
// Laptop
{ "nombre": "ThinkPad X1", "atributos": { "procesador": "Intel i7", "ram_gb": 16, "almacenamiento_gb": 512 } }

// Camisa
{ "nombre": "Camisa Oxford", "atributos": { "talla": "M", "color": "azul", "material": "algodón" } }
```

Ambos viven en la misma colección `productos`, se consultan con la misma API,
y el campo `atributos` simplemente tiene contenido distinto. No hay NULLs
espurios ni una tabla ancha con atributos que no aplican.

Adicionalmente, MongoDB permite conservar el historial documental en
`producto_eventos`. Precio e inventario se originan en MySQL; sus cambios se
publican mediante el outbox transaccional y se registran después en MongoDB.

---

## Consecuencias

**Positivas:**
- Cero columnas NULL por categoría incorrecta.
- Agregar una nueva categoría con nuevos atributos no requiere migraciones de esquema.
- La validación de atributos se puede hacer con JSON Schema a nivel de colección en MongoDB.
- El catálogo escala horizontalmente si fuera necesario.

**Negativas y mitigaciones:**
- No hay FK física entre un ObjectId y MySQL. `producto_referencias` ofrece una
  identidad mínima para reseñas y `verify_setup.py` comprueba las referencias
  cruzadas.
- El catálogo requiere combinar documentos MongoDB con ofertas MySQL. FastAPI
  resuelve las ofertas de una página en una sola consulta por lote, evitando
  una consulta SQL por producto.
- La sincronización entre motores no es atómica. El outbox guarda el cambio y
  el mensaje dentro de la misma transacción MySQL; un worker idempotente
  actualiza después la proyección MongoDB.
- El equipo necesita manejar dos motores de base de datos. Para este proyecto es asumible; en producción real requeriría mayor madurez operacional.
