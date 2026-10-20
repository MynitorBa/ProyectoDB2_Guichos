# Presentación de Entrega 3: DEMO original

La tienda y el laboratorio son **dos aplicaciones React independientes**. El
panel Admin conserva las fichas F01–F07; el laboratorio no aparece duplicado
allí. Ambos consultan el mismo backend, conectado exclusivamente a los seis
motores de `tiendaya_demo`. Los datos son sintéticos y conservan las
limitaciones históricas descritas en [el estado del proyecto](40-estado-proyecto-y-pendientes.md).

| Servicio | URL en esta presentación |
|---|---|
| TiendaYa | http://localhost:5173 |
| Laboratorio original | http://localhost:5174 |
| API FastAPI | http://localhost:8000/docs |
| Pasarela simulada | http://localhost:8001/docs |

## Arranque y apagado

Desde la raíz del repositorio, con Docker Desktop abierto:

```powershell
.\scripts\start-presentation.ps1
# Después de la presentación:
.\scripts\stop-presentation.ps1
```

El arranque comprueba rama de datos mediante `backend/.env.demo`, los seis
volúmenes `tiendaya_demo_demo_*`, contenedores y puertos libres. Importa las
variables DEMO al proceso **antes** de iniciar FastAPI en `:8000`; por tanto,
el número de puerto no hace que lea la base PRINCIPAL. Usa `--lifespan off`
para no iniciar automáticamente los workers de fraude, ventas flash o
recuperación. El único worker iniciado aparte es Outbox. No ejecuta
`setup.ps1`, migraciones, seeds, backfills, reparaciones ni reindexación.
También se niega a arrancar si PRINCIPAL o `tiendaya_demo_clean` tienen
contenedores activos. El apagado valida los procesos registrados, detiene solo
los de la presentación y hace `docker compose stop` de `tiendaya_demo`, sin
eliminar volúmenes. Si la identificación falla, no detiene nada por su cuenta.

La pasarela usa `payment_simulator/ledger.demo.db`, **ignorado por Git** y
separado de `ledger.db` de desarrollo. Es un prerrequisito local: el arranque
se detiene si falta para no aparentar que cobros históricos desaparecieron.
En el equipo de presentación se preparó mediante una copia consistente de
SQLite y se comprobó contra las compras de la DEMO. En otro equipo, validar
primero la procedencia de su ledger DEMO; no copiar a ciegas el de PRINCIPAL
ni subir bases SQLite al repositorio.

El frontend Vite usa proxy `/api` y `/static` hacia `:8000`. El laboratorio
consulta directamente `http://localhost:8000/api/v1`; CORS admite su origen
`http://localhost:5174` para los diagnósticos de lectura. El backend usa
`PAYMENT_GATEWAY_URL=http://127.0.0.1:8001` y el laboratorio muestra los
contenedores `tiendaya_demo_*`, no los de PRINCIPAL.

## Laboratorio en modo seguro

Ingresar en `:5174` con el administrador de prueba. Con
`FAULT_INJECTION_ENABLED=false` se pueden consultar Outbox, invariantes,
bitácora de la saga y estado de la pasarela. Los paneles originales de modos
de pago, puntos de falla, comandos Docker, reintentos y recuperación manual
permanecen visibles, pero sus controles están deshabilitados. No se afirma
que una falla se haya probado ahora por estar visible el botón. Para ejecutar
esas acciones se necesita un entorno aislado, respaldado y restaurable con
inyección habilitada expresamente; no se usan sobre esta DEMO original.

## Alcance verificable

Esta configuración permite presentar catálogo, búsqueda, reseñas,
recomendaciones, estadísticas y fraude F01–F07, más la evidencia histórica de
checkout, saga y Outbox. Las comprobaciones de esta integración son de lectura
y compilación. La suite completa y una demostración nueva de checkout/fallas
requieren bases de prueba aisladas; la DEMO original tiene las inconsistencias
sintéticas conocidas documentadas en `docs/40-estado-proyecto-y-pendientes.md`.
No utilizar la DEMO limpia incompleta ni presentarla como dataset medium válido.

## Comprobación de integración (20 de octubre de 2026)

- Ambas aplicaciones compilaron con Vite y cuatro pruebas focalizadas de
  enriquecimiento de evidencias y registro condicional de rutas aprobaron.
  La suite completa no se ejecutó contra bases vivas.
- Login de administrador comprobado visualmente en tienda y laboratorio.
  TiendaYa mostró 285 productos en catálogo, detalle con ofertas y reseñas,
  panel Admin con F01–F07 y panel vendedor. La sección «Más vendidos» volvió
  a mostrar ocho productos al corregir una redirección fuera del proxy.
- El laboratorio independiente mostró sus paneles originales, cinco destinos
  Outbox al día, bitácora de la saga e invariantes consultables. La pasarela
  indicó modo aprobar en `:8001`; la inyección de fallas estaba deshabilitada
  y los controles de escritura aparecieron inactivos. No se ejecutó ninguna
  simulación de falla ni una compra nueva.
- Los invariantes de lectura se mostraron en verde; el propio diagnóstico
  señala tres pedidos semilla anteriores a la saga como excepción histórica.
  Los conteos de alertas pueden variar con la vigencia temporal y no prueban
  integridad comercial completa de la DEMO original.
