# Plan B entre bases de datos: qué hace la tienda cuando se cae un motor

Rama `plan-b` (desde `final-entrega3`). Este documento explica qué hace TiendaYa
cuando se cae cada base de datos, por qué se resolvió así, qué no se puede
hacer y cómo probarlo. **Cassandra no se tocó**: su plan B (vista SQL en MySQL)
queda a cargo de otro integrante del equipo.

## 1. Idea general

Cuando un motor no responde, otro que ya tiene (o puede tener) una copia de sus
datos toma su lugar. La respuesta dice que se usó el respaldo y la tienda lo
avisa al usuario. Cuando el motor vuelve, todo se sincroniza solo.

> **Regla que no se rompe:** el dinero y el inventario solo se deciden en
> MySQL. Ningún respaldo aprueba pagos ni descuenta stock.

| Motor caído | Respaldo | Qué ve el usuario | Al volver |
|---|---|---|---|
| Redis | Carrito copiado en MySQL; reservas flash con `FOR UPDATE` en MySQL | Compra normal, un poco más lenta | El carrito se reconstruye en Redis desde MySQL; el worker flash rehidrata las promociones |
| MongoDB | Copia completa del catálogo en MySQL; Elasticsearch si un producto aún no se copió | Catálogo posiblemente desactualizado; no se pueden editar productos | El outbox y la reconciliación ponen la copia al día |
| Elasticsearch | MongoDB (ya existía) → copia en MySQL; autocompletado desde Redis | Búsqueda sin tolerancia a errores ni facetas | Avisos del outbox y reconciliación |
| Neo4j | Caché horaria de recomendaciones en MySQL → más vendidos de la categoría | Recomendaciones del último cálculo; F01–F03 «pendientes» | La caché se recalcula; el análisis de fraude se reintenta a los 5 min |
| MySQL | Modo de solo lectura: sesión por JWT, copias de lectura en Redis, precios proyectados; pedidos en cola | Puede navegar y dejar su pedido en cola; no se cobra nada | Un worker pasa cada pedido en cola por la saga normal |
| Cassandra | — (pendiente, otro integrante) | Paneles de tendencias no disponibles | — |

## 2. Base común: detector de fallas y aviso

**Archivo:** `backend/app/core/salud.py` (circuit breaker por motor).

- Tras 3 fallas seguidas, el circuito de ese motor se **abre** 15 s y quien
  tenga respaldo lo usa sin esperar el timeout en cada petición. Pasado ese
  tiempo se deja pasar un intento: si responde, se cierra.
- Un «servidor inalcanzable» (Redis sin conexión, Mongo sin servidor, Neo4j o
  MySQL rechazando la conexión) abre el circuito de una vez: solo la primera
  petición espera el timeout. Medido: 3.2 s la primera, ~30 ms las siguientes.
- `GET /api/v1/salud/motores` hace ping a los seis motores en paralelo (3 s
  máximo, resultado reutilizado 5 s) y responde `ok`, `degradado` o `caido`.
  Es público y no expone errores internos.
- Los manejadores de errores de infraestructura (`core/errores.py`) también
  alimentan el detector.
- Frontend: `components/layout/AvisoServicios.jsx` muestra un aviso bajo la
  cabecera, con un mensaje por motor caído. Se refresca cada 30 s y al
  instante cuando cualquier petición recibe un 503.

**Por qué:** sin detector, con un motor caído cada petición esperaría su
timeout (2–3 s) antes de usar el respaldo. Abrirlo de una vez cuando el
servidor ni siquiera acepta conexiones evita que el usuario note la espera.

## 3. Redis → MySQL (carrito y ventas flash)

**Archivos:** `services/redis_cart_service.py`, `services/carrito_respaldo_service.py`,
`services/flash_sale_service.py`, `services/flash_sale_worker.py`,
`api/v1/flash_sales.py`, `api/v1/cart.py`, `api/v1/orders.py`,
`database/mysql/24_respaldo_redis.sql`.

