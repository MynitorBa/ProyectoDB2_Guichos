# Línea base de la Entrega 3

Estado del sistema medido el 2026-10-06 en la rama `entrega3-mynor`, antes de
cualquier cambio de la Entrega 3. Sirve para dos propósitos:

1. Distinguir los problemas que ya existían de cualquier regresión que se
   introduzca durante la entrega.
2. Sustentar con evidencia el diagnóstico que motiva el motor de búsqueda y la
   estrategia de consistencia del checkout.

## 1. Regresión inicial

| Verificación | Resultado |
|---|---|
| `pytest tests -q` | **88 aprobadas, 1 fallida** |
| `scripts/verify_setup.py` | Error: "MongoDB Fase 5: 3 proyecciones pendientes o divergentes" |
| `npm run build` | Correcto |

La prueba fallida (`test_setup_regressions.py::test_runtime_index_and_all_existing_projections_are_synchronized`)
y el error de `verify_setup.py` tienen la misma causa:

| Producto | Campo | MongoDB | MySQL (esperado) |
|---|---|---|---|
| Laptop Dell Inspiron 15 | `stock` | 9 | 16 |
| Airpods Pro 2da generación | `stock` | 51 | 107 |
| gadieles2 | oferta principal | #133 TiendaYa, Q1000, stock 0 | #134 ModaExpress GT, Q100, stock 9 |

**Causa raíz.** El checkout encola `inventario.actualizado` con la proyección
`{'stock': stock_de_la_oferta_vendida}` (`checkout_service.py:286-298`). En
MongoDB, `stock` representa la **suma de todas las ofertas** del producto, y la
oferta principal depende del stock de todas ellas. La proyección del checkout
es un *delta parcial* que sobrescribe un valor agregado:

- Dell: la venta de la oferta #135 (stock 9) reemplazó el total 7 + 9 = 16.
- gadieles2: al agotarse la oferta TiendaYa #133, el evento solo marcó su stock
  en 0 y no recalculó que la oferta principal pasa a ser la #134.

**Corrección prevista:** Fase 3 (outbox v2). El destino `mongo` recalculará la
proyección completa desde el estado actual de MySQL al procesar cada evento.
Esto la vuelve independiente del orden y repetible, y se agregará una prueba
que reproduzca este caso.

## 2. Diagnóstico de la búsqueda

Tabla completa en [`busqueda-linea-base.md`](busqueda-linea-base.md),
generada con `backend/scripts/comparar_busqueda.py` sobre 17 consultas.

| Motor | Aciertos en top 3 | Latencia promedio |
|---|---|---|
| MongoDB `$regex` (lo que usa hoy el catálogo) | **6/17** | 1.2 ms |
| MongoDB `$text` (índice existente, sin uso) | **10/17** | 1.3 ms |

Hallazgos:

- **`$regex` es una comparación de subcadena exacta.** Solo acierta cuando la
  consulta aparece literalmente en el nombre o SKU (`laptop`, `lapto`, `sams`,
  `tala`, SKU). Falla con tildes omitidas (`audifonos`, `cafe`), con el orden de
  palabras invertido (`inspiron dell`) y con cualquier error ortográfico que
  no sea un prefijo (`macbok`, `samsng`).
- **`$text` no tolera errores ortográficos.** Sus aciertos en `samsng galaxy`
  y `harry poter` se deben a que *otra* palabra de la consulta coincide
  (`galaxy`, `harry`). Con una sola palabra mal escrita (`lapto`, `macbok`)
  devuelve 0 resultados. Tampoco admite prefijos (`sams`, `tala`) ni SKU.
- **Ninguno de los dos resuelve sinónimos** (`telefono` → celulares,
  `portatil` → laptops).
- **La relevancia de `$text` es pobre.** Para `laptop` pone primero el
  producto "CER", y para `zapatillas nike` pone el balón de fútbol antes que los
  tenis.
- **No hay facetas.** El listado carga todos los documentos de MongoDB,
  enriquece y filtra en Python y pagina en memoria
  (`catalog_service.listar_productos`). Los conteos por categoría, precio o
  atributo requerirían agregaciones adicionales.

Estos resultados motivan el motor de búsqueda (Fases 2 a 5). Las mismas
consultas se volverán a medir contra Elasticsearch para la tabla comparativa
del ADR.

## 3. Diagnóstico del checkout

Componentes que participan hoy en `POST /orders/checkout` y comportamiento ante
fallas:

| Paso | Componente | Comportamiento actual |
|---|---|---|
| Leer carrito | Redis | Si Redis falla responde `503 CART_UNAVAILABLE` sin efectos (correcto) |
| Validar reserva flash | Redis | Si venció responde `422 FLASH_RESERVATION_INVALID` (correcto) |
| Crear pedido, descontar stock y aprobar pago | MySQL, una transacción | El pago se marca `aprobado` dentro de la misma transacción (`checkout_service.py:322`); **no existe un paso externo que pueda fallar** |
| Proyecciones MongoDB y Cassandra | Outbox | Encoladas en la misma transacción; se reintentan hasta 5 veces y luego quedan en `error` sin backoff ni vista administrativa (`outbox_service.py:18`, `:158`) |
| Arista `COMPRO` en Neo4j | Neo4j | Se escribe después del commit dentro de `try/except: pass` (`checkout_service.py:337-365`). **Si Neo4j falla, la compra nunca se registra en el grafo y el cliente no puede publicar una reseña verificada.** No hay reintento ni registro |
| Consumir reserva flash y vaciar carrito | Redis | Después del commit; si falla solo se registra en el log (`orders.py:198`, `:212`). El carrito puede quedar con artículos ya comprados |
| Notificar a vendedores | MySQL | Commit separado del pedido (`orders.py:107`), no atómico con la compra |
| Factura por correo | SMTP | `BackgroundTasks`, mejor esfuerzo; se pierde si el proceso se reinicia |

Riesgos que la Entrega 3 debe abordar:

1. **Sin idempotencia.** Un doble clic o un reintento del navegador tras un
   timeout puede crear dos pedidos.
2. **Pago simulado sin falla posible.** No hay forma de demostrar el manejo de
   una falla parcial del pago.
3. **Escrituras posteriores al commit sin garantía** (Neo4j, Redis).
4. **Proyecciones por delta** que divergen (sección 1).

## 4. Otros problemas de datos detectados

- **Texto mal codificado en MongoDB (6 documentos).** Algunos nombres se
  guardaron con doble codificación UTF-8: por ejemplo
  `Cien aÃ±os de soledad â€” GarcÃ­a MÃ¡rquez` y el SKU `JUG-MUÃ‘-001`. Afecta
  directamente la búsqueda.
  **Corregido en la Fase 2** con `backend/scripts/repair_text_encoding.py`
  (respaldo en `backups/encoding/`): se repararon los 5 nombres. Se dejaron
  intactos, de forma deliberada, el SKU `JUG-MUÃ‘-001` (identificador
  compartido con 2 ofertas de MySQL y 1 variante) y los 43 eventos de
  `producto_eventos` (historial de solo agregado).
- **Neo4j fuera del instalador.** `scripts/setup.ps1` no espera a Neo4j y
  `verify_setup.py` no lo verifica. **Corregido en la Fase 2.**
