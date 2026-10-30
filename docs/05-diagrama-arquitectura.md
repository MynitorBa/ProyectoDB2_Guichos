# Diagrama de Arquitectura — TiendaYa (arquitectura final)

Versión gráfica para el informe y la presentación: [`diagramas/arquitectura-final.svg`](diagramas/arquitectura-final.svg).
Abajo, la misma arquitectura en tres vistas (Mermaid, editable como texto).

![Arquitectura final de TiendaYa](diagramas/arquitectura-final.svg)

## 1. Componentes y conexiones

Cada flecha hacia una base de datos indica con qué usuario se conecta ese servicio (control de acceso,
[ADR-005](48-ADR-005-control-de-acceso.md)).

```mermaid
flowchart LR
    subgraph Clientes
        RCT["Tienda y panel admin\nReact + Vite :5173"]
        LAB["Laboratorio de consistencia\n:5174 (solo desarrollo)"]
        HER["Herramientas de consulta\nAdminer :8080 · Mongo Express :8081\nRedis Commander :8082 · Elasticvue :8083\nNeo4j Browser :7474"]
    end

    subgraph Servicios
        API["FastAPI :8000\nAPI + workers en segundo plano"]
        EMB["Servicio de embeddings :8002\nmpnet multilingüe, 768 dims"]
        PAS["Pasarela de pagos simulada :8001"]
    end

    subgraph Persistencia["Persistencia políglota"]
        MYS[("MySQL 8\nautoridad ACID")]
        MNG[("MongoDB 7\ncatálogo documental")]
        RED[("Redis 7\nestado efímero y cachés")]
        ESR[("Elasticsearch 8.15\ntexto + vectores")]
        CAS[("Cassandra 4.1\nanalítica semanal")]
        NEO[("Neo4j 5.26\ngrafo de compras y fraude")]
        SQL[("SQLite\nlibro de la pasarela")]
    end

    RCT -->|HTTP / JSON + JWT| API
    LAB -.->|/admin/fallas, /admin/consistencia| API
    API -->|"tiendaya (usuario propio)"| MYS
    API -->|"tiendaya_api · rol a medida"| MNG
    API -->|"tiendaya_api · ACL"| RED
    API -->|"tiendaya_api · rol tiendaya_busqueda"| ESR
    API --> CAS
    API --> NEO
    API -->|"texto → vector"| EMB
    API -->|"cobro / consulta / reembolso\n(Idempotency-Key)"| PAS
    PAS --> SQL
    HER -.->|"usuarios de solo lectura\n(Redis, Mongo, Elasticsearch)"| Persistencia
```

| Componente | Autoridad y propósito |
|---|---|
| MySQL | Usuarios, vendedores, ofertas, precios, inventario, pedidos, pagos, reseñas, fraude, bitácora de la saga y outbox. **Única fuente de verdad** transaccional. Guarda además las copias del plan B (carritos, catálogo, recomendaciones) |
| MongoDB | Productos, variantes, esquemas de atributos por categoría, historial de eventos del producto y configuración de tiendas. No decide precio ni stock |
| Redis | Carritos con expiración, reservas de ventas flash (Lua), autocompletado de respaldo, copias de lectura y cola de pedidos del plan B, y las cachés de la búsqueda semántica (vector de cada consulta, vecinos de cada producto, «Te podría interesar», historial de vistos) |
| Elasticsearch | Proyección de búsqueda: texto (BM25, errores, sinónimos, facetas) y **vector** de cada producto (`dense_vector` int8 HNSW). Decide qué productos y en qué orden; precio y stock se hidratan desde MySQL |
| Cassandra | Proyección analítica de ventas pagadas por producto, oferta, vendedor y semana |
| Neo4j | Proyección de compras pagadas, ofertas y reseñas: «quien compró esto también compró» y patrones de fraude |
| Servicio de embeddings | Convierte texto en vectores (sin estado; se reinicia sin perder nada) |
| Pasarela simulada + SQLite | Sistema externo: cobro, consulta y reembolso idempotentes por clave |

## 2. Flujo de datos: autoridad, proyecciones y respaldos

