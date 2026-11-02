# Cobro histórico, consistencia y Outbox — cierre técnico Plan B

**Fecha:** 1 de noviembre de 2026. Investigación de solo lectura sobre
PRINCIPAL y DEMO; los eventos sintéticos de consistencia se crearon exclusivamente en
las bases `tiendaya_benchmark_20261101` (MySQL 3337) y Cassandra 9242.

## 1. Cobro de pasarela sin pedido PRINCIPAL

| Campo | Valor comprobado |
|---|---|
| Transacción del simulador | `ch_6d7b1e267f2744f8` |
| Clave de idempotencia | `ca8aac7d-1a53-4cd0-9c80-31221915fd4a` |
| Referencia declarada | `PED-00001844` |
| Momento | 20 oct 2026, 04:03:29 UTC (19 oct, 22:03:29 Guatemala) |
| Monto y moneda | Q799.00 GTQ |
| Estado | `aprobado`, sin motivo ni cambio de estado posterior |

Consultas de lectura en MySQL PRINCIPAL no encontraron ningún pedido con ID
1844 ni con esa clave, ningún pago con la clave o la transacción, y ningún paso
de saga ligado al ID o referencia. PRINCIPAL tiene **40 pedidos** (ID máximo
409), **40 pagos** y **85 líneas**; la compra más reciente registrada allí es
del 23 de septiembre de 2026. No hay en esa base un pedido cancelado,
reembolso, compensación ni registro de recuperación que explique este cobro.
El simulador tampoco registra un reembolso del mismo cargo.

El archivo local `payment_simulator/ledger.db` contiene un solo cobro, el de
arriba. `payment_simulator/ledger.demo.db` contiene doce y **también contiene
exactamente esa transacción, clave, referencia, monto y hora**. El archivo
`ledger.db` fue creado el 17 de octubre y su último cambio coincide con el
cobro del 19 de octubre (hora de Guatemala); `ledger.demo.db` fue creado el
20 de octubre, después de ese cobro. El código usa `ledger.db` por defecto,
mientras `scripts/start-demo-original.ps1` fija `PASARELA_DB=ledger.demo.db`.
La separación de ambos archivos está documentada en
[`docs/42-presentacion-entrega3.md`](42-presentacion-entrega3.md).

**Comprobación definitiva en DEMO:** se inició únicamente el contenedor
`tiendaya_demo_mysql`, identificado por el volumen original
`tiendaya_demo_demo_mysql_data`, el puerto anfitrión `3317` y la base
`tiendaya_demo`. En una transacción `READ ONLY` apareció el pedido **1844**,
`confirmado`, total **Q799.00**, creado el 20 de octubre a las 04:03:30 UTC.
Su pago **1840** está `aprobado` por Q799.00 y contiene exactamente la clave
`ca8aac7d-1a53-4cd0-9c80-31221915fd4a` y la referencia externa
`ch_6d7b1e267f2744f8`. La saga tiene tres pasos consecutivos: reserva `ok`
(paso 92), cobro `aprobado` con esa transacción (93) y confirmación `ok`
(94). No apareció cancelación, reembolso ni compensación posterior. La misma
fila de cobro está tanto en `ledger.db` como en `ledger.demo.db`, comprobados
con SQLite `mode=ro`. Tras la consulta se detuvo MySQL DEMO y Docker Desktop;
no se alteró ningún ledger ni dato comercial.

**Conclusión:** la transacción **sí corresponde al pedido DEMO 1844**. El
invariante I6 fallaba en PRINCIPAL porque su verificador consultaba el archivo
de pasarela de desarrollo que contenía este cobro DEMO. Es una mezcla de
entornos en la verificación, no un pedido PRINCIPAL perdido ni una saga DEMO
incompleta. El momento exacto en que se copió el cobro al segundo ledger no
está probado; las fechas de creación de los archivos son compatibles con una
separación posterior. No hay evidencia de un cargo real a un cliente: la
pasarela es simulada. Tampoco hay base para fabricar un pedido PRINCIPAL o
borrar/reembolsar el cargo.

**Propuesta de corrección:**

1. Documentar el ledger que corresponde a cada instalación y exigir su ruta
   explícita al arrancar pasarela/verificador, evitando mezclar PRINCIPAL y DEMO.
2. Antes de corregir la configuración PRINCIPAL, respaldar ambos SQLite y
   decidir dónde conservar el ledger histórico de DEMO. Preparar un ledger
   PRINCIPAL separado y verificable, sin trasladar ni borrar datos por defecto.
3. Hacer que el verificador registre qué entorno MySQL y qué ledger está
   comparando. Si no coinciden, informar configuración inválida en vez de
   atribuir el cargo a un pedido perdido.

No se modificó ningún ledger, pedido, pago o saga durante esta investigación.

## 2. Verificación de consistencia PRINCIPAL

