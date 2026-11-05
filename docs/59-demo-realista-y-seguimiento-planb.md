# DEMO realista y seguimiento de planes B

## Estado vigente verificado — 5 de noviembre de 2026

Este documento es la fuente de estado actual de la DEMO. Los diagnósticos de
sesiones anteriores se conservan al final como contexto histórico y no deben
interpretarse como el estado instalado hoy.

- Rama revisada: `feature/ferxo-demo-realista-planb-monitoreo`, base `9f28dad`.
- PRINCIPAL permaneció apagada y no se modificó.
- DEMO conserva las migraciones 24–27.
- La corrida `entrega4-realista-v1` completó el perfil `small`; volver a
  ejecutarlo no cambió conteos ni stock. `medium` no se ha ejecutado.
- Los respaldos preservados de los ocho volúmenes, `.env.demo` y
  `ledger.demo.db` coinciden con su manifiesto SHA-256.
- Los tres stashes existentes y el PNG de reseña ajeno al trabajo permanecen
  intactos.

| Dato DEMO | Conteo comprobado |
|---|---:|
| Usuarios / vendedores | 745 / 44 |
| Productos / ofertas / inventarios | 325 / 491 / 489 |
| Pedidos / líneas / pagos / reseñas | 1,822 / 2,714 / 1,822 / 825 |
| MongoDB | 325 productos y 325 variantes |
| Respaldo de catálogo MySQL | 650 documentos |
| Neo4j | 2,575 `Compra`, 491 `OFRECE`, 825 `Reseña`, 720 `BASADA_EN`, 0 `COMPRO` |
| Elasticsearch | 325 documentos con vector de 768 dimensiones |

## Analítica y Plan B

Cassandra y el respaldo analítico MySQL contienen 38 semanas. Se compararon
las 1,851 filas de producto/semana en ocho métricas por fila y no hubo
diferencias. Las dos vistas por vendedor contienen 2,483 filas en cada motor.
Cassandra continúa como fuente analítica primaria; MySQL se usa únicamente
cuando el circuito de Cassandra está abierto y su backfill está completo.

Los consumidores de `analytics.pedido_actualizado` reconstruyen la semana
desde las autoridades MySQL: eliminan el resumen de la semana y vuelven a
generarlo. No incrementan contadores a partir del payload, por lo que repetir
un evento no duplica ventas. La proyección Neo4j usa
`MERGE (c:Compra {linea_id: ...})`, de modo que repetir una compra tampoco crea
otro nodo.

## Seguridad y búsqueda vectorial

Las credenciales restringidas de aplicación se validaron sin operaciones
destructivas: Redis permitió `PING` y rechazó `ACL LIST`; MongoDB permitió leer
productos y rechazó administrar usuarios; Elasticsearch permitió leer
`productos_demo` y rechazó administrar usuarios. Elasticsearch estaba `green`.

Los 325 documentos están vectorizados. Sin reindexar se comprobaron cuatro
búsquedas semánticas: portátil de oficina, herramienta recargable, novela
espacial y calzado para correr. Las familias nuevas pertinentes ocuparon los
primeros puestos; productos históricos genéricos reducen la precisión de
algunos puestos bajos, pero no desplazan sistemáticamente los productos
nuevos.

## Incidentes, fraude y cola de pedidos

Durante una caída controlada de Neo4j, F04 siguió disponible desde MySQL y
F01–F03 quedaron pendientes, no en cero. F05–F07 históricos permanecieron
consultables. La corrida fallida no desactivó alertas; al recuperar el grafo,
la siguiente corrida fue exitosa y conservó decisiones y notas humanas. Una
caída que exceda la ventana de detección todavía requiere reproceso histórico
acotado antes de afirmar cobertura total.

La bitácora registró una sola activación por incidente, cerró la recuperación,
persistió al reiniciar y mantuvo `estado_sync=no_verificado` hasta comprobar
convergencia. El endpoint exige rol administrador y no almacena trazas ni
credenciales.

