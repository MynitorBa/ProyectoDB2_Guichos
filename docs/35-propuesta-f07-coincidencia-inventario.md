# Propuesta F07 — Coincidencia exacta entre venta e inventario

> **Estado: NO IMPLEMENTADA.** Este documento define una regla futura. No se
> crearon migraciones, nodos, relaciones ni eventos outbox.

## Propósito

F07 busca identificar coincidencias verificables entre una línea de compra
pagada y un aumento posterior de inventario de la misma oferta y exactamente la
misma cantidad. Una coincidencia es una señal para investigación; por sí sola
no demuestra fraude. Reponer lo vendido es una operación comercial normal.

## Regla exacta propuesta

Una línea `Compra` y un `MovimientoInventario` son candidatos cuando se cumplen
simultáneamente estas condiciones:

1. La compra y el movimiento pertenecen a la misma `oferta_id`.
2. La evidencia histórica de la compra atribuye la oferta al mismo vendedor.
   Debe usarse el vendedor registrado en la línea/subpedido o en la proyección
   `Compra-[:A_VENDEDOR]->Vendedor`, no inferirlo del propietario actual.
3. `Compra.cantidad == MovimientoInventario.cantidad` y ambas son positivas.
4. El movimiento ocurre estrictamente después de la compra.
5. La diferencia es mayor o igual a cero y menor o igual a 30 días.
6. El pedido posee pago aprobado y no está cancelado ni totalmente reembolsado.
7. El movimiento es `entrada` o un `ajuste` positivo. Se excluyen `reserva`,
   `liberacion`, `salida` y ajustes no positivos.
8. Se conservan y exponen `linea_id`, `movimiento_id`, oferta, inventario,
   fechas y procedencia de la evidencia.

Cuando exista variante o bodega, se exige coincidencia si ambos lados poseen el
dato. Si un registro histórico no lo posee, el sistema debe marcar “evidencia
insuficiente”; nunca debe inventar la relación.

## Ejemplos

### Positivos informativos

- Compra pagada de 3 unidades de la oferta 80; cinco días después entra un
  movimiento de 3 unidades en la misma oferta y bodega.
- Autocompra pagada de 10 unidades; el propietario registra diez días después
  un ajuste positivo de 10. La combinación F05 + F07 eleva la necesidad de
  revisión, no declara culpabilidad.
- Tres compras distintas tienen, cada una, un movimiento posterior único con
  cantidad exacta. El patrón repetido es más relevante que una coincidencia.

### Negativos

- Compra de 3 y reposición de 20: no hay igualdad exacta.
- Entrada anterior a la compra.
- Movimiento de otra oferta o vendedor.
- Reserva o liberación de una venta flash.
- Salida de inventario.
- Pedido pendiente, cancelado o con reembolso total.
- Reposición ordinaria aislada y respaldada por abastecimiento.

### Ambiguos

- Dos compras de 3 unidades y dos entradas de 3 dentro de 30 días.
- Una compra de 5 con tres ajustes positivos de 5.
- Mismo SKU en bodegas distintas sin bodega registrada en la compra.

Un caso ambiguo no debe generar varias relaciones “confirmadas”. Debe guardarse
como conjunto candidato con su cantidad de alternativas y requerir desempate o
revisión.

## Correspondencia uno a uno

Para evitar inflar la evidencia:

1. Particionar por oferta, cantidad y, cuando exista, variante/bodega.
2. Ordenar compras pagadas por fecha y `linea_id`.
3. Para cada compra, obtener movimientos posteriores no asignados dentro de 30
   días y ordenarlos por menor diferencia temporal y `movimiento_id`.
4. Si existe un único candidato, asignarlo.
5. Si hay varios candidatos con evidencia equivalente, registrar ambigüedad y
   no proyectar `COINCIDE_CANTIDAD` automáticamente.
6. Un movimiento y una línea solo pueden participar en una coincidencia firme.

La asignación debe persistir identificadores de ambos extremos y una versión del
algoritmo para que su repetición sea idempotente y auditable.

## Modelo conceptual Neo4j

Se reutiliza el nodo existente:

```text
(c:Compra {linea_id, pedido_id, oferta_id, cantidad, fecha, pagada})
```

Nodo opcional futuro:

```text
(m:MovimientoInventario {
  movimiento_id,
  inventario_id,
  oferta_id,
  tipo,
  cantidad,
  fecha,
  usuario_id,
  motivo
})
```

Relación conceptual:

```text
(c:Compra)-[:COINCIDE_CANTIDAD {
  diferencia_dias,
  version_regla,
  ambigua,
  detectada_en
}]->(m:MovimientoInventario)
```

La relación significa “cumple las condiciones de coincidencia”, no “es fraude”.
Las consultas de varios saltos aportarían valor al combinar:

```text
Usuario → REALIZO → Compra → COINCIDE_CANTIDAD → MovimientoInventario
Compra → A_VENDEDOR → Vendedor ← GESTIONA ← Usuario
```

Así se pueden estudiar coincidencias repetidas, autocompras y ajustes del
propietario sin convertir el grafo en autoridad transaccional.

## Alternativas técnicas

### A. Detectar en MySQL y guardar expedientes

**Ventajas**

- Los datos autoritativos ya están allí y pueden validarse con pagos, pedidos,
  ofertas e inventario en una sola lectura consistente.
- Menor duplicación y operación más sencilla.
- Idempotencia natural con claves únicas `(linea_id, movimiento_id, versión)`.

**Desventajas**

