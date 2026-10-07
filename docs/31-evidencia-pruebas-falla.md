# Evidencia de las pruebas de falla del checkout distribuido

Este documento reúne la evidencia exigida por la Entrega 3: *"al menos una
prueba de falla simulada sobre el flujo de checkout y el comportamiento
resultante del sistema"*. Se ejecutaron **14 escenarios** (13 fallas y una
línea base) contra el sistema en ejecución, sin mocks: la API real, la pasarela
de pagos simulada como proceso aparte y los contenedores Docker reales, que se
detienen y arrancan de verdad.

La estrategia que estas pruebas validan está en
[`30-estrategia-consistencia-checkout.md`](30-estrategia-consistencia-checkout.md).

## Cómo se obtuvo la evidencia

| Capa | Herramienta | Qué demuestra |
|---|---|---|
| Escenarios end-to-end | `backend/scripts/demo_fallas.py` → [`evidencia/fallas/`](evidencia/fallas/README.md) | Cada falla provocada sobre el sistema real, con el estado antes/después, la respuesta al cliente, la bitácora de la saga, los cobros de la pasarela y los invariantes |
| Pruebas automatizadas | `tests/test_checkout_saga.py`, `tests/test_checkout_recovery.py`, `tests/test_outbox_v2.py` | Los mismos desenlaces, repetibles en cada cambio (forman parte de la batería completa de `pytest`) |
| Invariantes | `scripts/verificar_consistencia.py` y el laboratorio de consistencia (`laboratorio/`, :5174) | Que después de cada falla el sistema quedó en un estado correcto, no solo que "no se cayó" |
| Observación en vivo | *Admin › Salud de sincronización* en la tienda y el laboratorio de consistencia | Eventos retenidos por destino, bitácora de la saga y modos de la pasarela durante la demostración |

Para reproducir (en desarrollo, con `start-dev.ps1` corriendo y en
`backend/.env`: `FAULT_INJECTION_ENABLED=true`, `CHECKOUT_RESERVA_MINUTOS=1`,
`RECONCILIADOR_GRACIA_S=20`):

```powershell
cd backend
.\venv\Scripts\python.exe scripts\demo_fallas.py            # los 14 escenarios (~10 min)
.\venv\Scripts\python.exe scripts\demo_fallas.py E01 E03    # algunos
```

Los valores de reserva (1 min) y gracia (20 s) se acortaron solo para que la
demostración no tarde; en operación normal son 10 min y 120 s.

## Resultados

Corrida completa del 6 de octubre de 2026 (19:46–19:52): **14 de 14 escenarios
superados**, con los invariantes I1–I7 cumpliéndose después de cada uno. Cada fila enlaza
su evidencia: estado antes/durante/después, respuesta al cliente, bitácora de la saga y
cobros de la pasarela.

| # | Falla provocada | Qué vio el cliente | Cómo terminó | Medido |
|---|---|---|---|---|
| [E00](evidencia/fallas/E00.md) | Ninguna (línea base) | 201 | Pedido confirmado; las 5 proyecciones al día | Checkout 0.59 s |
| [E01](evidencia/fallas/E01.md) | La pasarela rechaza el pago | 402 `PAYMENT_DECLINED` | Reserva liberada, carrito intacto, sin cargo | — |
| [E02](evidencia/fallas/E02.md) | La pasarela cobra y responde 500 | 201 | El reintento con la misma clave recibe el cargo existente: **un solo cargo** | 2 intentos |
| [E03](evidencia/fallas/E03.md) | La pasarela cobra y no responde a tiempo | 202 `PAYMENT_PENDING` | El reconciliador consulta por la clave y confirma sin volver a cobrar | Resuelto 1.0 s después de responder |
| [E04](evidencia/fallas/E04.md) | La pasarela responde 503 y no cobra | 202 `PAYMENT_PENDING` | Tras la gracia, el reconciliador comprueba que no hay cargo y compensa | 23.2 s (gracia 20 s) |
| [E05](evidencia/fallas/E05.md) | El proceso muere tras reservar, antes de cobrar | 500 | El recolector libera la reserva al vencer; sin cargo | 64.0 s (reserva 1 min) |
| [E06](evidencia/fallas/E06.md) | El proceso muere tras cobrar, antes de confirmar | 500 | El recolector encuentra el cargo y confirma **sin volver a cobrar** | 63.4 s |
| [E07](evidencia/fallas/E07.md) | Falla dentro de la transacción de confirmación | 500 | Rollback completo; el recolector confirma con el cargo existente; stock descontado una vez | 63.4 s |
| [E08](evidencia/fallas/E08.md) | Doble envío simultáneo con la misma clave | 201 y 409 `CHECKOUT_IN_PROGRESS`; reintento posterior → 200 (mismo pedido) | Un solo pedido y un solo cargo | — |
| [E09](evidencia/fallas/E09.md) | Redis (carrito) no responde | 503 `CART_UNAVAILABLE` | Ningún pedido creado, inventario intacto; el carrito sigue al volver Redis | — |
| [E10](evidencia/fallas/E10.md) | MongoDB detenido | 201 | Eventos `mongo` retenidos; Cassandra, Neo4j y Redis al día con MongoDB caído; todo converge al volver | Demás destinos al día en 6.5 s |
| [E11](evidencia/fallas/E11.md) | Elasticsearch detenido | 201 | La búsqueda sigue en modo degradado (MongoDB); el índice converge al volver | Demás destinos al día en 0.5 s |
| [E12](evidencia/fallas/E12.md) | Neo4j detenido | 201 | La arista `COMPRO` espera en el outbox y llega al volver | Demás destinos al día en 9.1 s |
| [E13](evidencia/fallas/E13.md) | Cassandra detenida | 201 | La proyección analítica se pone al día al volver | Demás destinos al día en 0.5 s |

En E10 la búsqueda (`busqueda`) también espera, porque sus documentos se arman con el
catálogo de MongoDB: es una dependencia de datos, no un bloqueo del outbox.

## Defectos encontrados por las pruebas

La primera corrida (9 de 14) encontró problemas reales, corregidos antes de esta evidencia:

| Hallazgo | Corrección |
|---|---|
| Con un solo consumidor del outbox, una base caída retenía los eventos de todas las demás (bloqueo de cabeza de línea) | Un consumidor por destino (`outbox_service.start_outbox_worker`) |
| Sin tiempos de espera acotados, MongoDB o Neo4j detenidos colgaban al consumidor | `serverSelectionTimeoutMS=5000` en MongoDB; `connection_timeout` y `connection_acquisition_timeout` en Neo4j |
| La proyección de Cassandra leía las imágenes de MongoDB y se detenía con él | Si MongoDB no responde, conserva la imagen ya proyectada (`analytics_service._imagenes_actuales`) |
| Comprobaciones del propio script sensibles al tiempo (E03, E08, E09) | Esperas acotadas y lectura de la bitácora de la saga en lugar de muestrear el estado |

## Conclusión

En ningún escenario se vendió sin stock, se cobró dos veces, quedó un cargo sin pedido ni un
pedido confirmado sin cargo, y ninguna saga quedó a medias. Las caídas de MongoDB,
Elasticsearch, Neo4j, Cassandra o Redis nunca impidieron confirmar una compra ya cobrada:
solo retrasaron su proyección, que convergió al volver el servicio.