La cola de MySQL se probó con una solicitud sintética aislada en Redis: la
misma clave devolvió el mismo identificador, no se llamó a la pasarela y se
retiraron solamente las claves creadas para la prueba. El procesamiento
posterior de una compra en cola sigue pendiente de un entorno integral
temporal; no se ejecutó contra la DEMO viva.

## Pedido histórico DEMO #1851

### Diagnóstico histórico previo a la conciliación

1. El 20-oct-2026 20:50:33 se crearon el pedido 1851, pago 1847, línea 2546 y
   la reserva de una unidad del inventario 507 para la oferta 768.
2. La pasarela DEMO aprobó Q10,000 GTQ como `ch_aa444fb6f6ee4289`, referencia
   `PED-00001851`, con la misma clave idempotente. Tres respuestas terminaron
   en `ReadTimeout`; MySQL dejó el pago `en_verificacion`.
3. Solo existía el movimiento 2753 (`reserva`). No había `salida` ni
   `liberacion`; el inventario permanecía 9 disponible/1 reservado.
4. No existía paso de saga de confirmación, conciliación o compensación.
5. El 21-oct un cambio administrativo confirmó el pedido, creó el envío 29 y
   lo marcó entregado sin convertir la reserva en venta.
6. Neo4j no contenía `Compra(linea_id=2546)` y la analítica excluía la línea.
   MongoDB y Elasticsearch ya mostraban stock visible 8 porque calculan
   disponible menos reservado.

La causa fue un defecto real: el flujo administrativo permitía avanzar un
pedido con tarjeta `en_verificacion` y cambiaba el estado sin ejecutar la saga
comercial. La corrección actual impide confirmar, preparar, enviar o entregar
con pago incierto; contra entrega pendiente sigue siendo válida. Confirmar
administrativamente usa `confirmar_pedido`, por lo que el inventario, la saga
y el Outbox se escriben atómicamente.

Los pedidos semilla 13, 14 y 27 son anteriores a la saga y conservan pago
pendiente. No se modificaron; la protección nueva impide seguir avanzándolos
sin un pago comercialmente válido.

### Selección autoritativa del pago

El esquema no impone unicidad sobre `pagos.pedido_id`: el índice es ordinario.
Sí impone unicidad sobre `pagos.clave_idempotencia`. En la DEMO actual hay
1,822 pagos para 1,822 pedidos y cero pedidos con más de un pago, pero esa
igualdad es un dato actual, no una garantía estructural.

Checkout y fulfillment ahora usan la misma regla: seleccionan bajo bloqueo el
único pago cuya clave coincide con `pedidos.clave_idempotencia`; para registros
anteriores a la saga aceptan una única fila sin clave. Si quedan varias filas
sin selección inequívoca, detienen la operación. Nunca eligen por ser la
primera o la última.

### Carrito y conciliación histórica

La confirmación normal elimina únicamente las ofertas compradas del carrito,
pero el pedido 1851 tiene más de dos semanas. El comprador pudo haber agregado
después la misma oferta. Por ello una conciliación histórica **no debe** emitir
`carrito.limpiar` ni llamar a `carrito_respaldo.quitar_ofertas()`: esos efectos
pertenecen al contexto efímero del checkout original y hoy no pueden
demostrarse.

Tampoco hace falta emitir otra proyección de inventario: convertir 9/1 en 8/0
mantiene el stock visible en 8 y los dos eventos originales ya proyectaron ese
valor. Los eventos necesarios son solamente:

- `analytics.pedido_actualizado` para Cassandra, respaldo MySQL y búsqueda;
- `grafo.compra_registrada` para Neo4j.

Ambos consumidores recalculan o hacen `MERGE`; no aplican un delta ciego.

### Conciliación aplicada y verificada

