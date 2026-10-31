# Verificación final del sistema contra el enunciado

Cierre del proyecto: se probó el sistema completo, en marcha, contra cada requisito del enunciado
(`Proyecto_TiendaYa_BasesDeDatos2.docx`): fase inicial, Entregas 1 a 3, entrega final, requisitos transversales
y lineamientos generales. Este documento resume cómo se verificó, qué resultó y qué se corrigió en el camino.

## Cómo se verificó

| Verificación | Herramienta | Resultado |
|---|---|---|
| Requisitos del enunciado, uno por uno, contra el sistema vivo | `backend/scripts/verificar_requisitos.py` → [matriz de requisitos](evidencia/requisitos.md) | **37/37 obligatorios** y el opcional de NewSQL |
| Suite de integración (MySQL, MongoDB, Redis, Cassandra, Neo4j, Elasticsearch reales, sin mocks) | `pytest tests` | **400 pasan, 4 omitidas, 0 fallan** |
| 18 escenarios de falla de punta a punta (pasarela, caída del proceso, de cada motor y de MySQL) | `backend/scripts/demo_fallas.py` → [evidencia](evidencia/fallas/README.md) | **18/18**, 97 comprobaciones |
| Invariantes de consistencia I1–I7 | `backend/scripts/verificar_consistencia.py` | **Todos se cumplen** (104 cobros de la pasarela revisados) |
| Permisos mínimos en Redis, MongoDB y Elasticsearch | `backend/scripts/verificar_permisos.py` → [evidencia](evidencia/permisos.md) | **40/40** como se esperaba |
| Integridad entre los motores (proyecciones, índices, restricciones) | `backend/scripts/verify_setup.py` | **Setup completo** |
| Build de producción del frontend | `npm run build` | Compila sin errores |

`verificar_requisitos.py` no repite lo que ya cubren otras pruebas: cuando un requisito modifica datos de forma no
trivial (una compra atómica, la concurrencia de la venta flash), cita la prueba de integración o el escenario de
falla que lo demuestra y comprueba que existan. Lo demás lo consulta en vivo: la API, las bases de datos y los
documentos exigidos (registros de decisión, diagrama, retrospectiva, informe).

## Hallazgos y correcciones

| Hallazgo | Tipo | Corrección |
|---|---|---|
| Tres pruebas fallaban desde el cambio a varias bodegas (`test_checkout_flash_convierte_reserva_y_descuenta_pool` y dos de `test_fulfillment_vendor_workspace`) | Pruebas desactualizadas, no del producto | Las fixtures ahora registran los movimientos de inventario que la aplicación escribe en producción |
| El sondeo de salud de Cassandra abría la sesión global **sin keyspace**; si era la primera en abrirse, las proyecciones del outbox fallaban con «No keyspace has been specified» | Error del producto | `salud._ping_cassandra` usa la sesión inicializada; prueba de regresión en `test_salud.py` |
| `verify_setup` encontró 17 compras en Neo4j de pedidos que ya no existían en MySQL | Restos de las pruebas | La fixture de checkout borra físicamente sus pedidos de prueba; ahora borra también sus nodos `Compra` (en producción los pedidos nunca se borran: se cancelan, y el outbox retira la compra). Se eliminaron los 17 nodos huérfanos |
| Tras la suite, Cassandra tenía una venta más que MySQL (un pedido de prueba ya borrado) | Restos de las pruebas | Carrera en la limpieza de `reset_stock`: contaba los eventos ya proyectados **antes** de retirar los pendientes, y un evento reclamado entre ambos pasos se proyectaba sin que la limpieza lo supiera. Ahora retira los pendientes, espera a los que están en proceso y cuenta al final; se reconstruyó la proyección con `backfill_cassandra_analytics.py` |
| El registro de decisiones de la Entrega 2 ([26](26-decision-grafos-columnar.md)) comparaba grafos y columnar, pero no tenía los cinco campos que pide el enunciado | Documentación | [ADR-006](51-ADR-006-clave-valor-grafos-columnar.md): Redis, Neo4j y Cassandra con contexto, alternativas (incluida «no cambiar»), decisión, justificación y consecuencias |
| Faltaba la evaluación opcional de NewSQL para el módulo de pagos (Entrega 3) | Opcional | [ADR-007](52-ADR-007-evaluacion-newsql-pagos.md): evaluación analítica; se decide no migrar y se fijan las condiciones para reconsiderarlo |
| La corrida de verificación usaba una contraseña sin carácter especial y el registro la rechazó | De la herramienta | La política de contraseñas funcionaba; ahora la verificación comprueba también que una contraseña débil se rechace con 422 |

Los tres pedidos semilla anteriores a la saga que aparecen como nota en I3 vienen de los datos de prueba originales y
se dejaron a propósito: el verificador los separa de los pedidos de la saga.

## Cómo repetir la verificación

Con los servicios de Docker, el backend con `FAULT_INJECTION_ENABLED=true`, la pasarela (:8001) y el servicio de
embeddings (:8002) en marcha (`scripts/start-dev.ps1`), desde `backend/`:

```powershell
.\venv\Scripts\python.exe scripts\verificar_requisitos.py
.\venv\Scripts\python.exe scripts\verificar_consistencia.py
.\venv\Scripts\python.exe scripts\verificar_permisos.py
.\venv\Scripts\python.exe scripts\verify_setup.py
.\venv\Scripts\python.exe -m pytest tests -q
```

Los escenarios de falla necesitan además `CHECKOUT_RESERVA_MINUTOS=1` y `RECONCILIADOR_GRACIA_S=20` en el backend
y en `scripts\demo_fallas.py`, para que el recolector y el reconciliador actúen en segundos.