**Carrito**
- Cada cambio exitoso en Redis se copia en MySQL (`carritos_respaldo` y
  `carritos_respaldo_items`, con el mismo JSON del HASH). La copia lee Redis
  **con la fila del carrito bloqueada**, así una foto vieja nunca pisa a una nueva.
- Si Redis no responde, la misma operación se hace en MySQL con la fila
  bloqueada (los incrementos simultáneos no se pierden) y el carrito queda
  `pendiente_redis = 1`. Antes de la siguiente operación con Redis de vuelta,
  el carrito se reconstruye en Redis desde MySQL.
- `confirmar_pedido` retira lo comprado de la copia **en su misma
  transacción**: lo comprado no reaparece aunque Redis esté caído.
- Si también falla MySQL se lanza `CarritoNoDisponible` (un `RedisError`) y se
  responde 503 como antes.

**Ventas flash**
- MySQL ya guarda el estado durable (unidades totales, vendidas y cada reserva).
  Sin Redis, la reserva se resuelve en MySQL bloqueando la fila de la promoción
  (`reservar_en_mysql`, mismos códigos que el script Lua). Más lento, igual de
  correcto: 10 compradores por 3 unidades reservan exactamente 3.
- La promoción se anota en `flash_resincronizar`; el worker borra su estado en
  Redis y lo rehidrata desde MySQL cuando Redis vuelve.

**Por qué así:** el carrito es lo que impide comprar si Redis cae. Escribir en
los dos lados (write-through) cuesta una escritura extra por cambio, pero el
respaldo siempre está al día. La marca `pendiente_redis` decide quién tiene la
versión más nueva sin comparar relojes.

## 4. MongoDB → copia en MySQL → Elasticsearch (catálogo)

**Archivos:** `services/catalogo_respaldo_service.py`, `services/catalog_service.py`,
`services/variant_service.py`, `services/search_service.py`,
`services/recommendation_service.py`, `services/checkout_service.py`,
`services/outbox_service.py`, `scripts/sync_catalogo_respaldo.py`,
`database/mysql/25_respaldo_catalogo.sql`.

- `catalogo_respaldo` guarda cada documento de `productos` y
  `producto_variantes` **completo** (JSON extendido de BSON: conserva ObjectId
  y fechas).
- Se mantiene con un nuevo destino del outbox, `catalogo` (las ediciones del
  catálogo ahora van a `busqueda` y a `catalogo`), recalculado desde MongoDB
  (idempotente), y con una reconciliación al arrancar y cada 10 min (documentos
  nuevos, editados o eliminados).
- Si MongoDB no responde, leen la copia el listado, el detalle (con ofertas y
  variantes), la hidratación de la búsqueda, las recomendaciones, el nombre en
  el carrito y el nombre que queda en cada línea del pedido. Un producto que
  aún no se copió sale de Elasticsearch, que tiene una versión resumida.
- Precio y stock siguen saliendo de MySQL.

**Por qué la copia en MySQL va antes que Elasticsearch:** la copia tiene el
documento completo (todas las imágenes, atributos y variantes);
Elasticsearch solo una versión resumida para buscar.

**Qué no se puede hacer: editar productos.** MongoDB es la autoridad del
contenido del catálogo y la copia va en una sola dirección:
1. Editar la copia crearía dos versiones del mismo producto y la reconciliación
   pisaría la edición con la versión de MongoDB al volver.
2. Cada edición registra un evento en el historial del producto (Entrega 1);
   sin MongoDB la reconstrucción por fecha dejaría de ser confiable.
3. Las validaciones (esquema de atributos por categoría, SKU único, variantes)
   viven en MongoDB.

Editar es poco frecuente y quien lo hace puede esperar; se prefiere esperar a
arriesgar una inconsistencia silenciosa. Si algún día hiciera falta, la
alternativa sería encolar ediciones como se encolan los pedidos.

## 5. Elasticsearch → MongoDB → MySQL; autocompletado en Redis

