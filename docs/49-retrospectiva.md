# Retrospectiva de la arquitectura de TiendaYa

Revisión de las decisiones de arquitectura de las cuatro entregas: cuáles se sostendrían si el proyecto
empezara hoy y cuáles se replantearían. Cada conclusión se apoya en algo que se midió o que falló durante
el proyecto, no en preferencias, y usa los mismos criterios que los registros de decisión: consistencia,
escalabilidad, patrón de consulta y costo operativo.

## Resumen

| Decisión | Entrega | Veredicto |
|---|---|---|
| MySQL como única autoridad de dinero e inventario; los demás motores, proyecciones | 1 | **Se sostiene** |
| MongoDB para el contenido del catálogo (atributos variables por categoría) | 1 | **Se sostiene** |
| Precio y stock copiados también en MongoDB | 1 | **Se replantea** |
| Editar el catálogo en MongoDB y después encolar el evento en MySQL | 1 | **Se replantea** |
| Redis para carritos con expiración y ventas flash con Lua | 2 | **Se sostiene** |
| Neo4j para fraude y «también compraron» | 2 | Se sostiene la elección; **se replantea su sincronización** |
| Cassandra para las tendencias semanales | 2 | **Se replantea el momento** de incorporarla |
| Elasticsearch como proyección de búsqueda | 3 | **Se sostiene** |
| Checkout como saga con idempotencia y recuperación | 3 | **Se sostiene** |
| Outbox transaccional con un consumidor por destino | 3 | **Se sostiene** (en su segunda versión) |
| Plan B con un respaldo para cada motor | 3–4 | **Se replantea su alcance** |
| Vectores en Elasticsearch, sin base vectorial dedicada | Final | **Se sostiene** |
| Control de acceso por servicio | Final | Se sostiene el diseño; **se replantea haberlo dejado al final** |
| Un nodo por motor con memoria mínima | Todas | **Se replantea el dimensionamiento** |

## Decisiones que se sostendrían

### 1. MySQL como única autoridad; el resto, proyecciones reconstruibles

Precio, inventario, pedidos y pagos solo se deciden en MySQL, dentro de transacciones. Los demás motores
guardan copias derivadas que se pueden reconstruir.

- **Consistencia.** Es lo que permitió que el checkout tuviera garantías verificables: los invariantes I1–I7
  (sin sobreventa, cada reserva explicada, ningún pedido vendido sin pago aprobado…) se cumplen al cierre de
  cada fase de esta entrega. Cuando una proyección se equivocó (siete divergencias de stock en
  Elasticsearch, el stock en MongoDB), la corrección fue siempre la misma: volver a proyectar desde MySQL.
- **Costo.** Que las proyecciones sean reconstruibles convierte una caída en un retraso y no en una pérdida
  de datos: con cualquier motor caído, el dinero y el inventario siguen correctos.

### 2. MongoDB para el contenido del catálogo

Una laptop y una camisa no comparten atributos (ADR-001). El catálogo terminó teniendo esquemas de atributos
por categoría, variantes dinámicas y un historial de eventos por producto, que en MySQL habrían sido tablas
EAV o columnas vacías.

- **Patrón de consulta.** Se lee un producto completo con sus variantes en una sola lectura, y el historial
  documental se consulta por producto y fecha con un índice compuesto.
- Lo que se replantea no es MongoDB, sino **lo que se copió dentro de él** (ver «Se replantearían», 1).

### 3. Redis para carritos y ventas flash

- **Patrón de acceso.** Los carritos tienen expiración por inactividad (TTL de 30 minutos), y las reservas de
  una venta flash compiten por unidades limitadas. Redis resuelve lo primero de forma nativa y lo segundo con
  scripts Lua atómicos, sin bloquear filas en MySQL en cada clic.
- **Seguridad.** El control de acceso se aplica incluso dentro de los scripts Lua: no son una puerta trasera
  (fase 9).
- MySQL sigue siendo la fuente durable: si Redis se reinicia, el worker de flash reconstruye su estado.

### 4. Elasticsearch para la búsqueda, y después también para los vectores

- **Patrón de consulta.** La búsqueda anterior con `$regex` acertaba 6 de 17 consultas en el top 3;
  Elasticsearch, 17 de 17 (ADR-003), con errores ortográficos, sinónimos y facetas.
- **Reutilizarlo para los vectores** (ADR-004) fue la decisión con mejor relación costo-beneficio de la
  entrega final: un campo nuevo en un índice que ya existía. La búsqueda híbrida (texto + kNN) se resuelve en
  **una sola consulta** con los mismos filtros y facetas, y subió el MRR de 0.62 a 0.82. Con un millón de
  vectores el kNN responde en ~9 ms. Una base vectorial dedicada habría sumado un motor, un destino de
  outbox y una segunda consulta sin beneficio a esta escala; las condiciones para dar ese paso quedaron
  medidas en el ADR-004.

### 5. Checkout como saga, con idempotencia y recuperación

