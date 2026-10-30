# Control de acceso a los componentes NoSQL (Entrega final)

El enunciado pide autenticación y autorización configuradas explícitamente en al menos un componente NoSQL,
«con roles y permisos acotados según el servicio que los utiliza», y evidencia de que un usuario sin permisos
no puede salirse de su alcance. Este documento describe cada componente; la decisión y su justificación
quedan en el ADR-005.

## Principios

- **Un usuario por servicio**, con solo lo que ese servicio usa (mínimo privilegio). El backend nunca usa
  la cuenta de administración.
- **Reglas en el repositorio, contraseñas fuera.** Los permisos son código revisable; las contraseñas se
  generan al azar en cada equipo (`scripts/generar-credenciales.ps1`) y viven en `.env` y `backend/.env`,
  que git ignora.
- **Sin modo abierto.** Si falta una contraseña, el componente no arranca (no hay un «modo sin
  autenticación» al que caer en silencio).
- **Evidencia automática**: pruebas que intentan lo prohibido y esperan el rechazo.

## Redis

Reglas: `database/redis/acl.conf`. Al arrancar el contenedor, `database/redis/iniciar-redis.sh` agrega a
cada usuario la contraseña de su variable de entorno y levanta Redis con `--aclfile`.

| Usuario | Lo usa | Llaves | Comandos |
|---|---|---|---|
| `tiendaya_api` | Backend (API y sus workers) | Solo sus 9 prefijos: `carrito:*`, `flash:*`, `autocompletar:*`, `cola_pedidos:*`, `respaldo:lectura:*`, `similares:*`, `vector_consulta:*`, `para_ti:*`, `vistos:*` | Lista cerrada de 34 comandos: los que usa el código, incluidos los de los scripts Lua de las ventas flash. Sin `KEYS`, `FLUSHALL`, `CONFIG`, `ACL`, `INFO`, `MONITOR`, `SAVE` ni `SHUTDOWN` |
| `tiendaya_lectura` | Diagnóstico, healthcheck | Todas | Solo lectura (`+@read`), sin `KEYS` |
| `default` (solo contraseña) | Redis Commander (su imagen no admite usuario) | Todas | Igual que `tiendaya_lectura`; además Commander corre en modo `READ_ONLY` |
| `tiendaya_admin` | Operación (revisar o cambiar permisos) | Todas | Todos |

**Cómo se obtuvo la lista de comandos del backend.** Se hizo un inventario de los métodos de Redis que usa
el código y de los comandos dentro de los scripts Lua. Después se corrieron las 368 pruebas del backend con el
usuario restringido y se revisó el `ACL LOG` de Redis: los respaldos de la aplicación (plan B) pueden esconder
un permiso faltante, porque si Redis rechaza un comando el carrito pasa a MySQL sin que una prueba falle. Así
apareció `ZRANGEBYLEX` (autocompletado de respaldo), que el primer inventario no tenía. Con la lista final,
el `ACL LOG` no muestra ninguna negación que no sea de las pruebas de permisos.

**El ACL también se aplica dentro de Lua.** Un script que intenta escribir una llave fuera de los prefijos
falla con `ACL failure in script`, así que las ventas flash no son una puerta trasera.

### Evidencia (`backend/tests/test_permisos_redis.py`, 21 pruebas)

| Intento | Resultado |
|---|---|
| Conectarse sin credenciales | `NOAUTH Authentication required` |
| Contraseña incorrecta | `WRONGPASS invalid username-password pair` |
| Backend lee y escribe `carrito:*` y `flash:*` | Permitido |
| Backend escribe o lee `otra:cosa`, `usuarios:1`, `sesion:admin` | `NOPERM No permissions to access a key` |
| Backend ejecuta `FLUSHALL`, `FLUSHDB`, `KEYS *`, `CONFIG GET`, `ACL LIST`, `SAVE`, `SHUTDOWN`, `INFO`, `CLIENT LIST`, `MONITOR` | `NOPERM ... has no permissions to run the '...' command` |
| Backend ejecuta Lua que escribe `otra:cosa` | `ACL failure in script` |
| Lectura hace `SET`, `DEL`, `EXPIRE`, `FLUSHDB`, `KEYS` | `NOPERM` (y la llave queda intacta) |
| Solo contraseña (como Redis Commander) lee / escribe | Lee / `NOPERM` |
| Admin lista los usuarios y sus reglas | Permitido |

