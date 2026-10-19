# Entorno DEMO aislado y datos sintéticos masivos

## Perfil de memoria para equipos con 32 GB

La pila DEMO define límites únicamente para sus propios contenedores: MySQL
768 MiB, MongoDB 768 MiB, Redis 256 MiB, Cassandra 1.5 GiB, Neo4j 1 GiB y
Elasticsearch 1.25 GiB. El máximo agregado es aproximadamente 5.5 GiB. Estos
límites no modifican los motores de la instancia principal.

El arranque se bloquea si Windows tiene menos de 8 GB de RAM física disponible,
si la memoria comprometida alcanza 80% o si quedan menos de 15 GB en disco. Las
cargas pequeña, mediana y completa vuelven a comprobar recursos y exigen 6, 7
y 8 GB disponibles, respectivamente. Que Docker tenga espacio bajo su límite no
es suficiente: también debe existir margen real para Windows y los procesos del
generador.

En una máquina bajo presión se recomienda cerrar aplicaciones de usuario que
consuman mucha RAM y volver a medir. No se debe reiniciar WSL mientras TiendaYa
principal esté en servicio. Si aun así no se cumplen las barreras, se operan los
entornos por turnos.

## Alcance

El entorno DEMO está diseñado para observar volumen, tendencias y patrones
F01–F06 sin mezclar un solo registro con la instancia principal. F07 permanece
fuera de alcance. Esta preparación no autoriza borrar volúmenes ni reutilizar
puertos productivos.

## Aislamiento

`docker-compose.demo.yml` define seis motores con contenedores y volúmenes
propios:

| Componente | Principal | DEMO |
|---|---:|---:|
| MySQL | 3307 / `tiendaya` | 3317 / `tiendaya_demo` |
| MongoDB | 27017 / `tiendaya` | 27117 / `tiendaya_demo` |
| Redis | 6379 | 6389 |
| Cassandra | 9042 / `tiendaya_analytics` | 9142 / `tiendaya_analytics_demo` |
| Neo4j Bolt/HTTP | 7687 / 7474 | 7787 / 7574 |
| Elasticsearch | 9200 / `productos` | 9210 / `productos_demo` |
| Backend | 8000 | 8005 |
| Frontend | 5173 | 5175 |
| Pasarela simulada | 8001 | 8006 |

El frontend DEMO muestra permanentemente el rótulo **TiendaYa — DEMO / DATOS
SINTÉTICOS**. `.env.demo` está excluido de Git; el repositorio conserva solo
`.env.demo.example`.

## Protección contra accidentes

`backend/scripts/seed_demo_large.py` exige simultáneamente:

- `--env-file` explícito y `--confirm-demo`.
- `TIENDAYA_DEMO=true`.
- nombres MySQL, MongoDB y Cassandra terminados en `_demo`.
- alias Elasticsearch que contenga `demo`.
- puertos distintos de todos los motores principales.

La validación ocurre antes de abrir conexiones. Los identificadores, usuarios,
correos y textos son sintéticos y están marcados con un `run_id`. La semilla
predeterminada es reproducible. Una tabla local `demo_seed_runs` registra el
avance y las métricas de cada corrida.

## Perfiles

| Perfil | Usuarios | Vendedores | Productos | Ofertas | Pedidos | Líneas | Reseñas |
|---|---:|---:|---:|---:|---:|---:|---:|
| small | 80 | 8 | 40 | 60 | 180 | 270 | 80 |
| medium | 650 | 30 | 220 | 320 | 1,600 | 2,400 | 700 |
| full | 3,000 | 100 | 800 | 1,000 | 8,000 | 12,000 | 3,000 |

La carga usa lotes configurables, claves deterministas y `INSERT IGNORE` o
upserts donde corresponde. Pedidos, pagos, líneas, vendedores, inventario,
movimientos, historiales y reseñas mantienen sus claves y estados. MongoDB se
carga con documentos de producto; Cassandra, Neo4j y Elasticsearch se
reconstruyen mediante los backfills oficiales apuntando al entorno DEMO. Redis
queda disponible para probar carritos y TTL sin crear reservas permanentes.

## Escenarios etiquetados

- **F01:** seis compradores distintos compran y reseñan el mismo producto en
  menos de 24 horas; la carga general aporta actividad normal de contraste.
- **F02:** un comprador concentra tres compras y reseñas verificables en un
  vendedor.
