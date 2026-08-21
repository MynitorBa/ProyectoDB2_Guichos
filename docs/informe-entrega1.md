# Informe Entrega 1 — TiendaYa
**Bases de Datos 2 · UNIS · Segundo Semestre 2026**

---

## 1. Modelo Relacional y Normalización

El modelo relacional de TiendaYa está compuesto por 17 tablas en MySQL 8 y fue diseñado siguiendo la Tercera Forma Normal (3NF). El proceso de normalización implicó identificar y eliminar dependencias transitivas que habría generado anomalías de actualización en operaciones cotidianas del sistema.

Las decisiones de normalización más importantes fueron tres. Primero, separar la información de vendedores de la tabla de productos: en un diseño inicial, columnas como `vendedor_nombre` y `vendedor_email` vivían en `productos`, creando una dependencia transitiva `producto_id → vendedor_id → vendedor_email`. La tabla `vendedores` resuelve esto con su propia PK. Segundo, modelar la relación usuario-rol con una tabla puente `usuario_rol` porque la relación es genuinamente N:M — un usuario puede tener múltiples roles (cliente y vendedor simultáneamente) y un rol puede asignarse a miles de usuarios. Una columna de roles en `usuarios` no puede representar esta realidad sin violar 1NF. Tercero, separar `categorias` como entidad propia con auto-referencia en `padre_id` para soportar la jerarquía de dos niveles del catálogo sin redundancia.

El caso de `precio_unitario` en `pedido_lineas` merece explicación separada porque parece una violación de 3NF pero no lo es. Este campo representa el precio al momento de la compra, no el precio actual del producto — son semánticamente distintos. `precio_unitario` depende de la PK compuesta `(pedido_id, producto_ref)` de la tabla, sin pasar por otra columna no-clave. La 3NF se mantiene intacta. La "redundancia" es deliberada: protege la integridad histórica de las órdenes ante cambios futuros de precio.

<!-- CAPTURA: Diagrama ER generado desde MySQL Workbench o DBeaver mostrando las 17 tablas con sus relaciones -->

<!-- CAPTURA: Resultado de SHOW CREATE TABLE pedido_lineas en MySQL para evidenciar la definición del campo precio_unitario y producto_ref -->

---

## 2. Diagnóstico del Problema de Heterogeneidad

El detonante para adoptar un esquema polígota fue el problema concreto de atributos heterogéneos entre las 8 categorías del catálogo. Cuando intenté modelar todos los productos en una sola tabla MySQL, el resultado fue un esquema con más de 40 columnas donde la mayoría de los valores eran NULL dependiendo de la categoría:

- Una **computadora** usa: `procesador`, `ram_gb`, `almacenamiento_gb`, `pulgadas` — pero no `talla`, `isbn` ni `voltaje`.
- Una **camisa** usa: `talla`, `color`, `material`, `genero` — pero no `ram_gb`, `paginas` ni `potencia_w`.
- Un **libro** usa: `autor`, `isbn`, `paginas`, `editorial` — pero no `procesador`, `talla` ni `ingredientes`.
- Un **alimento** usa: `peso_gr`, `calorias`, `ingredientes`, `fecha_vencimiento` — completamente distinto a todas las anteriores.

Evalué dos alternativas antes de decidir. El modelo EAV (Entity-Attribute-Value) con una tabla `atributos_producto(producto_id, nombre, valor_texto)` resuelve el NULL masivo pero destruye la capacidad de consultar por tipo: buscar laptops con RAM > 16 GB requiere castings y condiciones sobre strings que no se pueden indexar eficientemente. El modelo de tabla por categoría (`productos_electronica`, `productos_ropa`, etc.) preserva los tipos pero hace que agregar una categoría sea un cambio de esquema y que las consultas transversales sean UNIONs de 8 tablas.

<!-- CAPTURA: Consulta en MySQL mostrando una fila de producto con columnas NULL (evidencia del problema antes de la migración, puede ser un ejemplo simulado) -->

---

## 3. Decisión de Modelado Documental

La solución adoptada fue mover el catálogo de productos a MongoDB 7, donde cada documento en la colección `catalogo` puede tener un subdocumento `atributos` con la estructura exacta de su categoría. Los datos donde la consistencia transaccional es crítica — pedidos, pagos, inventario, usuarios — permanecen en MySQL.

La arquitectura resultante es polígota: FastAPI actúa como orquestador y decide qué base de datos consultar según la naturaleza de la operación. Una consulta de catálogo (leer atributos, ver imágenes, ver historial de precio) va a MongoDB. Una transacción de compra (descontar inventario, crear pedido, procesar pago) va a MySQL con transacción ACID.

La colección `catalogo` en MongoDB tiene a la fecha 65 documentos correspondientes a los productos del seed. Cada documento tiene un campo `atributos` de esquema variable y un array `imagenes` embebido. La colección `producto_eventos` tiene el historial append-only de cambios.

