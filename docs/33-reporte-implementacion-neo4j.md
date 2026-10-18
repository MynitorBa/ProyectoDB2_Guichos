# Reporte de implementación definitiva de Neo4j

Fecha de trabajo: 17 de octubre de 2026. Rama local: `entrega3-mynor`.
Commit local de implementación revisado:
`66328618eaab842a439fb48215df2b8a48d69953`.

Este reporte distingue lo implementado de lo comprobado. No sustituye el
procedimiento de instalación ni autoriza eliminar el modelo heredado.

## Fase 0 — Auditoría y protección

- Se preservaron los cambios locales que ya existían.
- La línea base comprobada antes del corte contenía 42 reseñas, 77 líneas
  pagadas válidas y 78 relaciones `COMPRO`; una relación era heredada sobrante.
- Se preparó respaldo JSON previo a la migración en `backups/reviews/`.
- No se reinicializaron volúmenes ni se eliminaron registros históricos.

## Fase 1 — Autoridad de reseñas

- `database/mysql/21_review_authority.sql` amplía `resenas` y crea las tablas
  durables de imágenes y respuestas.
- MySQL impone `UNIQUE(usuario_id, producto_referencia_id, vendedor_id)`.
- La elegibilidad exige una línea del mismo usuario, producto y vendedor, pago
  aprobado y pedido no cancelado ni reembolsado.
- Se permite editar la reseña existente, no crear otra para la misma combinación.
- Cancelar o reembolsar revalida el respaldo sin borrar la reseña.
- API, detalle de producto, imágenes, respuestas, moderación y calificaciones
  de búsqueda leen desde MySQL. Neo4j recibe la proyección mediante outbox.

Conciliación local aplicada: 42 reseñas conservadas; 17 tenían compra pagada
atribuible y 25 quedaron pendientes/no verificadas. No existían imágenes ni
respuestas heredadas que migrar en esta instancia.

## Fase 2 — Grafo definitivo

Modelo nuevo:

```text
Usuario -REALIZO-> Compra -DE_PRODUCTO-> Producto
                         -A_VENDEDOR-> Vendedor
Usuario -GESTIONA-> Vendedor -OFRECE-> Producto
Usuario -ESCRIBIO-> Reseña -SOBRE-> Producto
                            -CALIFICA_A-> Vendedor
                            -BASADA_EN-> Compra
```

- `Compra.linea_id` es único.
- `OFRECE` conserva identificadores, variante, SKU y estado, nunca precio o stock.
- Compras, cancelaciones, ofertas y reseñas se sincronizan idempotentemente por
  el outbox; una caída de Neo4j no bloquea checkout ni reseñas MySQL.
- El backfill es reconstruible desde MySQL y MongoDB.

Conciliación local aplicada: 77 nodos `Compra`, 72 relaciones `OFRECE`, 42
reseñas y 17 relaciones `BASADA_EN`.

## Cierre de dependencias heredadas `COMPRO`

- La proyección de compras crea solamente `Compra`, `REALIZO`, `DE_PRODUCTO` y
  `A_VENDEDOR`; dejó de escribir `COMPRO`.
- La cancelación retira el nodo `Compra` correspondiente y ya no intenta borrar
  una arista heredada.
- El escenario E12 de `demo_fallas.py` comprueba el modelo definitivo después
  de recuperar Neo4j.
- `simulate_fraud.py` quedó como auditoría de solo lectura. Ya no inyecta ni
  elimina nodos para fabricar casos.
- `seed_reviews.py` quedó retirado como generador heredado y remite al backfill
  idempotente desde las autoridades actuales.
- Se retiró el CRUD de reseñas Neo4j que ya no tenía consumidores; las rutas
  autoritativas permanecen en `review_mysql_service.py`.
- Una prueba de regresión inspecciona estos consumidores para impedir que
  `COMPRO` vuelva a introducirse.

Al cerrar esta fase funcional, las 80 relaciones `COMPRO` todavía no habían sido
modificadas: se conservaron temporalmente como evidencia histórica inerte hasta
la operación separada, expresamente autorizada y respaldada, que se documenta
en la sección **Limpieza definitiva de `COMPRO`** de este reporte.

Los tres pedidos semilla anteriores a la saga (`13`, `14` y `27`) se mantienen
sin alteraciones. Se identifican por no tener `clave_idempotencia`; el
verificador los reporta como nota histórica y aplica el invariante de pago
solamente a pedidos creados por la saga. No se reescriben para simular datos
modernos ni se eliminan.

## Fase 3 — Recomendaciones

- `GET /api/v1/products/{producto_ref}/recommendations` implementa compradores
  comunes contando usuarios distintos.
- Excluye el producto consultado y, en recomendaciones personalizadas, los ya
  comprados por el usuario.
- MySQL revalida oferta activa, precio y stock. Si Neo4j falla, responde una
  lista vacía y la tienda continúa funcionando.
- El detalle del producto muestra la sección solo cuando existen resultados.

## Fase 4 — Fraude explicable

- La migración `22_fraud_alerts.sql` crea expedientes deduplicados y revisables.
- Se detectan autocompras por `GESTIONA`, frecuencia, volumen y concentración
  respecto a las unidades pagadas de la oferta.
- Se correlacionan movimientos de inventario dentro de ±3 días, movimientos
  realizados por el propietario y reseñas respaldadas por esas compras.
- Inventario atípico exige evidencia combinada; vender y reponer normalmente no
  basta para abrir una alerta.
