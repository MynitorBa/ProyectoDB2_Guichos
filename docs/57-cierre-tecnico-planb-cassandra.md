# Cierre técnico del Plan B de Cassandra

**Fecha:** 1 de noviembre de 2026. **Rama:** `feature/ferxo-cassandra-planb-outbox`. **Base:** `d05920e5cb402992e476a68fbefe00fd446a9d0a`.

## Estado de la implementación

El Plan B queda validado para el conjunto de datos probado. Cassandra sigue siendo la fuente principal de las consultas de tendencias. La migración 27 crea en MySQL tres resúmenes por semana, la tabla de control del backfill y el destino `analitica_mysql` del Outbox. El destino Cassandra y el respaldo MySQL reciben eventos independientes; el consumidor MySQL recalcula y reemplaza la semana desde líneas pagadas. Los reintentos no suman dos veces las ventas. Los endpoints conservan permisos y contrato, indican `fuente_datos` y recurren al respaldo solo cuando falla Cassandra y el backfill está listo. La interfaz advierte el uso de datos de respaldo. El Outbox comercial permanece transaccional en MySQL.

En PRINCIPAL se aplicaron las migraciones 24–27 tras un respaldo restaurado de MySQL y MongoDB. Se compararon 23 semanas, 78 líneas elegibles y las tres proyecciones analíticas: **cero diferencias** en sus métricas. Los casos aislados de compra aprobada, venta flash, reembolso, reprocesamiento y caída/recuperación de Cassandra terminaron con las dos fuentes equivalentes. No se repitieron los benchmarks para este cierre. Véanse [notas de implementación](53-plan-b-cassandra-notas.md), [benchmark](55-benchmark-cassandra-vs-mysql-planb.md) e [investigación de consistencia](56-investigacion-cobro-y-consistencia-planb.md).

## Cobro histórico de Q799 e invariantes

La transacción simulada `ch_6d7b1e267f2744f8`, clave `ca8aac7d-1a53-4cd0-9c80-31221915fd4a`, referencia `PED-00001844`, está aprobada por Q799.00. Consultas exclusivamente de lectura identificaron la base **DEMO** mediante el contenedor `tiendaya_demo_mysql`, volumen `tiendaya_demo_demo_mysql_data`, puerto 3317 y base `tiendaya_demo`. Allí existe el pedido 1844 confirmado por Q799.00, pago 1840 aprobado con la misma clave y referencia de pasarela, y saga con reserva, cobro y confirmación satisfactorias (pasos 92–94). No hay cancelación ni compensación posterior. PRINCIPAL no tiene ese pedido, pago, clave ni saga; su mayor ID de pedido es 409. Ambos archivos SQLite de la pasarela, `ledger.db` y `ledger.demo.db`, contienen el cargo y se consultaron en modo de solo lectura. No se alteró ninguno.

La causa **comprobada** del fallo I6 es que el verificador de PRINCIPAL compara su MySQL con un ledger que contiene un cargo de DEMO. No se pudo establecer en qué momento se copió al segundo ledger. Para corregirlo, se deben fijar rutas de ledger explícitas e independientes para pasarela y verificador de cada entorno, respaldar ambos archivos antes de cualquier cambio y hacer que el verificador muestre la identidad de la base y del ledger; una mezcla debe reportarse como configuración inválida. No se propone borrar, mover ni reembolsar el cargo.

| Invariante | Último resultado observado en PRINCIPAL | Alcance |
|---|---|---|
| I1–I2 | OK | Verificador general previo; no repetido tras apagar servicios. |
| I3 | OK con observación histórica | Pedidos semilla 13, 14 y 27 anteriores a la saga; sin corrección artificial. |
| I4–I5 | OK | Verificador general previo. |
| I6 | FALLA | Explicado por mezcla de ledger DEMO y MySQL PRINCIPAL; configuración aún sin corregir ni revalidar. |
| I7 | OK | Verificador general previo. |

## Rendimiento y operación del respaldo