<!-- CAPTURA: Resultado de db.catalogo.findOne() en MongoDB Compass o mongosh mostrando un documento de laptop con sus atributos -->

<!-- CAPTURA: Resultado de db.catalogo.findOne() mostrando un documento de libro con atributos distintos (isbn, autor, paginas) para contrastar -->

<!-- CAPTURA: Vista de la colección producto_eventos en MongoDB mostrando varios documentos de eventos para un mismo producto_id -->

---

## 4. Embeber vs. Referenciar

Las decisiones de modelado dentro de MongoDB siguieron tres criterios: frecuencia de acceso conjunta, volumen potencial de datos, y tasa de cambio independiente.

**Imágenes: embebidas.** Cada producto tiene entre 1 y 5 imágenes. El array de imágenes pesa menos de 1 KB, siempre se necesita junto con el documento del producto, y su ciclo de vida está ligado al del producto. No hay razón para separarlo.

**Reseñas: colección separada `resenas` con resumen embebido.** Las reseñas pueden crecer de forma ilimitada en un producto popular. Un producto con 500 reseñas con texto extenso superaría el límite de 16 MB del documento BSON. Además, las reseñas se escriben de forma independiente al producto — no tiene sentido bloquear el documento del producto cada vez que alguien deja una opinión. El compromiso es guardar un campo `resumen_resenas { promedio, total }` en el documento del producto para evitar un join en cada carga del catálogo.

**Vendedor: referenciado con nombre desnormalizado.** El perfil completo del vendedor vive en MySQL (`vendedores`). Pero el nombre de la tienda aparece en cada card del catálogo, así que desnormalizarlo en el documento del producto evita un join en la operación más frecuente. Los cambios de nombre de tienda son infrecuentes y manejables mediante un proceso de actualización explícito.

<!-- CAPTURA: Documento de producto en MongoDB mostrando el array imagenes embebido y el campo resumen_resenas -->

---

## 5. Historial de Cambios — Event Sourcing

El historial de cambios de productos se implementó con event sourcing sobre la colección `producto_eventos`. Cada modificación a un producto genera un nuevo documento de evento; los documentos existentes nunca se modifican ni eliminan.

Los seis tipos de evento implementados son: `PRODUCTO_CREADO`, `PRECIO_ACTUALIZADO`, `DESCRIPCION_ACTUALIZADA`, `DISPONIBILIDAD_CAMBIADA`, `ATRIBUTOS_ACTUALIZADOS` y `PRODUCTO_DESCONTINUADO`. La colección tiene configurado un rol de solo `insert` y `find` a nivel de permisos de MongoDB para hacer cumplir la garantía append-only por construcción.

La reconstrucción del estado en una fecha dada se hace con replay completo: la función `reconstruir_estado(producto_id, hasta_fecha)` lee todos los eventos del producto en orden cronológico y los aplica secuencialmente hasta la fecha solicitada. Se eligió replay completo sobre snapshots porque el volumen de eventos por producto en este sistema no justifica la complejidad adicional de gestionar snapshots.

Esta arquitectura permite responder con exactitud preguntas como "¿cuánto costaba este producto el 15 de julio?" o "¿cuándo se cambió la descripción?", que son imposibles de responder en un modelo CRUD tradicional donde el UPDATE sobreescribe el valor anterior.

<!-- CAPTURA: Resultado de db.producto_eventos.find({ producto_id: ObjectId("...") }).sort({ timestamp: 1 }) mostrando la secuencia completa de eventos de un producto -->

<!-- CAPTURA: Output de la función reconstruir_estado llamada con dos fechas distintas para el mismo producto, mostrando estados diferentes -->

---

## 6. Evidencias de Funcionamiento

Esta sección consolida las capturas de pantalla que demuestran el sistema funcionando de extremo a extremo.

<!-- CAPTURA: Pantalla del frontend React mostrando el listado del catálogo con productos de distintas categorías -->

<!-- CAPTURA: Ficha de detalle de un producto (laptop) mostrando atributos específicos como procesador, RAM, almacenamiento -->

<!-- CAPTURA: Ficha de detalle de otro producto (libro o ropa) mostrando atributos completamente distintos — evidencia de heterogeneidad resuelta -->

<!-- CAPTURA: Proceso de checkout — carrito y confirmación de orden -->

<!-- CAPTURA: Docker Compose levantado con los tres servicios activos: backend (FastAPI), mysql, mongo — output de docker-compose ps -->

<!-- CAPTURA: Colección catalogo en MongoDB Compass mostrando la lista de 65 documentos del seed -->

<!-- CAPTURA: Tablas en MySQL Workbench o similar mostrando registros en pedidos y pedido_lineas, con la columna producto_ref visible -->

<!-- CAPTURA: Endpoint de la API FastAPI (Swagger UI en /docs) mostrando los endpoints disponibles -->

---

*Informe preparado para la Entrega 1 — Bases de Datos 2, UNIS, Segundo Semestre 2026.*
