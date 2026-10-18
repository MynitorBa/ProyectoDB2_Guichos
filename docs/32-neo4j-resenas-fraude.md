# Neo4j definitivo: compras, recomendaciones, reseñas y señales de fraude

## Responsabilidad de cada motor

- **MySQL es la autoridad** de usuarios, vendedores, ofertas, inventario,
  pedidos, pagos, reseñas, imágenes, respuestas y expedientes de fraude.
- **Neo4j es una proyección reconstruible** de relaciones pagadas. No decide
  precios, existencias, elegibilidad de una reseña ni sanciones.
- El transactional outbox lleva compras y cambios de reseñas hacia Neo4j. Si
  el grafo se detiene, checkout y reseñas MySQL siguen funcionando; los eventos
  se reintentan al recuperarse.

## Modelo proyectado

```text
(Usuario)-[:REALIZO]->(Compra {linea_id, pedido_id, oferta_id,
                               fecha, cantidad, precio_unitario, sku,
                               promocion_flash_id, pagada})
(Compra)-[:DE_PRODUCTO]->(Producto)
(Compra)-[:A_VENDEDOR]->(Vendedor)

(Usuario)-[:GESTIONA]->(Vendedor)
(Vendedor)-[:OFRECE {oferta_id, producto_variante_id,
                      variante_ref, sku, estado}]->(Producto)

(Usuario)-[:ESCRIBIO]->(Reseña)-[:SOBRE]->(Producto)
(Reseña)-[:CALIFICA_A]->(Vendedor)
(Reseña)-[:BASADA_EN]->(Compra)
```

`Compra.linea_id` es único. `OFRECE` no replica precio ni stock: esos valores
siempre se leen desde MySQL. Una variante se identifica mediante las referencias
canónicas existentes, sin crear otro nodo.

La arista histórica `COMPRO` se conserva temporalmente para validar las
consultas heredadas. Las funciones nuevas usan exclusivamente nodos `Compra`.
No debe borrarse hasta autorizar el corte y comprobar que ninguna consulta la usa.

## Reseñas

La migración `database/mysql/21_review_authority.sql` amplía `resenas` y crea
`resena_imagenes` y `resena_respuestas`. La restricción transaccional es:

```text
UNIQUE(usuario_id, producto_referencia_id, vendedor_id)
```

El backend comprueba en MySQL una línea del mismo usuario, producto y vendedor,
con pago aprobado y pedido no cancelado/reembolsado. Comprar nuevamente permite
editar la misma reseña, nunca crear un duplicado. Una compra a otro vendedor es
otra combinación válida. Las reseñas heredadas no demostrables se conservan
pendientes y no se publican.

Si el pedido de respaldo se cancela o reembolsa, el servicio intenta enlazar
otra compra elegible; si no existe, retira la verificación y conserva la reseña
para auditoría.

## Recomendaciones

`GET /api/v1/products/{producto_ref}/recommendations` implementa “quienes
compraron X también compraron Y”. Cuenta compradores distintos, excluye el
producto base y, para usuarios autenticados, productos ya adquiridos. Después
MySQL vuelve a validar que exista una oferta activa con stock. La vista aparece
en el detalle del producto y se oculta limpiamente si no hay resultados o
Neo4j está temporalmente fuera de servicio.

## Fraude y alertas

El análisis genera indicios, no decisiones automáticas:

- autocompra: `(Usuario)-[:GESTIONA]->(Vendedor)` y ese mismo usuario realizó
  una `Compra` hacia el vendedor;
- frecuencia y volumen de autocompras;
- coincidencia con entradas o ajustes positivos de la oferta;
- movimientos positivos frecuentes o grandes durante 30 días;
- bombardeo, concentración por vendedor y grupos de reseñadores comunes;
- compras flash efectivamente pagadas (`promocion_flash_id`), nunca reservas.

La consulta retrospectiva de ventas flash expone tanto las líneas pagadas como
un resumen por promoción con compradores distintos, unidades, ofertas y la
concentración máxima atribuible a un solo comprador.

Los umbrales son criterios académicos configurables, no un modelo estadístico
validado. `alertas_fraude` persiste motivos, evidencias, prioridad y el flujo
`pendiente → en_revision → revisada/descartada`. Ninguna alerta modifica stock,
cancela pedidos o suspende cuentas.

## Instalación, reconstrucción y comprobación

Desde `backend/`:

```powershell
.\venv\Scripts\python.exe scripts\apply_review_authority.py
.\venv\Scripts\python.exe scripts\apply_fraud_alerts.py
.\venv\Scripts\python.exe scripts\backfill_neo4j_reviews.py --dry-run
.\venv\Scripts\python.exe scripts\backfill_neo4j_reviews.py --apply
.\venv\Scripts\python.exe scripts\verify_setup.py
```

`apply_review_authority.py` crea primero un respaldo JSON en
`backups/reviews/`. Tras la primera migración, volver a ejecutarlo no copia el
estado de Neo4j hacia MySQL porque MySQL ya es la autoridad.

Neo4j Browser: `http://localhost:7474`. Consultas útiles:

```cypher
MATCH (u:Usuario)-[:REALIZO]->(c:Compra)-[:DE_PRODUCTO]->(p:Producto)
RETURN u, c, p LIMIT 50;

MATCH (v:Vendedor)-[o:OFRECE]->(p:Producto)
RETURN v, o, p LIMIT 50;

MATCH (r:Reseña)-[:BASADA_EN]->(c:Compra)
RETURN r, c LIMIT 50;
```

La verificación espera igualdad entre MySQL y Neo4j para compras válidas,
ofertas y reseñas respaldadas.