## MongoDB

Rol y usuarios: `database/mongo/03_usuarios.js` (idempotente). Docker lo ejecuta al crear el volumen; en una
base que ya existía lo ejecuta `scripts/configurar-acceso.ps1`. Las contraseñas llegan al contenedor por
variables de entorno desde el `.env` de la raíz.

| Usuario | Lo usa | Rol | Puede |
|---|---|---|---|
| `tiendaya_api` | Backend (API y workers) | `tiendaya_aplicacion` (a medida) | Solo sobre sus 5 colecciones (`productos`, `producto_variantes`, `producto_eventos`, `categoria_esquemas`, `tiendas_config`): `find`, `insert`, `update`, `remove`, `createIndex` (crea sus índices al arrancar) y `listIndexes`. Sin `drop`, sin crear colecciones, sin listar la base, sin `migraciones`, sin usuarios ni roles, sin otras bases |
| `tiendaya_lectura` | Mongo Express, diagnóstico | `read` sobre `tiendaya` | Leer |
| `tiendaya_admin` | Instalación y migraciones (`setup.ps1`) | `dbOwner` sobre `tiendaya` | Todo dentro de `tiendaya`; nada en `admin` ni en otras bases |
| `admin` (root) | Solo para crear los usuarios anteriores | `root` | — |

**Instalación con el usuario correcto.** Las migraciones de `setup.ps1` crean y modifican colecciones: el
script les pasa la conexión de `tiendaya_admin` solo por variable de entorno del proceso y la quita antes de
`verify_setup.py`, que corre con el usuario del backend. `backend/.env` nunca guarda la cuenta de
administración.

**Validación.** Igual que en Redis, el plan B podía esconder un permiso faltante (si Mongo rechaza, el
catálogo sale de su copia en MySQL). Durante las 383 pruebas del backend se activó el registro de control de
acceso de MongoDB (`setLogLevel(1, 'accessControl')`): todos los rechazos registrados son los que provocan a
propósito las pruebas de permisos; la aplicación no tuvo ninguno.

### Evidencia (`backend/tests/test_permisos_mongo.py`, 15 pruebas)

| Intento | Resultado |
|---|---|
| Leer sin credenciales | `requires authentication` |
| Contraseña incorrecta | `Authentication failed` |
| Backend inserta, actualiza, lee y borra en `producto_eventos`; cuenta productos; lee índices | Permitido |
| Privilegios del backend según MongoDB (`connectionStatus`) | Solo sus 5 colecciones y solo esas 6 acciones; nada sobre el servidor ni otras bases |
| Backend lee `migraciones`, inserta en una colección nueva, lista las colecciones | `not authorized` |
| Backend lee `admin.system.users` o la base `tiendaya_demo`; borra una base | `not authorized` |
| Backend crea un usuario `root` o se asigna `dbOwner` | `not authorized` |
| Lectura inserta, actualiza, borra o crea un índice | `not authorized` |
| Admin crea y borra una colección en `tiendaya` / lee `admin` u otra base | Permitido / `not authorized` |

`drop` sobre colecciones reales no se intenta en las pruebas: si el rol estuviera mal configurado, borraría
datos. En su lugar se comprueba que el usuario no tenga esa acción.

## Elasticsearch

Seguridad activada (`xpack.security.enabled`) en el nodo único. Roles y usuarios sin contraseñas en
`database/elasticsearch/seguridad.json`; `scripts/configurar-acceso.ps1` los crea o actualiza con el
superusuario `elastic` (cuya contraseña inicial toma Elasticsearch de `ELASTIC_PASSWORD`).

