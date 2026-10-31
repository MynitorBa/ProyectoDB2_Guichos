# Evidencia del control de acceso

Generado por `backend/scripts/verificar_permisos.py` el 2026-10-30 19:15 contra el sistema en marcha. Cada fila es un intento real con el usuario indicado. Lo que borraría datos (borrar el índice o colecciones de la tienda) no se ejecuta: se pregunta al motor si el usuario tendría ese privilegio.

**Resultado: 40 de 40 intentos dieron lo esperado.**

| Componente | Usuario | Intento | Esperado | Obtenido | Respuesta del motor |
|---|---|---|---|---|---|
| Redis | `(sin credenciales)` | PING | denegado | denegado | Authentication required. |
| Redis | `tiendaya_api` | PING con contraseña incorrecta | denegado | denegado | invalid username-password pair or user is disabled. |
| Redis | `tiendaya_api` | SET carrito:9900099 (su prefijo carrito:*) | permitido | permitido | — |
| Redis | `tiendaya_api` | SET otra:cosa (fuera de sus prefijos) | denegado | denegado | No permissions to access a key |
| Redis | `tiendaya_api` | FLUSHALL | denegado | denegado | User tiendaya_api has no permissions to run the 'flushall' command |
| Redis | `tiendaya_api` | KEYS * | denegado | denegado | User tiendaya_api has no permissions to run the 'keys' command |
| Redis | `tiendaya_api` | CONFIG GET requirepass | denegado | denegado | User tiendaya_api has no permissions to run the 'config\|get' command |
| Redis | `tiendaya_api` | ACL LIST | denegado | denegado | User tiendaya_api has no permissions to run the 'acl\|list' command |
| Redis | `tiendaya_api` | Lua que escribe otra:cosa | denegado | denegado | ACL failure in script: No permissions to access a key script: 2f002ef4df523da6842bd5c62a28ae83e3945586, on @us |
| Redis | `tiendaya_lectura` | GET carrito:9900099 | permitido | permitido | — |
| Redis | `tiendaya_lectura` | SET carrito:9900099 | denegado | denegado | User tiendaya_lectura has no permissions to run the 'set' command |
| Redis | `tiendaya_lectura` | DEL carrito:9900099 | denegado | denegado | User tiendaya_lectura has no permissions to run the 'del' command |
| Redis | `default (solo contraseña)` | GET carrito:9900099 | permitido | permitido | — |
| Redis | `default (solo contraseña)` | FLUSHALL | denegado | denegado | User default has no permissions to run the 'flushall' command |
| Redis | `tiendaya_admin` | ACL USERS | permitido | permitido | — |
| MongoDB | `(sin credenciales)` | find en productos | denegado | denegado | Command find requires authentication, full error: {'ok': 0.0, 'errmsg': 'Command find requires authentication' |
| MongoDB | `tiendaya_api` | find con contraseña incorrecta | denegado | denegado | Authentication failed., full error: {'ok': 0.0, 'errmsg': 'Authentication failed.', 'code': 18, 'codeName': 'A |
| MongoDB | `tiendaya_api` | find en productos | permitido | permitido | — |
| MongoDB | `tiendaya_api` | update y delete en producto_eventos (sin tocar datos) | permitido | permitido | — |
| MongoDB | `tiendaya_api` | no tiene dropCollection ni dropDatabase (connectionStatus) | permitido | permitido | — |
| MongoDB | `tiendaya_api` | find en migraciones (fuera de su rol) | denegado | denegado | not authorized on tiendaya to execute command { find: "migraciones", filter: {}, limit: 1, singleBatch: true,  |
| MongoDB | `tiendaya_api` | insert en una colección nueva | denegado | denegado | not authorized on tiendaya to execute command { insert: "coleccion_ajena", ordered: true, lsid: { id: UUID("b4 |
| MongoDB | `tiendaya_api` | find en admin.system.users | denegado | denegado | not authorized on admin to execute command { find: "system.users", filter: {}, limit: 1, singleBatch: true, ls |
| MongoDB | `tiendaya_api` | createUser intruso con rol root | denegado | denegado | not authorized on tiendaya to execute command { createUser: "intruso", pwd: "xxx", roles: [ "root" ], lsid: {  |
| MongoDB | `tiendaya_lectura` | count en productos | permitido | permitido | — |
| MongoDB | `tiendaya_lectura` | insert en productos | denegado | denegado | not authorized on tiendaya to execute command { insert: "productos", ordered: true, lsid: { id: UUID("d9cfce61 |
| MongoDB | `tiendaya_admin` | crear y borrar una colección de prueba en tiendaya | permitido | permitido | — |
| MongoDB | `tiendaya_admin` | find en admin.system.users | denegado | denegado | not authorized on admin to execute command { find: "system.users", filter: {}, limit: 1, singleBatch: true, ls |
| Elasticsearch | `(sin credenciales)` | count en productos | denegado | denegado | AuthenticationException(401, 'security_exception', 'missing authentication credentials for REST request [/prod |
| Elasticsearch | `tiendaya_api` | count con contraseña incorrecta | denegado | denegado | AuthenticationException(401, 'security_exception', 'unable to authenticate user [tiendaya_api] for REST reques |
| Elasticsearch | `tiendaya_api` | search en productos | permitido | permitido | — |
| Elasticsearch | `tiendaya_api` | no puede borrar, crear ni administrar el índice (has_privileges) | permitido | permitido | — |
| Elasticsearch | `tiendaya_api` | crear el índice productos_intruso | denegado | denegado | AuthorizationException(403, 'security_exception', 'action [indices:admin/create] is unauthorized for user [tie |
| Elasticsearch | `tiendaya_api` | agregar un alias a productos | denegado | denegado | AuthorizationException(403, 'security_exception', 'action [indices:admin/aliases] is unauthorized for user [ti |
| Elasticsearch | `tiendaya_api` | search en .security-7 | denegado | denegado | AuthorizationException(403, 'security_exception', 'action [indices:data/read/search] is unauthorized for user  |
| Elasticsearch | `tiendaya_api` | crear un usuario superuser | denegado | denegado | AuthorizationException(403, 'security_exception', 'action [cluster:admin/xpack/security/user/put] is unauthori |
| Elasticsearch | `tiendaya_lectura` | search en productos | permitido | permitido | — |
| Elasticsearch | `tiendaya_lectura` | index de un documento en productos | denegado | denegado | AuthorizationException(403, 'security_exception', 'action [indices:data/write/index] is unauthorized for user  |
| Elasticsearch | `tiendaya_indexador` | crear y borrar productos_verificar_tmp | permitido | permitido | — |
| Elasticsearch | `tiendaya_indexador` | crear otro_indice_verificar (fuera de productos*) | denegado | denegado | AuthorizationException(403, 'security_exception', 'action [indices:admin/create] is unauthorized for user [tie |