La migración 28 creó `conciliaciones_historicas` con unicidad por huella y por
`(entorno, pedido, tipo)`. Antes de tocar DEMO se restauró una copia completa
en una base temporal. Allí pasaron: falla antes del commit con rollback total,
aplicación, segunda ejecución sin efectos, conservación del carrito y ausencia
de cambios en otros pedidos y pagos.

El respaldo previo definitivo está fuera de Git en
`_backups/historical-reconciliation-1851/20261105_090302/`. El SQL tiene
SHA-256 `C0FC119A0AC2DE3D7C282D09C8D2BEB16CCAE0A1A6F2F38212369E55636A4DC5`.
El ledger copiado y el original mantuvieron SHA-256
`6AD5C81A48CEF55E68746045BDB0473990AB153A927C79F1919D1EA3972A2314`.

La conciliación DEMO se confirmó con:

- operación `de863135-c34b-5c78-985f-52ae1d9efa34`;
- huella `97a974c5d145f5deb70a6692afa7decefc263e447821a9ad87b28fecbf956bbe`;
- inventario 507 de 9/1 a 8/0;
- una sola salida, movimiento 3066, cantidad 1;
- oferta 768 de versión 3 a 4;
- pago 1847 de `en_verificacion` a `aprobado`, referencia
  `ch_aa444fb6f6ee4289`;
- pedido, subpedido y envío conservados como `entregado`;
- un paso `conciliacion_historica/ok`;
- tres eventos `analytics.pedido_actualizado` y uno
  `grafo.compra_registrada`.

No se llamó a la pasarela para cobrar, no se modificó el ledger, no se limpió
el carrito y no se generaron eventos flash ni de inventario. Ejecutar de nuevo
el servicio devolvió `ya_aplicada=true` y conservó los conteos 1 bitácora, 1
salida, 1 paso de saga y 4 eventos.

Las cuatro rutas Outbox se procesaron una vez y sin errores. Cassandra y el
respaldo MySQL quedaron iguales para la semana del 19-oct: oferta 768 con 2
unidades/Q20,000 y producto `6ad59a9a7bee255d17e63eae` con 4
unidades/Q25,598. Neo4j contiene exactamente una `Compra(linea_id=2546)`.
I1–I7 quedaron verificados y correctos; I3 conserva solo la nota histórica de
los pedidos semilla 13, 14 y 27.

## Regresiones de fulfillment

Las pruebas focalizadas usan una transacción externa por caso y revierten toda
escritura. Pasaron 7/7:

- permisos de administrador y vendedor en envíos parciales;
- bloqueo de confirmación y despacho con tarjeta en verificación;
- bloqueo explícito de preparación y entrega con tarjeta en verificación;
- selección del pago ligado a la clave del pedido aun con una fila posterior;
- contra entrega pendiente válida;
- confirmación administrativa idempotente, sin segunda salida ni Outbox;
- falla antes del commit con rollback de inventario, movimientos y Outbox.

El guard de Pytest impidió correctamente ejecutar la suite de integración
contra la DEMO de presentación. No se declara la suite completa como aprobada.
Además pasaron 3/3 pruebas unitarias de conciliación: huella estable,
restricciones únicas de la migración y lectura del ledger en modo `ro` sin
modificarlo ni retener su archivo abierto.

## Pendientes y límites

- La conciliación del pedido 1851 está aplicada, reproyectada e idempotente.
- El perfil `medium`, la prueba integral de cola y una nueva simulación larga
  de caída de Neo4j siguen pendientes.
- La publicación en GitHub queda pendiente de autorización; los cambios se
  preparan en commits locales para revisión.

## Contexto histórico reemplazado

Antes de aplicar migraciones 24–27 y el perfil pequeño, la DEMO tenía 665
usuarios, 36 vendedores, 285 productos, 431 ofertas, 1,642 pedidos, 2,515
líneas y 745 reseñas. Esos conteos describen el estado anterior y se conservan
solo para explicar la evolución; no deben usarse en la presentación como
estado vigente. La DEMO limpia incompleta tampoco es la instancia activa.