| Usuario | Lo usa | Rol | Puede |
|---|---|---|---|
| `tiendaya_api` | Backend | `tiendaya_busqueda` | Sobre `productos*`: buscar y leer, escribir documentos (`write`), ver mappings y alias, estadísticas y mantenimiento (`refresh`, `forcemerge` de la purga de borrados). Del clúster, solo `monitor`. **No** puede crear ni borrar índices, cambiar alias ni ajustes, ni ver otros índices |
| `tiendaya_indexador` | Instalación, `reindex_search.py --recrear`, benchmark | `tiendaya_indexacion` | Todo sobre `productos*` y `bench_vectores_*`; nada más |
| `tiendaya_lectura` | Elasticvue (:8083), diagnóstico | `tiendaya_consulta` | Solo leer `productos*` |
| `elastic` | Configurar roles y usuarios; healthcheck del contenedor | `superuser` | Todo |

**Por qué el backend no crea índices.** Crear un índice nuevo y mover el alias solo ocurre al migrar el mapping
o reindexar todo (`reindex_search.py --recrear`), que es una tarea de instalación. El botón «Reindexar» del
panel de administración solo reescribe documentos. Así, un fallo o una intrusión en el backend no puede borrar
el índice ni apuntar el alias a otro lado. `setup.ps1` corre la instalación con el indexador (solo por variable
de entorno del proceso); si alguien ejecuta `--recrear` con el usuario del backend, el script lo rechaza y
explica qué usuario usar.

**Elasticvue** corre en el navegador: su configuración (con la contraseña) la puede ver quien abra :8083. Por
eso usa el usuario que solo lee.

**Sin TLS en desarrollo.** El nodo es único y la red es local, así que HTTP va sin cifrar
(`xpack.security.http.ssl.enabled: false`) y las contraseñas viajan en Basic Auth sin cifrar. En producción se
activaría TLS en HTTP; el resto de la configuración no cambia.

**Validación.** Elasticsearch no tiene registro de auditoría en la licencia básica. Para detectar permisos
faltantes que el plan B pudiera esconder (si la búsqueda falla, sale de MongoDB), las 397 pruebas del backend
se corrieron mostrando todas las advertencias del backend: no hubo ningún `security_exception` ni `401` fuera
de las pruebas de permisos. Las pruebas que crean índices temporales (`productos_test_*`) usan el indexador
(fixture `es_indexador`).

### Evidencia (`backend/tests/test_permisos_elasticsearch.py`, 14 pruebas)

| Intento | Resultado |
|---|---|
| Consultar sin credenciales / con contraseña incorrecta | `401 AuthenticationException` |
| Backend busca, indexa, edita y borra un documento; lee el mapping y las estadísticas | Permitido |
| Privilegios del backend sobre el índice (`has_privileges`) | `read`, `write`, `maintenance`: sí. `delete_index`, `create_index`, `manage`, `all`: no |
| Backend crea un índice, agrega un alias, cambia ajustes del índice | `403 security_exception` |
| Backend lee `.security-7`, cambia ajustes del clúster, crea un superusuario o lista usuarios | `403 security_exception` |
| Backend busca en `.security*` (comodín) | 0 resultados en 0 shards: Elasticsearch descarta lo no autorizado |
| Lectura busca / indexa o borra | Permitido / `403` |
| Indexador crea y borra `productos_test_*` / crea otro índice o lista usuarios | Permitido / `403` |

Borrar el índice real no se intenta: `has_privileges` confirma que el backend no tiene `delete_index`.

## Instalación y equipos existentes

`scripts/setup.ps1` llama a `configurar-acceso.ps1` antes de instalar. En un equipo que ya tenía el proyecto,
después de actualizar el repositorio basta con:

```powershell
.\scripts\configurar-acceso.ps1
```

Ese script, idempotente:
1. genera las contraseñas que falten en `.env` y `backend\.env` (`generar-credenciales.ps1`);
2. recrea los contenedores para que las tomen (`docker compose up -d`);
3. crea o actualiza los usuarios de MongoDB;
4. crea o actualiza los roles y usuarios de Elasticsearch.

Los datos no se pierden (volúmenes de Docker). Sin las contraseñas, Redis no arranca y su registro explica qué
ejecutar; MongoDB y Elasticsearch arrancan, pero el backend no puede conectarse hasta que existan sus
usuarios.