`backend/scripts/verificar_consistencia.py --json` dio I1–I5 e I7 **OK**;
I6 **FALLA** por el único cobro descrito arriba. I3 recuerda por separado tres
pedidos semilla anteriores a la saga (#13, #14 y #27) ya documentados como
históricos. `verify_setup.py` había informado «Setup completo» en la
validación incremental anterior. Al terminar los benchmarks, PRINCIPAL seguía
con 40 pedidos, 40 pagos, 85 líneas y 48 eventos Outbox; los seis motores y
embeddings respondían `ok`. No se ejecutó checkout ni se escribió en
PRINCIPAL para esta tarea.

## 3. Casos controlados del Plan B en bases aisladas

El script reproducible [`benchmarks/planb_consistency.py`](../benchmarks/planb_consistency.py)
confirma por puerto y nombre de base que no puede apuntar a PRINCIPAL/DEMO;
deshabilita además el acceso a Mongo PRINCIPAL, pues las imágenes son
decorativas para estas métricas. Los pagos aprobados aquí son **filas
sintéticas del benchmark**, no cargos en la pasarela ni checkouts completos.
El detalle de la última corrida está en
[`consistencia.json`](../benchmarks/results/20261101/consistencia.json).

| Caso | Resultado observado |
|---|---|
| Compra pagada nueva | Evento independiente a MySQL y Cassandra; dos fuentes iguales. Primera proyección y comparación: 1.90 s. |
| Compra flash | `unidades_flash` aumentó; dos fuentes iguales. Proyección y comparación: 0.47 s. |
| Reembolso | Ingresos reembolsados y netos coinciden; la compra reembolsada deja de contar como unidad vendida, según la regla vigente. |
| Reprocesar dos veces | Métricas idénticas antes/después; cada línea nueva aparece una sola vez en detalle Cassandra. |
| Cassandra detenida | Destino Cassandra pasó a `error`; destino `analitica_mysql` llegó a `procesado` y la lectura de respaldo siguió disponible. |
| Recuperación | Tras reiniciar Cassandra benchmark, Outbox reintentó y ambos destinos terminaron `procesado`; métricas iguales, sin diferencia permanente. Caída + reinicio + convergencia: 21.58 s. |

Una primera ejecución de la **prueba**, no del sistema, falló porque esperaba
que una compra reembolsada continuara contando como pedido vendido. Se
corrigió esa expectativa y se verificó la idempotencia contra la presencia
única de cada `pedido_linea_id`; la corrida final pasó. La copia aislada
conserva los registros sintéticos de ambas ejecuciones para auditoría.

## 4. Outbox transaccional y retención

El Outbox **permanece en MySQL** y dentro de la transacción comercial. Los
destinos Cassandra y `analitica_mysql` usan filas independientes, de modo que
una caída de uno no impide el avance del otro. No se migró a Redis ni se
modificó la garantía transaccional.

`backend/scripts/audit_outbox_retention.py --retencion-dias 90` se ejecutó
solo en modo lectura: **48 eventos**, todos `procesado` y del destino histórico
`mongo`; **0 candidatos** con 90 días; InnoDB informó 16 KiB de datos y
80 KiB de índices. La propuesta de retención está en
[`docs/54-ADR-outbox-transaccional-y-retencion.md`](54-ADR-outbox-transaccional-y-retencion.md):
clasificar dependencias de auditoría y reconstrucción, excluir cualquier fila
no procesada, ensayar lotes pequeños sobre copia, respaldar y verificar antes
de habilitar una limpieza periódica. **No se ejecutó ningún DELETE.**

## 5. Git, pruebas y límites restantes

- Rama local: `feature/ferxo-cassandra-planb-outbox`.
- Commit base: `d05920e5cb402992e476a68fbefe00fd446a9d0a`
  (`origin/inicio-entrega4`). No se creó commit ni se hizo push.
- Cambios locales del Plan B: migración 27 y ajuste idempotente de 25;
  servicio de respaldo MySQL; rutas API y Outbox; scripts de instalación,
  backfill, auditoría y benchmark; pruebas focalizadas; avisos frontend; y
  documentación 53–56 con evidencia. El PNG de reseña que ya era ajeno a este
  trabajo sigue sin tocarse; el stash anterior permanece guardado.
- Validación: 7 pruebas focalizadas de lógica aprobadas; frontend compilado;
  `verify_setup.py` OK; 23 semanas y cuatro consultas analíticas equivalentes;
  dos repeticiones de carga A/B/C; seis casos controlados de proyección;
  `git diff --check` sin errores en la última revisión.
- Pendiente: medir checkout **real** y saturación con una pila completa aislada; ejecutar
  suite completa de tests en infraestructura de pruebas que tolere escrituras.

El benchmark de dos motores está documentado en
[`docs/55-benchmark-cassandra-vs-mysql-planb.md`](55-benchmark-cassandra-vs-mysql-planb.md).