**Archivos:** `services/search_service.py`, `services/autocompletado_respaldo_service.py`.

- Búsqueda: Elasticsearch → MongoDB (ya existía) → copia del catálogo en MySQL.
  La respuesta dice qué motor contestó (`motor`). Un texto sin coincidencias
  sigue mostrando productos populares.
- Autocompletado: Elasticsearch → índice de prefijos en Redis → MongoDB → MySQL.
  El índice es un ZSET con puntaje 0 (orden alfabético) consultado con
  `ZRANGEBYLEX`; cada producto se indexa con su nombre y sus sufijos desde cada
  palabra y sin tildes, como el completion suggester («galax» → Samsung Galaxy,
  «audif» → Audífonos). Se reconstruye desde la copia del catálogo al arrancar y
  cada 10 min (en claves temporales que luego se renombran) y se actualiza por
  producto con el destino `catalogo` del outbox.

**Por qué:** Redis responde prefijos en milisegundos y ya está en la
arquitectura; buscar con `$regex` o `LIKE` en cada tecla sería más lento.

**Qué se pierde sin Elasticsearch:** tolerancia a errores ortográficos,
sinónimos, relevancia y facetas por atributo.

## 6. Neo4j → caché en MySQL → más vendidos

**Archivos:** `services/recommendation_service.py`, `services/outbox_service.py`,
`api/v1/products.py`, `core/deps.py` (`get_neo4j_opcional`), `api/v1/reviews.py`,
`services/fraud_analysis_service.py`, `services/fraud_analysis_worker.py`,
`database/mysql/26_recomendaciones_cache.sql`.

- El consumidor `neo4j` del outbox copia cada hora (y al arrancar) el recorrido
  de co-compra de todos los productos a `recomendaciones_cache` (30 candidatos
  por producto; la tabla se reemplaza en una transacción).
- Sin Neo4j, las recomendaciones salen de la caché (mismo filtro de categoría,
  sin lo que el usuario ya compró) y, si el producto no tiene caché, de los más
  vendidos de su categoría según MySQL. La respuesta trae `origen` (`grafo`,
  `cache` o `mas_vendidos`) y la página del producto ajusta el título.
- Fraude: el resumen del panel ya no responde 503; F01–F03 aparecen
  «Pendiente» y F04 y los expedientes F05–F07 se muestran desde MySQL. Un
  análisis que falla porque Neo4j no responde queda registrado como pendiente
  (los expedientes conservan su vigencia) y se reintenta a los 5 min.
  **Las reglas F01–F07 no cambiaron.**
- Además, las recomendaciones ahora solo muestran productos **de la misma
  categoría principal** que el producto (el catálogo da las referencias
  permitidas y la consulta del grafo se limita a ellas).

**Por qué no se reescriben F01–F03 en SQL:** son consultas de varios saltos,
justamente la razón de usar un grafo. Duplicarlas en SQL solo para el caso de
falla duplicaría la lógica; dejarlas pendientes unos minutos no afecta a nadie.

## 7. MySQL → modo de solo lectura y pedidos en cola

**Archivos:** `core/deps.py` (`UsuarioToken`), `services/lectura_respaldo_service.py`,
`services/cola_pedidos_service.py`, `services/catalog_service.py`,
`api/v1/auth.py`, `api/v1/addresses.py`, `api/v1/categories.py`,
`api/v1/cart.py`, `api/v1/orders.py`, `main.py`, frontend `AuthContext.jsx`,
`CheckoutPage.jsx`, `OrdersPage.jsx`.

MySQL es la autoridad y no se reemplaza; sin él la tienda funciona a medias:

- **Sesión:** el JWT firmado identifica al usuario (`UsuarioToken`, sin roles:
  lo de vendedor y administrador queda fuera). El frontend ya no borra la
  sesión por un error que no sea 401.
- **Copias de lectura en Redis:** perfil, direcciones y categorías se guardan en
  cada lectura exitosa y se sirven si MySQL no responde.
