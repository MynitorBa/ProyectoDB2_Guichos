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
| [E09](evidencia/fallas/E09.md) | Redis (carrito) no responde | 201 | Plan B: el carrito se lee de su copia en MySQL y la compra se confirma; al volver Redis el carrito ya no tiene lo comprado. Antes del plan B respondía 503 `CART_UNAVAILABLE` | — |
| [E10](evidencia/fallas/E10.md) | MongoDB detenido | 201 | Eventos `mongo` retenidos; Cassandra, Neo4j y Redis al día con MongoDB caído; todo converge al volver | Demás destinos al día en 6.5 s |
| [E11](evidencia/fallas/E11.md) | Elasticsearch detenido | 201 | La búsqueda sigue en modo degradado (MongoDB); el índice converge al volver | Demás destinos al día en 0.5 s |
| [E12](evidencia/fallas/E12.md) | Neo4j detenido | 201 | El nodo `Compra` y sus relaciones definitivas esperan en el outbox y llegan al volver | Demás destinos al día en 9.1 s |
| [E13](evidencia/fallas/E13.md) | Cassandra detenida | 201 | La proyección analítica se pone al día al volver | Demás destinos al día en 0.5 s |
| [E14](evidencia/fallas/E14.md) | MongoDB detenido (plan B) | 200 | El catálogo se lee de su copia en MySQL con precios de MySQL | Primera petición 3.3 s, luego sin espera |
| [E15](evidencia/fallas/E15.md) | Elasticsearch y MongoDB detenidos (plan B) | 200 | Búsqueda desde MySQL y autocompletado desde Redis | — |
| [E16](evidencia/fallas/E16.md) | Neo4j detenido (plan B) | 200 | Recomendaciones desde la caché en MySQL; F01–F03 pendientes | — |
| [E17](evidencia/fallas/E17.md) | MySQL detenido (plan B) | 202 `ORDER_QUEUED` | Pedido en cola sin cobrar; al volver MySQL se confirma por la saga | Procesado 6.1 s después de volver |

En E10 la búsqueda (`busqueda`) también espera, porque sus documentos se arman con el
catálogo de MongoDB: es una dependencia de datos, no un bloqueo del outbox.

## Casos específicos: una falla en un instante exacto (C01–C12)

Detener un contenedor no permite elegir el momento de la caída: Redis puede caer antes de que
el usuario presione «Comprar» o un minuto después. Para responder preguntas como «¿qué pasa si
Redis se cae justo cuando presiono Comprar?», cada caso arma un punto de falla
(`app/core/fault_injection.py`) que lanza **el mismo error que el driver del motor caído**
(`redis.ConnectionError`, `OperationalError` 2013 o 1213 de MySQL,
`ServerSelectionTimeoutError` de MongoDB, `httpx.ConnectError`) en ese instante preciso. Así se
ejecuta exactamente el camino de recuperación de una caída real.

Los casos están en el **laboratorio de consistencia**, en el panel «Casos específicos». El
botón «Preparar caso» deja el entorno limpio (sin otros puntos activos y con la pasarela
aprobando) y arma la falla para la próxima acción en la tienda. Cada caso tiene una prueba de
integración en `backend/tests/test_casos_falla.py` y una corrida contra el sistema vivo con
`scripts/demo_fallas.py C01 … C12`.

| # | Pregunta | Qué vio el cliente | Cómo terminó | Medido |
|---|---|---|---|---|
| [C01](evidencia/fallas/C01.md) | ¿Redis cae justo al presionar «Comprar»? | 201 | El carrito se leyó de su copia en MySQL; un solo cargo; al volver Redis el carrito sigue vacío | Checkout 0.25 s |
| [C02](evidencia/fallas/C02.md) | ¿MySQL deja de responder justo al recibir la compra? | 202 `ORDER_QUEUED` | Nada reservado ni cobrado; la cola la confirmó por la saga al volver MySQL | 17.1 s |
| [C03](evidencia/fallas/C03.md) | ¿MySQL cae a mitad de la reserva, con las filas bloqueadas? | 202 `ORDER_QUEUED` | Rollback completo (sin pedido ni stock retenido); la cola la confirmó al volver | 13.1 s |
| [C04](evidencia/fallas/C04.md) | ¿Deadlock con otra compra en el mismo instante? | 201 | La reserva se reintentó sola; un pedido y un cargo | — |
| [C05](evidencia/fallas/C05.md) | ¿Se pierde la respuesta justo después de pagar? | 500, y al reintentar 200 `IDEMPOTENT_REPLAY` | El mismo pedido: ni duplicado ni cobro doble | — |
| [C06](evidencia/fallas/C06.md) | ¿Redis cae al vaciar el carrito, con la venta hecha? | 201 | `carrito.limpiar` del outbox lo retiró; lo comprado no reaparece | 1.0 s |
| [C07](evidencia/fallas/C07.md) | ¿Redis cae al cerrar la reserva flash, con la venta hecha? | 201 | `flash.consumir` del outbox cerró la reserva; la unidad no volvió al cupo | 0.5 s |
| [C08](evidencia/fallas/C08.md) | ¿Redis cae al validar la reserva flash al comprar? | 201 | La reserva se validó en MySQL; compra al precio promocional | — |
| [C09](evidencia/fallas/C09.md) | ¿MongoDB cae al armar las líneas del pedido? | 201 | Nombre del producto desde la copia del catálogo en MySQL, no el SKU | — |
| [C10](evidencia/fallas/C10.md) | ¿Redis cae justo al agregar al carrito? | 201 | Guardado en la copia en MySQL; al volver Redis el carrito se reconstruye | — |
| [C11](evidencia/fallas/C11.md) | ¿Redis aparta la unidad flash pero no responde? | 201 | Reserva en MySQL; la promoción se reconstruyó y la unidad no contó dos veces | — |
| [C12](evidencia/fallas/C12.md) | ¿El servicio de embeddings cae justo al buscar? | 200 (`semantica: false`) | Búsqueda solo de texto, sin esperar timeout; híbrida otra vez al volver | 0.2 s |

Los casos encontraron cuatro respuestas que no eran las correctas. Se corrigieron antes de
generar esta evidencia:

| Caso | Antes | Ahora |
|---|---|---|
| C04 | Un deadlock al reservar llegaba al cliente como 409 «intenta de nuevo» | La reserva (T1, sin nada escrito ni cobrado) se reintenta hasta 3 veces (`checkout_service._reservar_con_reintentos`) |
| C03 | Una caída de MySQL a mitad de la reserva respondía 503 y el cliente perdía la compra | `ReservaInterrumpida`: la compra sigue el plan B y queda en cola como si MySQL hubiera caído antes |
| C05 | Ante un 500, la tienda descartaba la clave de idempotencia; al reintentar, el cliente veía «carrito vacío» aunque su pedido existía | Un 5xx sin resultado definitivo se trata como «sin respuesta»: se conserva la clave y el reintento devuelve el mismo pedido (`CheckoutPage.jsx`) |
| — | El laboratorio se quedaba en blanco al aparecer el destino `catalogo` del outbox | El panel del outbox lo muestra y tolera destinos nuevos |

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