- **F03:** cuatro compradores comparten tres productos comprados y reseñados.
- **F04:** aproximadamente 10 % de las reseñas son históricas, no verificadas,
  no públicas y claramente marcadas como DEMO.
- **F05:** propietarios de vendedor realizan compras pagadas de ofertas propias.
- **F06:** ofertas seleccionadas reciben al menos tres ajustes positivos hechos
  por el propietario, junto con ventas pagadas y movimientos normales.

Las reglas siguen siendo heurísticas explicables; estos datos permiten medir
verdaderos/falsos positivos conocidos, no afirmar precisión de un modelo de IA.

## Operación cuando existan recursos

Desde la raíz, en PowerShell:

```powershell
# Comprueba puertos y contenedores DEMO
.\scripts\demo-environment.ps1 -Action status

# Requiere al menos 8 GB de RAM libre, menos de 80 % de memoria
# comprometida y 15 GB de disco libre
.\scripts\demo-environment.ps1 -Action start
.\scripts\demo-environment.ps1 -Action bootstrap

# Primero validar el perfil pequeño
.\scripts\demo-environment.ps1 -Action seed-small
.\scripts\demo-environment.ps1 -Action start-app
```

Después de comprobar integridad y consumo puede usarse `seed-medium` y por
último `seed-full`. Nunca se recomienda saltar directamente al perfil completo.

URLs DEMO previstas:

- Frontend: `http://localhost:5175`
- Backend: `http://localhost:8005/docs`
- Neo4j Browser: `http://localhost:7574`
- Elasticsearch: `http://localhost:9210`

Para detener exclusivamente DEMO conservando sus volúmenes:

```powershell
.\scripts\demo-environment.ps1 -Action stop
```

No utilizar `docker compose down -v`: eliminaría los volúmenes DEMO. El script
no toca contenedores, procesos, puertos ni volúmenes de la instancia principal.

### Reconciliación del seed académico de reseñas

Una instalación DEMO fresca parte con Neo4j vacío. Por ello la migración de
autoridad no puede recuperar por sí sola las 17 compras pagadas que respaldan
parte de las 42 reseñas del seed base. Antes de ampliar la carga se debe auditar
la evidencia individual:

```powershell
cd backend
.\venv\Scripts\python.exe scripts\reconcile_demo_base_reviews.py `
  --env-file .env.demo
```

El modo predeterminado es de solo lectura y debe producir 17 reseñas elegibles
y 25 históricas. Después de revisar cada usuario, producto, vendedor, línea,
estado de pedido y pago, la aplicación explícita es:

```powershell
.\venv\Scripts\python.exe scripts\reconcile_demo_base_reviews.py `
  --env-file .env.demo --apply --confirm-demo
```

El script rechaza puertos y nombres de la instancia principal, no modifica las
25 reseñas sin evidencia y reproyecta las reseñas reconciliadas a Neo4j.

### Operación por turnos

Cuando no sea seguro mantener las dos pilas en memoria, el cambio de entorno se
realiza con confirmación explícita y siempre mediante `docker compose stop`, sin
eliminar contenedores ni volúmenes:

```powershell
# Solo lectura
.\scripts\switch-ti-endaya-environment.ps1 -Action status

# Detiene PRINCIPAL y abre DEMO
.\scripts\switch-ti-endaya-environment.ps1 -Action to-demo -ConfirmSwitch

# Detiene DEMO y restaura PRINCIPAL, incluido el worker si está habilitado
.\scripts\switch-ti-endaya-environment.ps1 -Action to-main -ConfirmSwitch
```

El script no ejecuta setup, migraciones, seeds, backfills ni resets. Antes de
detener un puerto comprueba que corresponda al proceso esperado de TiendaYa.
El frontend DEMO fuerza `VITE_API_URL=/api/v1`; así utiliza el proxy de Vite
hacia `127.0.0.1:8005` sin cambiar la configuración normal de `5173`.

## Estado de esta computadora

El perfil `small` fue cargado y validado en la pila aislada. Mantener PRINCIPAL
y DEMO simultáneamente redujo posteriormente la RAM libre a cerca de 1.6 GB y
provocó paginación ligera. Por ello la operación recomendada es por turnos.
Los perfiles `medium` y `full` continúan protegidos por guardas de RAM libre,
memoria comprometida y disco, y no deben ejecutarse mientras ambas pilas estén
activas.
