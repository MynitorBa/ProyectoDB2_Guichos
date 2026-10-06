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

(Usuario)-[:ESCRIBIO]->(Reseña)
(Reseña)-[:SOBRE]->(Producto)
(Reseña)-[:PARA_VENDEDOR]->(Vendedor)
(Usuario)-[:COMPRO {pedido_id, oferta_id, fecha}]->(Producto)
```

Restricciones de unicidad: `Usuario.id`, `Producto.ref`, `Vendedor.id` y
`Reseña.id` (ver `backend/app/core/db_neo4j.py`).

### Consultas de detección (`backend/app/services/fraud_detection_service.py`)

| Patrón | Consulta | Saltos |
|---|---|---|
| Cluster coordinado | Pares de usuarios que reseñaron los mismos ≥3 productos: `(u1)-[:ESCRIBIO]->()-[:SOBRE]->(p)<-[:SOBRE]-()<-[:ESCRIBIO]-(u2)` | 4 |
| Reseñador de un solo vendedor | Usuarios con ≥3 reseñas, todas hacia el mismo vendedor | 2 |
| Bombardeo | Productos con ≥5 reseñas en 24 horas | 1 |
| Sin compra verificada | Reseñas cuyo autor no tiene arista `COMPRO` hacia el producto | 2 |

La consulta de cluster coordinado es la consulta de varios saltos que exige el
enunciado. Además, las reglas de bombardeo y reseñador único se evalúan antes
de crear cada reseña: si se activan, la reseña queda `pendiente` de moderación.

### Datos de demostración

- `backend/scripts/seed_reviews.py` genera compras y reseñas realistas.
- `backend/scripts/simulate_fraud.py` inyecta los cuatro patrones pasando por el
  servicio real (`--limpiar` los retira).

## Límites de responsabilidad

- **MySQL** confirma pagos, inventario, pedidos, líneas, vendedores y ofertas.
- **MongoDB** describe productos, variantes, atributos e imágenes de catálogo.
- **Redis** conserva carrito y reservas efímeras de ventas flash.
- **Cassandra** mantiene una proyección reconstruible para analítica; nunca
  aprueba pagos ni descuenta inventario.
- **Neo4j** es la fuente de las reseñas y del grafo de interacción. La arista
  `COMPRO` es una proyección de los pedidos de MySQL que habilita las reseñas
  verificadas; nunca decide pagos ni inventario.

Ninguno de los dos motores analíticos participa en la decisión de una compra.
Cassandra recibe las ventas mediante el outbox después del commit en MySQL. A
inicios de la Entrega 3, la arista `COMPRO` se escribe después del commit con
un bloque de mejor esfuerzo que descarta errores silenciosamente; esa falla
parcial se aborda en la estrategia de consistencia de la Entrega 3.
