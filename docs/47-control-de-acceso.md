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

### Instalación y equipos existentes

`scripts/setup.ps1` llama a `generar-credenciales.ps1` antes de `docker compose up`. En un equipo que ya
tenía el proyecto instalado, después de actualizar el repositorio:

```powershell
.\scripts\generar-credenciales.ps1   # crea las contraseñas que falten en .env y backend\.env
docker compose up -d                 # recrea Redis con el control de acceso
```

Los datos de Redis no se pierden (volumen `redis_data`). Sin las contraseñas, el contenedor de Redis no
arranca y su registro explica qué ejecutar.
