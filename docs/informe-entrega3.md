# Informe Entrega 3 — TiendaYa

**Bases de Datos 2 · UNIS · Segundo Semestre 2026**
**Estado verificado:** 6 de octubre de 2026 · rama `entrega3-mynor`

La Entrega 3 resuelve dos problemas: **encontrar productos** aunque el usuario escriba con
errores, y **no perder ni duplicar dinero o inventario** cuando el checkout toca varias
bases y un servicio de pagos externo que pueden fallar por separado.

| Requisito del enunciado | Puntos | Dónde está |
|---|---|---|
| Motor de búsqueda con tolerancia ortográfica y facetas | 5 | §1 · [ADR-003](28-ADR-003-motor-busqueda.md) · [detalle técnico](29-busqueda-elasticsearch.md) |
| Documento de estrategia de consistencia del checkout distribuido | 5 | §2 · [estrategia](30-estrategia-consistencia-checkout.md) |
| Evidencia de una prueba de falla simulada | 4 | §3 · [evidencia](31-evidencia-pruebas-falla.md) · [escenarios](evidencia/fallas/README.md) |
| Calidad del informe y del repositorio | 1 | §4–§6 |
| Diagrama de arquitectura actualizado | — | [05-diagrama-arquitectura.md](05-diagrama-arquitectura.md) |

## 1. Búsqueda de productos (Elasticsearch)

**Problema medido antes de decidir.** La búsqueda anterior (`$regex` en MongoDB) acertaba
6 de 17 consultas representativas; el índice `$text` de MongoDB, 10 de 17. Ninguno tolera
errores ni ofrece sinónimos o facetas ([línea base](evidencia/busqueda-linea-base.md)).

**Decisión.** Elasticsearch 8.15 como **proyección de solo lectura** del catálogo
([ADR-003](28-ADR-003-motor-busqueda.md)):

- Mapping estricto con analizador español sin tildes y *stemmer* ligero, sinónimos solo al
  consultar, edge n-gramas para prefijos, *shingles* para «¿Quisiste decir…?», atributos
  `nested` para facetas que cambian por categoría y un campo `completion` para el autocompletado.
- Consulta combinada: exacta con sinónimos, difusa (`AUTO:5,8`), prefijo, frase y SKU, con
  desempate por ventas, calificación y stock.
- **Facetas disyuntivas** (categoría, vendedor, rango de precio, disponibilidad y atributos
  como RAM o talla) calculadas por el motor con `post_filter`.
- Elasticsearch decide **qué** productos y **en qué orden**; el precio y el stock mostrados
  se leen siempre de MySQL.
- Sincronización por el outbox (destino `busqueda`) con documentos armados desde el estado
  actual y versión externa; reindexado sin caída por cambio de alias; reconciliación cada 10 min.
- **Degradación:** si Elasticsearch no responde, la búsqueda continúa sobre MongoDB y lo indica.

**Resultado.** 17 de 17 consultas aciertan en el top 3, con ~9 ms por consulta
([comparación](evidencia/busqueda-comparacion.md)):

| Consulta | Antes (`$regex`) | Ahora |
|---|---|---|
| `macbok` (error ortográfico) | Sin resultados | MacBook Air M2 |
| `audifonos sony` (sin tilde) | Sin resultados | Audífonos Sony WH-1000XM5 |
| `telefono` (sinónimo) | Sin resultados | Motorola Edge 40, Xiaomi Redmi Note 12, Samsung Galaxy A54 |
| `inspiron dell` (orden de palabras) | Sin resultados | Laptop Dell Inspiron 15 |
| `sams` (prefijo) | Samsung Galaxy A54 | Samsung Galaxy A54 (con `$text`: sin resultados) |

En la interfaz: autocompletado en el encabezado, catálogo con panel de facetas y filtros en
la URL, resaltado de coincidencias, «¿Quisiste decir…?» y búsqueda dentro de cada tienda.

## 2. Estrategia de consistencia del checkout

Documento completo: [`30-estrategia-consistencia-checkout.md`](30-estrategia-consistencia-checkout.md).

- **El checkout es una saga**, no una transacción distribuida: T1 reserva el inventario en
  MySQL y crea el pedido `pendiente`; el cobro ocurre en una pasarela externa
  (`payment_simulator/`, proceso aparte) **fuera de toda transacción**; T2 confirma o compensa.
  Se descartó 2PC/XA porque la pasarela y los motores NoSQL no son participantes XA y porque
  2PC bloquea recursos mientras espera a un servicio externo.