El cobro ocurre en un sistema externo que no participa en transacciones de MySQL.

- **Consistencia.** Reservar (T1), cobrar fuera de toda transacción y confirmar o compensar (T2), con la misma
  clave de idempotencia en cada reintento, más un reconciliador para los resultados desconocidos, es lo que
  permitió demostrar los escenarios de falla E00–E17 sin dinero ni inventario perdidos.
- Se sostendría sin cambios.

### 6. Outbox transaccional con un consumidor por destino

Se sostiene **en su segunda versión**, y la primera es la mejor lección del proyecto:

- **Primera versión: una sola cola, y eventos con el cambio.** El checkout publicaba «el stock de la oferta
  vendida» y MongoDB lo copiaba encima del **total** de todas las ofertas. Resultado medido en la línea base
  de la Entrega 3: la Dell Inspiron quedó con stock 9 en MongoDB y 16 en MySQL. Además, un destino caído
  retrasaba a todos.
- **Segunda versión: una fila y un consumidor por destino**, y los manejadores **recalculan** la proyección
  desde el estado actual de MySQL en lugar de aplicar el cambio del evento. Así son idempotentes, no
  dependen del orden y un destino caído no frena a los demás.
- **Lección:** una proyección debe derivarse del estado, nunca acumular deltas.

### 7. Neo4j para fraude y «también compraron»

- **Patrón de consulta.** Las reglas de fraude recorren varios saltos (cuenta → compras → vendedor → reseñas
  de otras cuentas) y en MySQL eran auto-JOIN repetidos (documento 26). «Quien compró esto también compró»
  es un recorrido de dos saltos.
- Se sostiene el motor; lo que se replantea es cómo se mantiene sincronizado (ver abajo, 3).

### 8. Control de acceso por servicio y secretos fuera del repositorio

El diseño de la fase 9 a la 12 (un usuario por servicio con mínimo privilegio, reglas versionadas,
contraseñas generadas) se sostiene. Validarlo corriendo toda la suite con los usuarios restringidos y
revisando los rechazos de cada motor fue lo que encontró permisos faltantes que el plan B escondía. Lo que se
replantea es **cuándo** se hizo (abajo, 5).

## Decisiones que se replantearían

### 1. Copiar precio y stock dentro de MongoDB

**Decisión original** (ADR-002): MongoDB guarda, además del contenido, una proyección de precio, stock y
vendedor de la oferta principal.

**Qué pasó.** El mismo dato terminó en cuatro lugares: MySQL (autoridad), MongoDB, Elasticsearch y la copia
del catálogo en MySQL del plan B. Cada copia necesitó su manejador de outbox, su reconciliación y su
invariante (I7), y la falla más visible de la Entrega 3 (stock 9 frente a 16) ocurrió justamente en esa
copia.

**Qué se haría.** MongoDB solo con contenido (nombre, atributos, variantes, imágenes, historial). Precio y
stock solo en MySQL y en Elasticsearch, que sí los necesita para filtrar y ordenar; toda pantalla hidrata
desde MySQL, como ya hace la búsqueda.

- **Consistencia:** una copia menos que puede divergir.
- **Costo:** un destino de outbox menos y menos reconciliación.

### 2. Escribir el catálogo en MongoDB y después encolar el evento en MySQL

**Decisión original:** una edición de catálogo se guarda primero en MongoDB y después se encola su evento en el
outbox de MySQL. Es una escritura doble: si el proceso cae entre ambos pasos, la búsqueda queda desactualizada
hasta la reconciliación de cada 10 minutos (riesgo aceptado en el documento 30).

**Qué se haría.** Que una sola transacción decida: registrar la intención en el outbox de MySQL junto con la
edición y que el consumidor `mongo` la aplique (MongoDB queda como proyección también del contenido), o
escuchar los *change streams* de MongoDB.

- **Consistencia:** desaparece la ventana de 10 minutos.
- **Costo:** la reconciliación periódica queda como red de seguridad, no como mecanismo principal.

### 3. Sincronización de Neo4j sin reconciliación propia

**Qué pasó.** `verify_setup.py` reporta durante toda la Entrega 4 la misma divergencia: 192 compras en MySQL y
175 en el grafo. Elasticsearch tiene una reconciliación cada 10 minutos que detecta y corrige lo desfasado;
Neo4j no tiene equivalente, así que una compra que no llegó por el outbox no llega nunca.

**Qué se haría.** La misma reconciliación que tiene Elasticsearch: comparar periódicamente MySQL con el grafo
y volver a proyectar lo que falte.

- **Consistencia:** convergencia garantizada, no solo «normalmente».

### 4. Cassandra desde la Entrega 2

**Decisión original:** Cassandra para las tendencias de venta por semana, con tablas desnormalizadas por
consulta.

**Qué pasó.** El modelo es correcto para series de tiempo con escritura masiva, pero con el volumen del
proyecto (cientos de pedidos) las mismas consultas caben en tablas resumen de MySQL alimentadas por el mismo
outbox. Cassandra fue el contenedor más pesado después de Elasticsearch (~1 GB de RAM) y quedó sin respaldo
en el plan B y sin control de acceso.

