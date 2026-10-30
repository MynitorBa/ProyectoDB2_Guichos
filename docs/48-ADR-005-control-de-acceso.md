# ADR-005 · Control de acceso en los componentes NoSQL

| Campo | |
|---|---|
| Estado | Aceptada (Entrega final) |
| Componente | Redis, MongoDB y Elasticsearch |
| Decisión | **Un usuario por servicio con mínimo privilegio** en los tres componentes NoSQL que usa el backend; reglas versionadas en el repositorio y contraseñas generadas al azar en cada equipo, fuera de git |

## Contexto

El enunciado de la entrega final pide autenticación y autorización configuradas explícitamente en al menos un
componente NoSQL, con roles y permisos acotados según el servicio que los usa, y evidencia de que un usuario
sin permisos no puede salirse de su alcance.

Estado del sistema antes de esta decisión:

| Componente | Autenticación | Con qué se conectaba el backend |
|---|---|---|
| Redis | Ninguna: cualquiera que alcanzara el puerto podía leer los carritos o ejecutar `FLUSHALL` | Sin usuario |
| MongoDB | Solo el usuario root | **root** (`admin`): el backend podía borrar cualquier base o crear usuarios |
| Elasticsearch | Desactivada (`xpack.security.enabled: false`) | Sin usuario: podía borrar el índice o cambiar el alias |
| Contraseñas | Fijas en el repositorio (`.env.example`, valores por defecto de `config.py` y de 19 scripts) | — |

Con esto, un fallo en el backend (por ejemplo, una inyección en una consulta) o cualquier proceso de la
máquina tenía control total sobre los tres motores.

## Alternativas consideradas

| Alternativa | Qué resuelve | Qué no |
|---|---|---|
| **1. No introducir cambios** | Nada | No cumple el requerimiento |
| **2. Solo aislar la red** (puertos en `127.0.0.1` o red interna de Docker) | Que otras máquinas no lleguen a los puertos | Cualquier proceso local sigue teniendo control total, y el backend sigue siendo root en Mongo |
| **3. Una contraseña por componente** (`requirepass` en Redis, un usuario `readWrite` en Mongo, un usuario en Elasticsearch) | Autenticación | No hay autorización: el backend, Mongo Express y la instalación tendrían los mismos permisos. Un fallo en el backend podría seguir borrando todo |
| **4. Usuarios por servicio con mínimo privilegio** | Autenticación y autorización acotada por servicio | — (**elegida**) |
| **5. Gestor de secretos externo** (HashiCorp Vault, secretos de la nube) | Rotación y auditoría de contraseñas | Un servicio más que operar para un proyecto que corre en laptops; no cambia los permisos, solo dónde viven las contraseñas |

## Decisión

En cada componente, un usuario para cada servicio que lo usa, con solo lo que ese servicio necesita (detalle
en [docs/47](47-control-de-acceso.md)):

| | Backend | Herramienta de consulta | Instalación / operación |
|---|---|---|---|
| **Redis** (ACL) | `tiendaya_api`: sus 9 prefijos y 34 comandos | `tiendaya_lectura` y `default`: solo lectura (Redis Commander) | `tiendaya_admin` |
| **MongoDB** (roles) | `tiendaya_api`: rol a medida sobre 5 colecciones, sin `drop` | `tiendaya_lectura`: `read` (Mongo Express) | `tiendaya_admin`: `dbOwner` solo de `tiendaya` |
| **Elasticsearch** (roles) | `tiendaya_api`: documentos de `productos*`, sin crear ni borrar índices | `tiendaya_lectura`: solo leer (Elasticvue) | `tiendaya_indexador`: `productos*` y `bench_vectores_*` |

- **Reglas en el repositorio** (`database/redis/acl.conf`, `database/mongo/03_usuarios.js`,
  `database/elasticsearch/seguridad.json`): son código que se revisa y que es igual en todos los equipos.