- **Consistencia fuerte donde importa:** dinero e inventario se deciden solo en MySQL, con
  bloqueos de fila en un orden único (sin interbloqueos) y transiciones protegidas por estado,
  así que confirmar o compensar dos veces no tiene efecto.
- **Idempotencia de punta a punta:** el navegador genera una clave por intento; la API la guarda
  con índice único (reintento → mismo pedido) y la pasarela no cobra dos veces la misma clave.
- **Cuatro compensaciones** (rechazo, pasarela no alcanzada, reserva vencida, reembolso de un
  cobro aprobado que ya no se puede cumplir).
- **Resultado desconocido ≠ fallo:** ante un timeout el pedido queda «en verificación» (HTTP 202),
  la reserva se conserva y un **reconciliador** consulta la pasarela por la clave. Un
  **recolector** libera las sagas interrumpidas por una caída del proceso.
- **Outbox por destino:** la confirmación inserta, en la misma transacción, una fila por
  proyección (MongoDB, Elasticsearch, Cassandra, Neo4j, Redis). Cada destino tiene su propio
  consumidor con reintento exponencial; las proyecciones se recalculan desde el estado actual,
  por lo que repetir o desordenar eventos no las corrompe.
- **Siete invariantes verificables** (sin sobreventa, toda reserva explicada, ningún pedido
  vendido sin pago, cancelados liberan su reserva, sin sagas atascadas, pasarela ↔ pedidos,
  proyecciones convergen) en `scripts/verificar_consistencia.py` y `GET /admin/consistencia`.
- **Matriz de 19 fallas** con su desenlace, respuesta al usuario y la prueba que lo demuestra.

## 3. Evidencia de las pruebas de falla

Documento: [`31-evidencia-pruebas-falla.md`](31-evidencia-pruebas-falla.md).

Se ejecutaron **14 escenarios** (13 fallas y una línea base) contra el sistema real, sin
mocks: pasarela con fallas programadas, caídas del proceso en tres puntos de la saga, doble
envío y bases detenidas de verdad con `docker stop`. Cada escenario registra el estado antes,
durante y después, la respuesta al cliente, la bitácora de la saga, los cobros de la pasarela
y los invariantes. Resumen y resultados en [`evidencia/fallas/README.md`](evidencia/fallas/README.md).

La primera corrida encontró dos defectos reales que se corrigieron antes de entregar:

1. **Bloqueo de cabeza de línea en el outbox:** con un solo consumidor, una base caída
   retenía los eventos de todas las demás. Se pasó a un consumidor por destino.
2. **Dependencias ocultas de MongoDB y Neo4j:** sin tiempos de espera acotados, un componente
   detenido colgaba al consumidor. Se configuraron los tiempos de espera de los drivers y la
   proyección analítica dejó de depender de MongoDB para las imágenes.

Para provocar fallas y observar la recuperación en vivo existe el **laboratorio de
consistencia** (`laboratorio/`, puerto 5174), una aplicación aparte de la tienda que solo
habla con la API y cuyos endpoints únicamente existen con `FAULT_INJECTION_ENABLED=true`.

## 4. Arquitectura

Diagrama actualizado en [`05-diagrama-arquitectura.md`](05-diagrama-arquitectura.md): se
agregan Elasticsearch, la pasarela de pagos simulada, el outbox con un consumidor por
destino, el reconciliador y recolector de la saga, y el laboratorio de consistencia.

## 5. Calidad y verificación

| Verificación | Resultado |
|---|---|
| Pruebas automatizadas (`pytest tests -q`), integración contra los motores reales, sin mocks | 162 aprobadas |
| `scripts/verify_setup.py` (integridad de los seis motores y del índice de búsqueda) | Setup completo |
| `scripts/verificar_consistencia.py` (invariantes I1–I7) | Todos se cumplen (I3 anota 3 pedidos del seed de la Entrega 1, anteriores a la saga) |
| Escenarios de falla (`scripts/demo_fallas.py`) | 14/14 |
| Compilación del frontend y del laboratorio | Correcta |

Instalación desde cero con `scripts/setup.ps1` (levanta Elasticsearch, crea el índice y lo
llena) y arranque con `scripts/start-dev.ps1` (API, pasarela, tienda y, si la bandera está
activa, el laboratorio).
