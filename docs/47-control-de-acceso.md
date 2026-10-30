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

## Instalación y equipos existentes

`scripts/setup.ps1` llama a `configurar-acceso.ps1` antes de instalar. En un equipo que ya tenía el proyecto,
después de actualizar el repositorio basta con:

```powershell
.\scripts\configurar-acceso.ps1
```

Ese script, idempotente:
1. genera las contraseñas que falten en `.env` y `backend\.env` (`generar-credenciales.ps1`);
2. recrea los contenedores para que las tomen (`docker compose up -d`);
3. crea o actualiza los usuarios de MongoDB.

Los datos no se pierden (volúmenes de Docker). Sin las contraseñas, Redis no arranca y su registro explica qué
ejecutar; MongoDB arranca, pero el backend no puede conectarse hasta que existan sus usuarios.