- **Catálogo:** precio y stock proyectados en el catálogo, marcados
  `precio_referencial`; el detalle muestra solo la oferta principal.
- **Carrito:** se ve y se agrega con el precio que el usuario vio.
- **Checkout:** sin MySQL no se reserva ni se cobra. Se guarda una solicitud
  de pedido en Redis y se responde `202 ORDER_QUEUED` (idempotente con la misma
  clave, una solicitud en cola por usuario, sin ofertas flash).
  `GET /orders/cola` las lista.
- **Al volver MySQL:** `cola_pedidos_service` pasa cada solicitud por la saga
  normal (revalida precio y existencia, reserva, cobra y confirma) con su propia
  clave de idempotencia. Si el precio cambió, no hay stock o el pago se rechaza,
  queda «requiere atención» y **no se cobra nada distinto** de lo que el usuario
  vio. En ambos casos se le notifica.

**Qué no se puede hacer sin MySQL:** registrarse, iniciar sesión de nuevo,
editar perfil o direcciones, ver el historial de pedidos y todo lo de
vendedores y administración.

**Por qué así:** cobrar sin MySQL arriesgaría cobros sin pedido o pedidos sin
stock. Encolar la intención y pasarla por la misma saga reutiliza todas las
garantías de la Entrega 3 (idempotencia, compensaciones, invariantes). La
solución de fondo para producción es una réplica de MySQL que se pueda promover.

## 8. Migraciones y scripts

| Migración / script | Contenido |
|---|---|
| `24_respaldo_redis.sql` / `apply_respaldo_redis.py` | `carritos_respaldo`, `carritos_respaldo_items`, `flash_resincronizar` |
| `25_respaldo_catalogo.sql` / `apply_respaldo_catalogo.py` | `catalogo_respaldo` y destino `catalogo` del outbox |
| `26_recomendaciones_cache.sql` / `apply_recomendaciones_cache.py` | `recomendaciones_cache` |
| `sync_catalogo_respaldo.py` | Llena la copia del catálogo y el autocompletado de Redis (idempotente) |

`scripts/setup.ps1` los aplica. Todas son aditivas e idempotentes.

## 9. Cómo probarlo

**Pruebas automatizadas** (desde `backend/`, con los motores principales arriba):

```powershell
.\venv\Scripts\python.exe -m pytest tests\test_salud.py tests\test_respaldo_redis.py tests\test_respaldo_mongo.py tests\test_respaldo_elasticsearch.py tests\test_respaldo_neo4j.py tests\test_respaldo_mysql.py tests\test_recomendaciones_categoria.py -v
```

**Escenarios contra el sistema real** (API en :8000, pasarela en :8001,
`FAULT_INJECTION_ENABLED=true`): `scripts\demo_fallas.py E09 E14 E15 E16 E17`
escribe la evidencia en `docs/evidencia/fallas/`.

**A mano** (tienda en :5173):

| Prueba | Comandos y qué observar |
|---|---|
| Redis | `docker stop tiendaya_redis` → agregar al carrito y comprar funciona; aviso amarillo. `docker start tiendaya_redis` → el carrito sigue igual. |
| MongoDB | `docker stop tiendaya_mongo` → el catálogo y el detalle se ven (desde la copia); editar un producto responde 503. |
| Elasticsearch + MongoDB | Detener ambos → buscar «laptop» responde `motor: mysql`; el autocompletado responde `motor: redis`. |
| Neo4j | `docker stop tiendaya_neo4j` → las recomendaciones de una laptop siguen (origen `cache`); el panel de fraude muestra F01–F03 «Pendiente». |
| MySQL | `docker stop tiendaya_mysql` → con la sesión ya abierta se navega; al pagar «tu pedido quedó en cola». `docker start tiendaya_mysql` → en segundos el pedido aparece confirmado en «Mis pedidos». |
| Estado | `GET http://localhost:8000/api/v1/salud/motores` |