- Las alertas almacenan motivos, evidencia, prioridad y estado administrativo.
  Nunca suspenden cuentas, cancelan pedidos ni cambian stock automáticamente.

## Fase 5 — Ventas flash y cierre

- Neo4j recibe `promocion_flash_id` únicamente en líneas convertidas y pagadas.
- Se pueden consultar las líneas históricas y el resumen por promoción:
  compradores distintos, unidades, ofertas y concentración máxima por comprador.
- `verify_setup.py` concilia compras, ofertas y reseñas respaldadas contra MySQL,
  además de verificar la autoridad y unicidad de reseñas.

## Evidencia de pruebas

- Compilación Python de los módulos modificados: aprobada.
- El commit definitivo agregó nueve pruebas de modelo, unicidad, atribución a
  vendedor, recomendaciones, fraude, ventas flash y rutas de outbox. El dato
  anterior de “ocho nuevas” era un conteo preliminar; no se eliminó ni sustituyó
  ninguna prueba. La base inmediatamente anterior tenía 162 y quedó en 171.
- Este cierre agrega dos regresiones para impedir la reintroducción de `COMPRO`
  en consumidores y para validar E12 contra el nodo `Compra` completo.
- Build de producción del frontend: aprobado.
- `setup.ps1` y `verify_setup.py` terminaron en `Setup completo` con 77 compras,
  72 ofertas, 42 reseñas y 17 respaldos `BASADA_EN` proyectados en Neo4j.
- `verificar_consistencia.py` confirmó los siete invariantes, incluida la
  comparación entre MySQL y el libro de la pasarela simulada.
- La diferencia Cassandra 78 / Neo4j 77 no es una divergencia: Cassandra
  conserva además la línea 106 del pedido reembolsado 96 para calcular ingresos
  reembolsados y netos; Neo4j proyecta únicamente las 77 compras pagadas que
  siguen vigentes. `setup.ps1` volvió a ejecutar el backfill idempotente y
  conservó exactamente las mismas 78 líneas; no cambió el contenido lógico ni
  se intentó ajustar artificialmente la diferencia.
- Antes de este cierre, la suite integral terminó con **171 pruebas aprobadas y
  0 fallos**. Tras agregar las dos regresiones, la ejecución final terminó con
  **173 pruebas aprobadas y 0 fallos**.
- La compilación final de Vite procesó 3060 módulos y terminó correctamente.

## Comandos finales de comprobación

Desde la raíz:

```powershell
.\scripts\setup.ps1
cd backend
.\venv\Scripts\python.exe scripts\verify_setup.py
.\venv\Scripts\python.exe -m pytest tests -q
cd ..\frontend
npm run build
```

La implementación definitiva ya estaba conservada en el commit local
`66328618eaab842a439fb48215df2b8a48d69953`. El retiro de consumidores heredados
se consolidó posteriormente en el segundo commit indicado a continuación. No
se hizo push.

## Limpieza definitiva de `COMPRO`

Fecha de ejecución: 17 de octubre de 2026, hora de Guatemala. Segundo commit
local previo a la operación:
`3455b76b4554e11585a3240f9b39f9d329221d0b`.

- Se auditaron 80 relaciones heredadas `COMPRO`, con 11 usuarios y 48 productos
  distintos. Todos los extremos y los 80 `pedido_id` pudieron resolverse.
- El respaldo restaurable se guardó fuera de Git en
  `C:\Users\fboan\Documents\ChatGPT\Proyecto Base de datos\Respaldos TiendaYa\neo4j\compro_legacy_20261018_054437.json`.
- SHA-256 del archivo:
  `c2e736fa4026f306d972fff6346d8b3bfe3bc28a4a7482bf706cc7fac1ce307b`.
- SHA-256 del arreglo canónico de relaciones:
  `e4f469209ae90e4a2294c068236c61823f0db38361b721ddb7a98e5cd95d027f`.
- El respaldo se releyó, conservó 80 registros, coincidió con el estado de
  Neo4j, resolvió sus 80 usuarios y productos y la consulta de restauración fue
  validada con `EXPLAIN`.
- Una única transacción eliminó exactamente 80 relaciones con
  `MATCH ()-[r:COMPRO]->() DELETE r`. No se usó `DETACH DELETE` ni se eliminaron
  nodos u otras relaciones.
- Resultado final: 0 `COMPRO`, 77 `Compra`, 77 `DE_PRODUCTO`, 77 `A_VENDEDOR`,
  72 `OFRECE` y 17 `BASADA_EN`; no hay compras incompletas.
- MySQL conserva 42 reseñas (17 verificadas y 25 históricas no verificadas) y
  los pedidos semilla 13, 14 y 27.
- El backfill Neo4j reconstruyó la proyección definitiva y `COMPRO` permaneció
  en cero. `verify_setup.py` terminó correctamente, los siete invariantes se
  cumplieron y la suite final aprobó 173 pruebas.
- No se ejecutó `setup.ps1` completo después de la eliminación porque también
  reconstruye Cassandra y esta operación prohibía modificarla. Se ejecutó
  directamente el mismo backfill Neo4j invocado por setup y se comprobó en el
  código que setup, backfill y outbox no contienen consumidores de `COMPRO`.

El modelo Neo4j definitivo opera exclusivamente con nodos `Compra` y las
relaciones `REALIZO`, `DE_PRODUCTO` y `A_VENDEDOR`. El respaldo debe conservarse
hasta el cierre académico o hasta que el equipo autorice retirarlo.
