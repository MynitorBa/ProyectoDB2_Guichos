# ADR-007 · Evaluación de NewSQL para el módulo de pagos

| Campo | |
|---|---|
| Estado | Aceptada (evaluación opcional de la Entrega 3, cerrada al final del proyecto) |
| Componente | Pedidos, pagos e inventario (MySQL 8) |
| Decisión | **No migrar** a un motor NewSQL; si hiciera falta alta disponibilidad, primero replicación de MySQL |

La sección «Entrega 3» del enunciado propone, de forma opcional, contrastar el módulo de pagos en su modelo
relacional actual con un motor NewSQL, «con independencia del sentido de la conclusión». Esta es una
evaluación analítica: no se desplegó un motor NewSQL; se contrastaron sus capacidades con lo que el módulo
necesita y con lo que se midió del sistema.

## Contexto

El módulo de pagos vive en MySQL 8 (un nodo) y es la autoridad del dinero y del inventario:

- **El checkout es una saga** ([30](30-estrategia-consistencia-checkout.md)): T1 reserva el inventario y crea
  el pedido pendiente con `SELECT … FOR UPDATE` ordenado por id; el cobro ocurre **fuera de toda transacción**,
  en una pasarela externa, con la misma clave de idempotencia en cada reintento; T2 confirma o compensa.
- **Transacciones cortas y localizadas**: cada una toca pocas filas (ofertas, inventario, pedido, pago, pasos
  de la saga y una fila de outbox por destino).
- **Volumen**: 189 pedidos y 189 pagos en la base principal; la DEMO de presentación, unos cientos más. Un nodo
  de MySQL atiende ese volumen con holgura.
- **Lo que sí fue difícil** (Entrega 3): coordinar la base con la pasarela externa y con las proyecciones en
  otros motores. Se resolvió con la saga, la idempotencia, el reconciliador y el outbox, y se demostró con los
  escenarios de falla E00–E17 ([31](31-evidencia-pruebas-falla.md)).

## Alternativas consideradas

| Alternativa | Qué aporta | Qué no |
|---|---|---|
| **No cambiar** (MySQL 8, un nodo) | ACID local, bloqueos de fila, el equipo ya lo opera | Un solo nodo: si cae, no hay cobros (el plan B deja la tienda en solo lectura y encola pedidos sin cobrar) |
| **MySQL con replicación** (InnoDB Cluster / Group Replication) | Conmutación automática ante la caída del primario, lecturas en réplicas | Las escrituras siguen en un primario |
| **TiDB** (NewSQL compatible con el protocolo de MySQL) | Transacciones ACID distribuidas, escritura horizontal, alta disponibilidad por consenso (Raft) | No soporta procedimientos almacenados: en ejecución el sistema no usa ninguno (no hay triggers ni procedimientos activos), pero 10 migraciones del esquema los crean como ayudantes temporales y habría que reescribirlas; diferencias de bloqueo pesimista/optimista; varios componentes que operar |
| **CockroachDB / YugabyteDB** (compatibles con PostgreSQL) | Aislamiento serializable por defecto, multirregión, alta disponibilidad por consenso | Cambiar de dialecto y de controlador (el sistema usa MySQL); bajo contención, las transacciones serializables se abortan y la aplicación debe reintentarlas |

## Decisión

No migrar el módulo de pagos a NewSQL. Mantener MySQL como autoridad transaccional. Si el requisito pasara a
ser alta disponibilidad, el primer paso sería la replicación de MySQL, no un cambio de motor.

## Justificación

| Criterio | Argumento |
|---|---|
| Consistencia | El riesgo real del checkout no está dentro de la base: está entre la base y la **pasarela externa**, que no participa en ninguna transacción. Un motor NewSQL ofrece ACID distribuido entre sus propios nodos, pero no puede incluir a la pasarela ni a MongoDB, Elasticsearch o Neo4j: la saga, la idempotencia y el outbox seguirían siendo necesarios. Migrar no elimina la parte difícil |
| Escalabilidad | NewSQL compensa cuando un solo primario ya no aguanta las escrituras o el volumen de datos, o cuando hace falta escribir en varias regiones. Con cientos de pagos, un nodo está lejos de ese límite. Además, el inventario de un producto en venta flash es una fila muy disputada: en un motor distribuido, cada escritura requiere acuerdo entre réplicas (más latencia por commit) y la contención se traduce en reintentos |
| Patrón de consulta | Transacciones cortas, sobre pocas filas, con bloqueo explícito ordenado. Es el caso para el que un motor relacional de un nodo está optimizado |
| Costo operativo | Un clúster NewSQL necesita al menos tres nodos para tolerar fallas. En la máquina del proyecto, la VM de Docker (5.8 GB) ya no admite dos pilas a la vez; agregar tres nodos más no es viable. La migración exigiría reescribir las migraciones que usan procedimientos temporales (TiDB) o cambiar de dialecto (CockroachDB) |

## Consecuencias

**Beneficios**
- Se conserva un motor que el equipo conoce y una autoridad transaccional simple de razonar.
- El esfuerzo se dedicó a lo que sí era el problema: la consistencia con sistemas externos (saga, outbox,
  reconciliación), con evidencia de falla.

**Limitaciones asumidas**
- MySQL es un punto único de falla para cobrar: si cae, la tienda queda en solo lectura y los pedidos se encolan
  sin cobrar hasta que vuelve ([44](44-plan-b-respaldos-entre-bases.md)).
- No hay escritura multirregión.

**Condiciones para reconsiderar NewSQL**
- Las escrituras del checkout saturan un primario de MySQL bien dimensionado (medido, no supuesto).
- Se exige operar en varias regiones con escritura activa en todas, o tolerar la caída de una zona completa sin
  perder pagos confirmados (RPO = 0) y sin intervención manual.
- El volumen de pedidos y pagos supera lo que un nodo puede almacenar y respaldar en las ventanas de operación.

En cualquiera de esos casos, antes de cambiar de motor se probaría la replicación de MySQL; NewSQL entra
cuando la escritura, no la disponibilidad, es el límite.
