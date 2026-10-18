# Decisión de Entrega 2: grafos frente a base columnar

## Contexto

La Entrega 2 plantea dos necesidades analíticas distintas:

1. **Tendencias de venta:** observar ventas por intervalos de tiempo e
   identificar productos cuya demanda aumenta entre periodos.
2. **Fraude en reseñas:** señalar cuentas, reseñas y productos con patrones de
   interacción anómalos (por ejemplo, cuentas que califican reiteradamente los
   mismos productos).

El enunciado exige evaluar ambas familias frente a estos dos problemas y
seleccionar al menos una. Como los dos problemas tienen patrones de acceso
opuestos, TiendaYa terminó implementando **ambas familias, cada una para el
problema que mejor resuelve**.

## Comparación aplicada al caso

| Criterio | Grafo (Neo4j) | Columnar (Cassandra) |
|---|---|---|
| Fortaleza principal | Recorrer relaciones de profundidad variable | Leer grandes volúmenes por una clave de partición conocida |
| Consulta de tendencias | Mala: obliga a agregar por fecha recorriendo nodos | Natural: una partición por semana y producto, sin JOIN |
| Consulta de fraude | Natural: `Usuario→Reseña→Producto←Reseña←Usuario` en una sola consulta | Mala: requiere JOIN recursivos que Cassandra no ofrece |
| Modelo | Nodos, aristas y propiedades | Tablas diseñadas por consulta, particiones y clustering |
| Escritura | Una reseña crea pocos nodos y aristas | Alto volumen de líneas de venta, escritura append |
| Costo operacional | Un motor adicional, justificado por el problema de fraude | Un motor adicional, justificado por el problema temporal |

## Decisión

| Problema | Familia elegida | Implementación |
|---|---|---|
| Tendencias de venta | **Columnar: Apache Cassandra 4.1** | Proyección semanal reconstruible desde MySQL. Ver [`27-analitica-cassandra.md`](27-analitica-cassandra.md). |
| Fraude en reseñas | **Grafos: Neo4j 5.26** | Grafo de usuarios, reseñas, productos, vendedores y compras. |

La primera iteración de la Entrega 2 implementó solo Cassandra. Después se
incorporó Neo4j para el panel de fraude, porque las consultas de varios saltos
sobre reseñas eran inviables de forma eficiente en Cassandra y costosas en
MySQL (auto-JOIN repetidos sobre reseñas y usuarios).

## Modelo de grafos

```
(:Usuario {id, nombre, email})
(:Producto {ref, nombre})          ref = ObjectId del catálogo MongoDB
(:Vendedor {id, nombre})
(:Reseña {id, calificacion, texto, fecha, estado, verificada, imagenes})
(:Compra {linea_id, pedido_id, oferta_id, fecha, cantidad, promocion_flash_id})

(Usuario)-[:ESCRIBIO]->(Reseña)
(Reseña)-[:SOBRE]->(Producto)
(Reseña)-[:CALIFICA_A]->(Vendedor)
(Reseña)-[:BASADA_EN]->(Compra)
(Usuario)-[:REALIZO]->(Compra)
(Compra)-[:DE_PRODUCTO]->(Producto)
(Compra)-[:A_VENDEDOR]->(Vendedor)
(Usuario)-[:GESTIONA]->(Vendedor)
(Vendedor)-[:OFRECE]->(Producto)
```

Restricciones de unicidad: `Usuario.id`, `Producto.ref`, `Vendedor.id`,
`Reseña.id` y `Compra.linea_id` (ver `backend/app/core/db_neo4j.py`).

### Consultas de detección (`backend/app/services/fraud_detection_service.py`)

| Patrón | Consulta | Saltos |
|---|---|---|
| Cluster coordinado | Pares de usuarios que reseñaron los mismos ≥3 productos: `(u1)-[:ESCRIBIO]->()-[:SOBRE]->(p)<-[:SOBRE]-()<-[:ESCRIBIO]-(u2)` | 4 |
| Reseñador de un solo vendedor | Usuarios con ≥3 reseñas, todas hacia el mismo vendedor | 2 |
| Bombardeo | Productos con ≥5 reseñas en 24 horas | 1 |
| Sin compra verificada | Reseñas sin `BASADA_EN` hacia una `Compra` pagada y atribuible | 1 |

La consulta de cluster coordinado es la consulta de varios saltos que exige el
enunciado. Además, las reglas de bombardeo y reseñador único se evalúan antes
de crear cada reseña: si se activan, la reseña queda `pendiente` de moderación.

### Datos de demostración

- `backend/scripts/seed_reviews.py` quedó retirado como generador para impedir
  que recree el modelo heredado; solo conserva un mensaje de compatibilidad.
- `backend/scripts/simulate_fraud.py` es una auditoría de solo lectura sobre
  los patrones presentes. No inyecta ni elimina usuarios, compras o reseñas.

## Límites de responsabilidad

- **MySQL** confirma pagos, inventario, pedidos, líneas, vendedores y ofertas.
- **MongoDB** describe productos, variantes, atributos e imágenes de catálogo.
- **Redis** conserva carrito y reservas efímeras de ventas flash.
- **Cassandra** mantiene una proyección reconstruible para analítica; nunca
  aprueba pagos ni descuenta inventario.
- **MySQL** también es la autoridad de reseñas, imágenes, respuestas y su
  verificación. Impone la unicidad por usuario, producto y vendedor.
- **Neo4j** es una proyección reconstruible para recomendaciones y fraude. Las
  compras se modelan con `Compra`, `REALIZO`, `DE_PRODUCTO` y `A_VENDEDOR`;
  nunca decide pagos, inventario ni elegibilidad de una reseña.

Ninguno de los dos motores analíticos participa en la decisión de una compra.
Cassandra y Neo4j reciben sus proyecciones mediante el outbox después del
commit en MySQL. Las 80 aristas `COMPRO` de la etapa anterior permanecen como
evidencia histórica inerte: ningún consumidor funcional las lee o escribe.