```mermaid
flowchart LR
    API["FastAPI"] -->|"escritura autoritativa\n+ fila de outbox por destino\n(misma transacción)"| MYS[("MySQL")]
    MYS -->|outbox_eventos| OBX["Outbox: un consumidor por destino\nreintentos 2^n hasta 300 s"]
    OBX -->|mongo| MNG[("MongoDB")]
    OBX -->|busqueda| ESR[("Elasticsearch")]
    OBX -->|cassandra| CAS[("Cassandra")]
    OBX -->|neo4j| NEO[("Neo4j")]
    OBX -->|redis| RED[("Redis")]
    OBX -->|catalogo| CAT[("MySQL: copia del catálogo")]
    API -->|carrito, flash| RED
    RED -.->|"copia de cada cambio\n(respaldo)"| MYS
    REC["Reconciliador y recolector\nde la saga"] --> MYS
    FLS["Worker de ventas flash"] --> RED
    FLS --> MYS
    IDX["Reconciliación del índice (10 min)\n+ purga de borrados"] --> ESR
```

- **Checkout como saga**: T1 reserva el inventario en MySQL, se cobra fuera de toda transacción y T2 confirma o
  compensa ([30](30-estrategia-consistencia-checkout.md)).
- **Outbox por destino**: una base caída no retrasa a las demás; los manejadores recalculan desde MySQL, así
  que son idempotentes e independientes del orden.
- **Plan B** ([44](44-plan-b-respaldos-entre-bases.md)): cuando un motor no responde, se usa otro que ya
  tiene una copia de sus datos.

| Motor caído | Respaldo |
|---|---|
| Redis | Carrito copiado en MySQL; reservas flash con `FOR UPDATE` en MySQL |
| MongoDB | Copia completa del catálogo en MySQL (destino `catalogo`); Elasticsearch como último recurso |
| Elasticsearch | MongoDB → copia del catálogo en MySQL; autocompletado con un índice de prefijos en Redis |
| Neo4j | Caché horaria de recomendaciones en MySQL → más vendidos de la categoría |
| MySQL | Solo lectura (sesión por JWT, copias de lectura en Redis) y pedidos en cola sin cobrar |
| Servicio de embeddings | Búsqueda solo de texto (las consultas ya hechas usan su vector guardado en Redis); los productos se indexan sin vector y la reconciliación los completa |

## 3. Vectores: de dónde salen y quién los usa

```mermaid
flowchart LR
    OBX["Outbox (busqueda)"] -->|texto del producto| HUE{"¿cambió el texto?\n(huella)"}
    HUE -->|no| REU["reutiliza el vector del índice"]
    HUE -->|sí| EMB["Servicio de embeddings"]
    EMB --> ESR[("Elasticsearch\nproductos_v2: vector int8 HNSW")]
    REU --> ESR
    Q["Texto buscado"] --> RV{"¿vector en Redis?"}
    RV -->|sí| HIB
    RV -->|no| EMB2["Servicio de embeddings"] --> HIB
    HIB["Búsqueda híbrida\ntexto + kNN"] --> ESR
    SIM["«También te podría interesar»\n(página de producto)"] -->|"kNN del vector del producto"| ESR
    PT["«Te podría interesar» (inicio)\ncarrito + vistos"] -->|"una cláusula kNN por semilla"| ESR
    DUP["Aviso de duplicados\n(solicitudes de catálogo)"] -->|"kNN + parecido del nombre"| ESR
```

Detalle técnico en [46](46-vectores-implementacion.md); decisión en [ADR-004](45-ADR-004-busqueda-vectorial.md).

## Decisiones de arquitectura por entrega

| Entrega | Decisión | Documento |
|---|---|---|
| 1 | Catálogo documental en MongoDB | [ADR-001](03-ADR-001-catalogo-documental.md), [ADR-002](04-ADR-002-embeber-vs-referenciar.md) |
| 2 | Redis para carritos y flash; Cassandra para tendencias y Neo4j para recomendaciones y fraude | [26](26-decision-grafos-columnar.md), [27](27-analitica-cassandra.md) |
| 3 | Elasticsearch como proyección de búsqueda; checkout como saga con outbox por destino | [ADR-003](28-ADR-003-motor-busqueda.md), [30](30-estrategia-consistencia-checkout.md) |
| Final | Vectores en Elasticsearch con un servicio de embeddings propio | [ADR-004](45-ADR-004-busqueda-vectorial.md) |
| Final | Usuarios por servicio con mínimo privilegio en Redis, MongoDB y Elasticsearch | [ADR-005](48-ADR-005-control-de-acceso.md) |