- Consultas repetitivas y de varios saltos requieren más joins.
- Menos natural para explorar redes entre propietarios, compras, reseñas y
  movimientos.

**Riesgo:** confundir una coincidencia SQL con fraude si el expediente no
explica contexto y ambigüedad.

### B. Proyectar todos los movimientos a Neo4j

**Ventajas**

- Excelente navegación de patrones y visualización de varios saltos.
- Facilita correlaciones futuras entre usuarios, vendedores y movimientos.

**Desventajas**

- Duplica todo el historial de inventario y amplía significativamente el outbox,
  backfill, índices y reconciliación.
- Debe reproducir en el grafo la validez de pagos y pedidos sin volverlo fuente
  de verdad.
- Más costo operativo y más posibilidades de desfase.
- La coincidencia exacta inicial no necesita un grafo completo.

**Riesgo:** falsos positivos durante convergencia eventual o al reconstruir una
propiedad histórica incompleta.

### C. Detectar candidatos en MySQL y proyectar solo casos relevantes

**Ventajas**

- MySQL valida pago, estado, cantidad, oferta y tiempo usando datos
  autoritativos.
- Solo se proyectan coincidencias firmes o expedientes seleccionados, reduciendo
  duplicación.
- Neo4j conserva su valor real: explorar relaciones de varios saltos entre F05,
  F07, reseñas y propietarios.
- El grafo puede reconstruirse desde MySQL y el outbox.

**Desventajas**

- Requiere definir una pequeña proyección, backfill e idempotencia.
- Hay consistencia eventual entre expediente y visualización de grafo.
- Los casos ambiguos necesitan representación explícita o permanecer solo en
  MySQL.

**Riesgo:** proyectar únicamente casos sospechosos puede introducir sesgo en
consultas globales; debe documentarse que Neo4j contiene una proyección de
candidatos, no el universo completo.

## Recomendación

Adoptar **C, enfoque híbrido**:

1. MySQL selecciona y valida candidatos con pago aprobado y correspondencia
   uno a uno.
2. MySQL conserva el expediente, la evidencia, ambigüedad y estado humano.
3. Solo coincidencias firmes o casos seleccionados se proyectan de forma
   idempotente a Neo4j para análisis de varios saltos.
4. Una relación en Neo4j siempre incluye los identificadores autoritativos y la
   versión de F07; el grafo sigue siendo reconstruible.

Esta alternativa evita duplicar todo inventario y aprovecha Neo4j únicamente
donde aporta valor. Antes de implementarla debe corregirse F06, crear fixtures
aislados y medir falsos positivos sobre reposiciones legítimas.

## Severidad y combinación de señales

- **Coincidencia informativa:** un par único sin otras señales.
- **Coincidencias repetidas:** varias parejas firmes para una misma oferta en
  una ventana definida.
- **F05 + F07:** comprador propietario y reposición exacta posterior.
- **F07 + ajustes manuales:** coincidencias repetidas con movimientos `ajuste`,
  especialmente si los realiza el propietario.

La prioridad debe depender de la combinación y repetición; nunca de una
coincidencia aislada.

## Idempotencia y reconstrucción futuras

- Clave estable del candidato: hash de versión, `linea_id` y `movimiento_id`.
- Restricciones únicas en los identificadores de nodos si se aprueba la
  proyección.
- Eventos outbox posteriores al commit MySQL, con destino Neo4j.
- Backfill reejecutable desde fuentes MySQL, sin crear duplicados.
- Reconciliación que compare casos activos, no que borre historia.
- Cambios de algoritmo crean una versión nueva y no reinterpretan silenciosamente
  evidencia previa.

## Matriz mínima de pruebas futuras

| Caso | Resultado esperado |
|---|---|
| Misma oferta/cantidad, movimiento posterior ≤30 días, pago aprobado | Candidato firme |
| Día 0 y día 30 exactos | Incluido |
| Más de 30 días | Excluido |
| Movimiento anterior | Excluido |
| Cantidad diferente | Excluido |
| Oferta/vendedor diferente | Excluido |
| Reserva/liberación/salida | Excluido |
| Pago pendiente/cancelado/reembolsado total | Excluido |
| Dos movimientos candidatos equivalentes | Ambiguo, sin relación firme |
| Repetir proceso | Sin duplicados |
| Propietario + F05 | Evidencia combinada explicable |
| Reposición legítima frecuente | No elevar por sí sola a fraude |
| Neo4j caído | Expediente MySQL válido; proyección reintentable |

## Limitaciones

- La igualdad de cantidades puede ser coincidencia común en productos vendidos
  por paquetes.
- Una reposición puede agrupar varias ventas y no coincidir individualmente.
- Los datos históricos pueden carecer de variante, bodega o dueño vigente.
- Un reembolso parcial requiere una regla explícita antes de implementación.
- El intervalo de 30 días y la severidad necesitan calibración con datos reales.

## Decisiones pendientes antes de implementar

1. Tratamiento exacto de reembolsos parciales.
2. Fuente histórica de vendedor, variante y bodega por línea.
3. Política para casos ambiguos.
4. Umbral de repetición y ventana para elevar prioridad.
5. Qué casos se proyectan a Neo4j y cuánto tiempo se retienen.

## Estado final

F07 queda documentada exclusivamente como propuesta futura. En esta fase no se
crearon `MovimientoInventario` en Neo4j, relaciones `COINCIDE_CANTIDAD`,
migraciones, eventos outbox ni cambios funcionales.