**Qué se haría.** Empezar con tablas resumen en MySQL e incorporar Cassandra cuando el volumen lo pida, con un
umbral medido (por ejemplo, cuando las escrituras de eventos de venta o el tamaño de las tablas resumen
degraden las transacciones de MySQL).

- **Costo:** se usó un motor antes de necesitarlo.
- **Escalabilidad:** la decisión era correcta para el crecimiento, no para el presente.

### 5. Seguridad al final del proyecto

**Qué pasó.** Las contraseñas estuvieron fijas en el repositorio desde la Entrega 1 (`.env.example`,
valores por defecto de `config.py` y 19 scripts) y el backend se conectaba a MongoDB como root. Activar el
control de acceso en la entrega final obligó a:

- adoptar las contraseñas antiguas, porque los volúmenes ya existían con ellas;
- tocar decenas de archivos;
- resolver un incidente: al quitar el valor por defecto de Neo4j se generó una contraseña nueva que no
  coincidía con la base, y hubo que hacer que el script adoptara la del contenedor ya creado.

**Qué se haría.** Usuarios por servicio y contraseñas generadas desde el primer día. El costo inicial es
mínimo; agregarlo al final cuesta mucho más.

### 6. Plan B con un respaldo para cada motor

**Decisión original:** cuando cualquier motor cae, la tienda sigue funcionando con otro que tiene una copia
(carrito en MySQL, catálogo en MySQL, recomendaciones en caché, copias de lectura en Redis, cola de pedidos).

**Qué pasó.**
- **Disponibilidad:** funcionó, y se demostró con fallas inyectadas.
- **Complejidad:** sumó tres migraciones, un destino de outbox y varios servicios.
- **Errores escondidos:** un permiso faltante (`ZRANGEBYLEX` en Redis) no hizo fallar ninguna prueba,
  porque el respaldo tomó el control en silencio. Solo apareció revisando el registro de rechazos de Redis.

**Qué se haría.** Mantener el respaldo donde el negocio lo exige (carrito, checkout y búsqueda) y, para el
resto, preferir mostrar un error claro. Además, todo modo degradado debe dejar una señal que alguien mire (una
métrica o alerta), no solo un aviso en pantalla.

- **Costo operativo:** menos código que mantener.
- **Consistencia:** las fallas se ven en lugar de taparse.

### 7. Un nodo por motor con la memoria mínima

**Qué pasó.** Con 512 MB de heap, Elasticsearch rechazó cargas grandes (límite de ~51 MB de escrituras en
curso) y se cayó por falta de memoria al fusionar un millón de vectores (fase 7). Las reindexaciones dejaron
245 versiones borradas frente a unos 66 productos vivos, y el kNN llegó a devolver cero resultados hasta que se agregó una
purga (fase 6).

**Qué se haría.** Dimensionar cada motor desde el principio según el uso medido y no según lo mínimo para
arrancar. Para Elasticsearch, eso significa al menos 1–2 GB de heap si va a manejar vectores, y la purga y las
fusiones como parte de la operación desde que se crea el índice. La arquitectura no cambia; cambia cuánto se
le da a cada pieza.

## Lecciones de proceso

- **Medir antes de decidir.** Las decisiones que mejor se sostienen (Elasticsearch, la búsqueda híbrida, el
  umbral semántico, los permisos) tienen una línea base o una evaluación detrás. Las que se replantean son, en
  su mayoría, las que se tomaron sin medir el costo de mantenerlas.
- **Regresión completa en cada cambio.** Tres pruebas del checkout y de bodegas quedaron fallando tras un
  cambio de inventario y siguieron así toda la Entrega 4. Una integración que no corre la suite completa
  acumula deuda que después nadie reconoce como propia.
- **Datos de prueba fuera del entorno principal.** Productos de prueba creados a mano («CER», «Gadieles»)
  terminaron en el índice y empeoraron la evaluación de los vectores (el vecino más cercano de una laptop era
  «CER»). Hace falta un entorno separado para probar a mano.
- **Evidencia automática.** Los scripts que generan evidencia (`demo_fallas.py`, `evaluar_vectores.py`,
  `benchmark_vectores.py`, `verificar_permisos.py`) se pueden volver a correr para comprobar que lo afirmado
  sigue siendo cierto. Una evidencia que no se puede regenerar envejece sin que nadie lo note.

## Si el proyecto empezara hoy

Los mismos motores para los mismos problemas, con cuatro cambios:
- MongoDB solo con contenido;
- toda escritura decidida por una transacción de MySQL con su outbox;
- Cassandra hasta que el volumen la pida;
- control de acceso y contraseñas generadas desde el primer commit.

La regla que más valor dio, y que se mantendría por encima de todo: **una sola autoridad por dato, y todo lo
demás, proyecciones que se pueden reconstruir.**