En el dataset pequeño, MySQL respondió las cuatro consultas de servicio entre 89.6 % y 92.3 % más rápido en media que Cassandra. Esto mide las funciones analíticas, no los endpoints HTTP ni un checkout completo. En la carga concurrente, aumentar los hilos de analítica MySQL de dos a seis redujo 21.1 % el throughput del proxy de inventario frente al escenario MySQL de menor carga y aumentó 23.1 % su latencia media. El proxy solo bloqueó y actualizó filas de inventario con rollback; no incluye carrito, pasarela, pago, saga ni Outbox. El p95 no mostró tendencia monotónica y no se encontró un punto real de saturación.

El respaldo es razonable para una caída breve de Cassandra con backfill completo, volumen analítico limitado y vigilancia del retraso del Outbox. Una caída prolongada o muchas consultas simultáneas pueden competir con pedidos e inventario en MySQL; el recálculo semanal también crece con las líneas de esa semana. Antes de operar con más carga conviene medir p95/p99 de checkout, CPU, conexiones, consultas lentas, esperas de bloqueo y retraso por destino; establecer límites de concurrencia o ritmo de consultas analíticas y criterios para degradar temporalmente las vistas. Estos controles son propuestas, **no límites ya implantados**. El tamaño pequeño, la caché caliente, las duraciones cortas y la máquina compartida impiden extrapolar los porcentajes a millones de líneas.

Para medir checkout completo y un punto de saturación se necesitaría una pila aislada con los seis motores, backend, pasarela y ledgers propios, datos sintéticos representativos y clientes HTTP que recorran carrito, pago, pedido, inventario, saga y Outbox. Habría que comparar A/B/C con repeticiones y aumento gradual de concurrencia hasta observar degradación sostenida, sin exceder RAM ni usar PRINCIPAL. Windows tenía **31.11 GiB físicos y 10.23 GiB libres** al evaluar esta propuesta, con los motores apagados. La DEMO limita sus seis motores a un máximo nominal conjunto de aproximadamente 5.5 GiB, antes de backend, pasarela, frontend, WSL y picos de caché. La prueba parece viable **por turnos y tras un preflight de RAM**, pero no hay margen demostrado para levantarla a la vez que PRINCIPAL y otra pila de benchmark. No se inició ni se ejecutó esta prueba.

## Outbox, pruebas y estado de trabajo

El Outbox permanece en MySQL. El umbral de **90 días** es solo un parámetro evaluable para una eventual retención, no una política definitiva. El dry-run de PRINCIPAL halló **cero candidatos** entre 48 eventos procesados; no se borró nada ni se activó un programador. El [ADR](54-ADR-outbox-transaccional-y-retencion.md) exige clasificación de dependencias, respaldo y validación aislada antes de cualquier limpieza.

Para esta revisión se validó la sintaxis AST de ocho archivos Python y se comprobó `git diff --check` sin errores. En la fase anterior de este mismo trabajo pasaron siete pruebas focalizadas puras y `npm run build` del frontend; también se completaron las comparaciones y casos aislados citados arriba. La suite completa no se ejecutó en esta revisión: sus fixtures pueden escribir datos y los servicios se dejaron apagados a petición del usuario. `verify_setup.py` informó «Setup completo» en la validación incremental anterior, pero no se volvió a ejecutar tras el apagado. Ninguna de estas pruebas equivale a certificar un checkout real bajo carga.

Git mantiene los cambios locales del Plan B en API, Outbox, servicio MySQL, migración 27, scripts, frontend, pruebas, benchmarks y documentación 53–57. No hay staging, commit ni push de esta fase. `stash@{0}` conserva cambios previos de `feature/fraude-automatico`; `stash@{1}` y `stash@{2}` son anteriores. El PNG sin seguimiento bajo `backend/static/reviews/` es ajeno a este trabajo y debe quedar fuera del staging. No se aplicó ni eliminó ningún stash.

**Recomendación:** se puede preparar un commit selectivo del Plan B tras revisar sus archivos y excluir el PNG ajeno. El defecto I6 debe quedar señalado como pendiente operativo separado; no corresponde declarar los siete invariantes verdes hasta separar los ledgers y volver a verificar. No se hizo commit ni push.
