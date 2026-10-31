# ADR-006 · Clave-valor, grafos y columnar (Entrega 2)

| Campo | |
|---|---|
| Estado | Aceptada (Entrega 2; registro formal escrito al cierre del proyecto) |
| Componentes | Redis 7 (carrito y venta flash), Cassandra 4.1 (tendencias), Neo4j 5.26 (fraude en reseñas) |
| Decisión | Redis para el estado efímero y la concurrencia; **ambas** familias analíticas, cada una para el problema que mejor resuelve |

Este registro reúne, con la estructura que pide el enunciado (sección 5.3), las decisiones de la Entrega 2 que
se documentaron en [24](24-carrito-redis.md), [25](25-ventas-flash.md), [26](26-decision-grafos-columnar.md) y
[27](27-analitica-cassandra.md). Las cifras y pruebas citadas están en esos documentos y en la suite de
integración.

## Contexto

La Entrega 2 planteaba cuatro necesidades con patrones de acceso distintos:

1. **Carrito**: escrituras y lecturas frecuentes de datos transitorios, que deben expirar por inactividad. En
   MySQL ocupaba tablas de negocio con datos que la mayoría de las veces nunca se convierten en pedido.
2. **Venta flash**: muchas solicitudes simultáneas compiten por pocas unidades; una actualización sin control
   vende más de lo que existe.
3. **Fraude en reseñas**: encontrar cuentas que se califican entre sí de forma reiterada sobre los mismos
   productos, es decir, recorridos de varios saltos entre usuarios, reseñas, productos y vendedores.
4. **Tendencias de venta**: ventas por intervalos de tiempo y productos cuya demanda sube entre periodos, es
   decir, lecturas por producto y semana sobre un volumen creciente de eventos.

## Alternativas consideradas

| Necesidad | Alternativas | Evaluación |
|---|---|---|
| Carrito | **Dejarlo en MySQL** (no cambiar) · Redis con TTL · solo en el navegador | MySQL no tiene expiración nativa (habría que limpiar con tareas programadas) y mezcla datos efímeros con los de negocio. El navegador no permite retomar el carrito en otro dispositivo ni validarlo en el servidor. Redis da expiración por inactividad nativa (`EXPIRE`) y operaciones atómicas |
| Venta flash | **MySQL con `SELECT … FOR UPDATE`** (no cambiar) · bloqueos en la aplicación · Redis con scripts Lua | Los bloqueos de fila serializan a todos los compradores sobre la misma fila; los bloqueos en la aplicación no funcionan con varias instancias y el enunciado los excluye. Un script Lua se ejecuta de forma atómica en Redis: verifica cupo, reserva y descuenta en una sola operación |
| Fraude | **Consultas en MySQL** (no cambiar) · Cassandra · Neo4j | En MySQL son auto-JOIN repetidos sobre reseñas y usuarios; Cassandra no tiene JOIN. Neo4j expresa `Usuario→Reseña→Producto←Reseña←Usuario` en una consulta |
| Tendencias | **Agregaciones en MySQL** (no cambiar) · Neo4j · Cassandra | En MySQL compite con las transacciones del checkout; en Neo4j obliga a agregar por fecha recorriendo nodos. Cassandra lee una partición por producto y semana, sin JOIN |

## Decisión

- **Redis** para el carrito (`carrito:{usuario}` con expiración de 30 minutos por inactividad, renovada con
  cada operación) y para el cupo y las reservas de la venta flash (scripts Lua de reserva, liberación,
  consumo y limpieza). MySQL sigue siendo la fuente durable: el checkout vuelve a validar precio, estado e
  inventario con bloqueo de filas, y el estado de la venta flash se puede reconstruir desde MySQL.
- **Neo4j** para el fraude en reseñas (reglas F01–F03 de varios saltos) y, después, para «quien compró esto
  también compró».
- **Cassandra** para las tendencias: tablas desnormalizadas por consulta, particionadas por producto, oferta o
  vendedor y semana.
- Las dos familias analíticas son **proyecciones reconstruibles** desde MySQL por el outbox: ninguna decide
  pagos ni inventario.

## Justificación

| Criterio | Argumento |
|---|---|
| Patrón de consulta | Cada motor recibe el patrón para el que está hecho: clave con expiración (carrito), operación atómica sobre un contador (flash), recorrido de relaciones (fraude), lectura por partición temporal (tendencias). La comparación aplicada al caso está en [26](26-decision-grafos-columnar.md) |
| Consistencia | Redis y las dos familias analíticas nunca son la autoridad. El checkout revalida en MySQL con `SELECT … FOR UPDATE`; las proyecciones llegan por el outbox después del commit y convergen (invariante I7) |
| Escalabilidad | La prueba de concurrencia enfrenta 100 compradores contra 10 unidades y exige exactamente 10 reservas, sin sobreventa y sin bloqueos en la aplicación (`test_flash_sales.py::test_cien_compradores_compiten_por_diez_unidades`). Las tendencias no tocan las tablas transaccionales |
| Costo operativo | Tres motores más. Se aceptó porque cada uno resuelve un problema distinto; la retrospectiva ([49](49-retrospectiva.md)) reconoce que, con el volumen del proyecto, Cassandra pudo esperar |

## Consecuencias

**Beneficios**
- El carrito expira solo y no ensucia las tablas de negocio; su expiración está documentada en el checkout
  ([24](24-carrito-redis.md)).
- La venta flash no vende de más bajo concurrencia, con evidencia automatizada.
- El panel de fraude encuentra patrones de varios saltos y el de tendencias compara semanas sin cargar a MySQL.

**Limitaciones asumidas**
- Tres componentes más que operar y mantener sincronizados (outbox por destino desde la Entrega 3).
- Redis es memoria: si se reinicia, el estado de la venta flash se reconstruye desde MySQL y el carrito tiene
  una copia en MySQL (plan B, [44](44-plan-b-respaldos-entre-bases.md)).
- **Condiciones para la alternativa no elegida en cada caso**, como pide el enunciado: tendencias en Neo4j solo
  si el análisis pasara a ser de relaciones (por ejemplo, propagación de compras entre clientes); fraude en
  Cassandra solo si se redujera a contar eventos por ventana de tiempo, sin recorridos.