- **Contraseñas fuera del repositorio**: `scripts/generar-credenciales.ps1` las genera al azar en `.env` y
  `backend/.env` (ignorados por git) y adopta las que ya existían en una instalación previa, sin cambiarlas.
  El backend recibe solo las de su usuario. `scripts/configurar-acceso.ps1` aplica todo en un comando.
- **Sin modo abierto**: si falta una contraseña, `docker compose` se niega a arrancar y dice qué ejecutar.

## Justificación

| Criterio | Argumento |
|---|---|
| Patrón de acceso | Los permisos salen de lo que el código hace de verdad: un inventario de comandos y colecciones, validado después corriendo las 397 pruebas con los usuarios restringidos y revisando los rechazos de cada motor (`ACL LOG` en Redis, registro de control de acceso en Mongo, advertencias del backend en Elasticsearch). El plan B podía esconder un permiso faltante, porque si un motor rechaza, el backend usa el respaldo sin que falle ninguna prueba. Así apareció `ZRANGEBYLEX` en Redis, que el inventario no tenía. |
| Consistencia | Las reglas versionadas hacen que el control de acceso sea el mismo en todos los equipos y en la instalación desde cero. Los scripts son idempotentes: correrlos de nuevo no cambia contraseñas ni pierde datos. |
| Escalabilidad | Agregar un servicio es agregar un usuario con su rol, sin tocar a los demás. Cada contraseña se puede rotar sin afectar a los otros servicios. |
| Costo operativo | Ningún componente nuevo: Redis ACL, roles de MongoDB y la seguridad de Elasticsearch (licencia básica) vienen incluidos. Un comando configura un equipo existente; la instalación lo hace sola. |
| Seguridad | Un fallo en el backend ya no puede borrar el índice, las colecciones ni los datos de Redis fuera de los suyos, ni crear usuarios. Las herramientas de consulta (Commander, Mongo Express, Elasticvue) no pueden escribir. |

**Evidencia**: 50 pruebas automáticas (`test_permisos_redis.py`, `test_permisos_mongo.py`,
`test_permisos_elasticsearch.py`) y `backend/scripts/verificar_permisos.py`, que hace 40 intentos reales contra
el sistema en marcha y deja la tabla en [evidencia/permisos.md](evidencia/permisos.md). Lo que borraría datos
no se intenta: se pregunta al motor si el usuario tiene el privilegio (`connectionStatus`, `has_privileges`).

## Consecuencias

**Beneficios**
- Autenticación obligatoria en Redis, MongoDB y Elasticsearch; el enunciado pide al menos uno.
- El backend opera con mínimo privilegio en los tres; las herramientas de consulta solo leen.
- No queda ninguna contraseña en el repositorio (solo las de los usuarios de prueba de la tienda, que son datos
  semilla documentados).

**Limitaciones asumidas**
- **Sin TLS**: en desarrollo los motores están en la misma máquina y las contraseñas viajan sin cifrar. En
  producción se activaría TLS (Redis `tls-port`, MongoDB `net.tls`, Elasticsearch `xpack.security.http.ssl`)
  sin cambiar usuarios ni roles.
- **Siguen existiendo superusuarios** (`root` de MongoDB, `elastic`, `tiendaya_admin` de Redis): se usan solo
  para crear los usuarios, nunca desde el backend.
- **Contraseñas en archivos de texto** (`.env`) en cada equipo: aceptable en laptops de desarrollo; en
  producción irían a un gestor de secretos (alternativa 5).
- **Elasticvue corre en el navegador**: su contraseña la ve quien abra :8083, por eso usa el usuario que solo
  lee.
- **Fuera del alcance**: MySQL ya usaba un usuario propio (`tiendaya`, no root); Neo4j y Cassandra no se
  restringieron en esta entrega. El entorno DEMO de la presentación se configura en la fase 15, junto con sus
  demás cambios.
- **Rotar contraseñas** de MySQL root, Mongo root o Neo4j exige cambiarlas también dentro del motor, porque
  sus volúmenes ya se crearon con ellas; las de los usuarios de servicio se rotan volviendo a correr
  `configurar-acceso.ps1`.
