# Auditoría de fraude y diseño de automatización

**Fecha de auditoría:** 18 de octubre de 2026

**Rama y referencia:** `entrega3-mynor` en `5ed005a26217e33140a983643a63b716e70a446d`

**Alcance:** investigación, pruebas no destructivas y diseño. No se implementó
ninguna corrección ni programador.

## Resumen ejecutivo

TiendaYa cuenta con dos familias distintas de análisis:

1. consultas informativas de Neo4j para reseñas y compras (`F01` a `F05` y
   ventas flash); y
2. expedientes administrativos persistentes en MySQL, generados únicamente por
   el recálculo manual para autocompras (`F05`) e inventario atípico (`F06`).

La arquitectura mantiene una separación correcta: las señales no bloquean el
checkout y requieren revisión humana. Sin embargo, la auditoría confirmó tres
problemas prioritarios antes de automatizar el recálculo:

- `F02` devuelve una fila por reseña después de haber agregado por usuario; en
  los datos actuales produjo dos filas para una sola combinación
  usuario-vendedor.
- `F06` denomina `sales` a todas las salidas de inventario y no verifica que
  estén asociadas a un pago aprobado. En la instancia auditada existen 40
  salidas, pero solamente 36 tienen un pago aprobado asociado.
- no existe exclusión mutua entre dos recálculos. La huella única evita el
  duplicado persistente, pero dos ejecuciones simultáneas pueden competir por
  insertar la misma alerta y una puede terminar en `IntegrityError`.

La automatización horaria debe construirse después de corregir y cubrir estos
hallazgos. Se recomienda un proceso Python independiente, reutilizable también
por el botón manual, coordinado mediante MySQL y arrancado por `start-dev.ps1`.
Para ejecutar aun cuando FastAPI esté detenido, se recomienda invocar el mismo
trabajo de una sola ejecución desde el Programador de tareas de Windows.

## Estado actual y componentes

### Autoridades y proyecciones

- **MySQL:** autoridad de usuarios, vendedores, ofertas, pedidos, pagos,
  inventario, reseñas y expedientes `alertas_fraude`.
- **Neo4j:** proyección reconstruible de compras pagadas, reseñas, vendedores y
  productos para recorridos de grafo.
- Ninguna consulta de fraude participa en la transacción de checkout ni cambia
  inventario.

### Endpoints administrativos

Todos requieren rol administrador y se encuentran bajo `/api/v1/reviews`:

| Método y ruta | Función | Naturaleza |
|---|---|---|
| `GET /admin/fraude/resumen` | F01–F04 resumidas | Informativa, Neo4j |
| `GET /admin/fraude/bombardeo` | F01 parametrizable | Informativa, Neo4j |
| `GET /admin/fraude/sin-compra` | F04 | Informativa, Neo4j |
| `GET /admin/fraude/reviewer-unico-vendedor` | F02 | Informativa, Neo4j |
| `GET /admin/fraude/cluster` | F03 | Informativa, Neo4j |
| `POST /admin/fraude/recalcular` | F05 y F06 | Escribe/actualiza expedientes MySQL |
| `GET /admin/fraude/alertas` | Lista expedientes | Lectura MySQL |
| `PATCH /admin/fraude/alertas/{id}` | Revisión humana | Escritura MySQL |
| `GET /admin/fraude/ventas-flash` | Conversiones flash pagadas | Informativa, Neo4j |
| `GET /admin/fraude/ventas-flash/resumen` | Concentración flash | Informativa, Neo4j |

El panel muestra cuatro tarjetas para F01–F04, una lista de expedientes F05/F06,
un selector de estado y una tabla detallada de F04. Mantiene el botón
**Recalcular señales**.

## Revisión por mecanismo

### F01 — Bombardeo de reseñas

- Ventana predeterminada: 24 horas; el endpoint acepta de 1 a 168 horas.
- Umbral predeterminado: 5; el endpoint permite valores desde 2.
- Agrupa por producto y ordena por cantidad descendente.
- Riesgo: cuenta todas las reseñas proyectadas sin filtrar `verificada` ni
  estado de moderación. Una reseña histórica no pública podría contribuir a la
  señal.
- El resumen solo expone los primeros cinco elementos, aunque conserva el
  conteo completo de la consulta.

### F02 — Concentración en un vendedor

- Primero agrega por usuario, exige un solo vendedor y un mínimo de tres
  reseñas.
- Después vuelve a recorrer todas las reseñas del usuario sin reagrupar ni usar
  `DISTINCT`; por ello devuelve una fila repetida por reseña.
- **Defecto confirmado:** con `min_resenas=2`, la instancia produjo 2 filas para
  una única combinación `(usuario 8, vendedor 1)`.
- También incluye reseñas históricas/no verificadas, lo que puede convertir una
  concentración antigua en señal actual.

### F03 — Cuentas coordinadas

- Recorre `Usuario → Reseña → Producto ← Reseña ← Usuario`.
- Evita el par invertido mediante `u1.id < u2.id` y cuenta productos distintos.
- Umbral predeterminado: tres productos comunes; el endpoint permite desde dos.
- No limita por fecha, verificación ni moderación. Las reseñas históricas pueden
  formar parte del patrón.
- En los datos actuales no apareció ningún par ni siquiera con umbral dos.

### F04 — Reseñas sin compra elegible

- Consulta reseñas con `verificada=false` y estado pendiente o aprobado.
- Las 25 reseñas históricas no verificadas siguen fuera de la vista pública; la
  moderación no transforma `verificada_compra` ni sustituye la validación
  transaccional de MySQL.
- La consulta tiene límite 50. El contador del resumen es por tanto un conteo
  truncado si existieran más de 50 casos.
- Estado actual observado: 25 señales.

### F05 — Autocompras

- Recorre `Usuario-[:GESTIONA]->Vendedor` y
  `Usuario-[:REALIZO]->Compra-[:A_VENDEDOR]->Vendedor`.
- Agrupa por usuario, vendedor, producto y oferta; calcula compras, unidades y
  concentración respecto de unidades pagadas en MySQL.
- Las compras proyectadas son pagadas, pero la consulta usa todo el historial;
  no posee ventana móvil configurable.
- `GESTIONA` representa al propietario actual. Un cambio histórico de dueño
  podría atribuir compras antiguas al propietario nuevo si no se conserva la
  vigencia temporal de la propiedad.
- Estado actual observado: cero autocompras.

### F06 — Inventario atípico

- Selecciona ofertas con al menos tres entradas/ajustes positivos o 25 unidades
  positivas durante los últimos 30 días.
- Abre expediente si encuentra dos pares temporales, tres ajustes manuales o
  intervención reiterada del propietario con volumen suficiente.
- **Defecto confirmado por código y datos:** considera toda fila `tipo='salida'`
  como venta. No exige `pedido_id`, pedido válido ni pago aprobado. Actualmente
  hay 40 salidas: 40 tienen pedido, pero solo 36 tienen pago aprobado.
- El emparejamiento busca, para cada reposición, la primera salida ubicada a
  ±3 días. No exige que la salida ocurra antes de la reposición, no compara
  cantidades y no reserva cada salida para un único emparejamiento.
- Por tanto una misma salida puede reutilizarse para varias reposiciones. No se
  observó el caso en la instancia actual porque no hay movimientos positivos,
  pero el algoritmo lo permite.
- `entrada` y `ajuste` se tratan juntos. La evidencia distingue ajustes
  manuales, aunque no valida el motivo ni la procedencia de una entrada.

### Ventas flash

Las dos consultas exigen simultáneamente `promocion_flash_id IS NOT NULL` y
`Compra.pagada=true`. No incluyen reservas ni intentos fallidos. La instancia
actual contiene dos conversiones pagadas, cada una de una unidad.

## Expedientes persistentes

La huella SHA-256 se calcula con tipo, usuario, vendedor, producto y oferta. La
restricción única `uq_alerta_fraude_huella` impide duplicados persistentes.

- Un nuevo análisis actualiza prioridad, motivos, evidencia y
  `ultima_deteccion`.
- Conserva correctamente `estado`, `revisada_por` y `notas_revision`.
- Si una señal deja de cumplir la condición, el expediente no cambia: no existe
  `activa`, `resuelta_en`, `ultima_ejecucion_id` ni cierre automático. Así, una
  alerta antigua puede parecer vigente.
- No se registra el origen manual/automático ni existe una bitácora de cada
  ejecución.
- Dos recálculos concurrentes realizan “consultar y luego insertar”; la
  restricción única protege los datos, pero no evita que una ejecución falle.
- Todas las escrituras se confirman al final. Una excepción previa al `commit`
  no debería persistir cambios, pero falta un `rollback` explícito y un bloque
  de servicio que normalice el error. El endpoint depende del cierre de la
  sesión de FastAPI para liberar la transacción.

## Pruebas ejecutadas

No se ejecutó `recalcular_alertas`, no se crearon pedidos, reseñas ni movimientos
y no se modificó ninguna base.

| Prueba ejecutada | Resultado esperado | Resultado observado | Evidencia |
|---|---|---|---|
| Regresión `test_neo4j_review_integrity.py` | Reglas de compra, reseña, grafo y flash intactas | 11/11 aprobadas | `pytest`, 3.45 s; solo advertencias de caché |
| F01–F04 sobre Neo4j | Consultas legibles sin escritura | F01=0, F02=0 con umbral normal, F03=0, F04=25 | consultas de servicio en solo lectura |
| F02 con umbral 2 | Una fila por usuario/vendedor | 2 filas para 1 combinación | usuario 8, vendedor 1 |
| F03 con umbral 2 | Identificar pares comunes | 0 pares | consulta de solo lectura |
| F05 | Solo autocompras pagadas proyectadas | 0 casos | consulta de solo lectura |
| Ventas flash | Solo compras pagadas | 2 líneas, 2 resúmenes | promociones 1 y 7 |
| Inventario por tipo | Conocer el universo sin alterarlo | 40 salidas, 4 reservas, 3 liberaciones, 0 entradas/ajustes | agregación MySQL |
| Salidas con pago | Toda “venta” de F06 debería ser pagada | 36 de 40 poseen pago aprobado | cruce MySQL de lectura |
| Alertas actuales | Conservar expedientes existentes | 0 expedientes; no era posible observar preservación con datos reales | lectura MySQL |
| Reutilización observable | Detectar salidas emparejadas con varios positivos | 0, porque no existen movimientos positivos | consulta MySQL |

Las advertencias de pytest se deben a permisos para crear `.pytest_cache`; no
afectan el resultado.

## Escenarios diseñados, todavía no ejecutados

Estos casos requieren un esquema MySQL/Neo4j efímero o transacciones preparadas
con reconstrucción del grafo; no deben ejecutarse sobre la instancia principal.

| Escenario | Preparación controlada | Resultado esperado |
|---|---|---|
| Autocompra individual | Propietario compra una unidad pagada | Una señal informativa |
| Tres autocompras | Tres compras pagadas de la misma oferta | Prioridad elevada según volumen/movimientos |
| Autocompra por volumen | Una o más líneas suman al menos 10 unidades | Motivo explícito de volumen |
| Compra normal | Comprador sin `GESTIONA` | Ninguna F05 |
| Reposición habitual | Ventas pagadas y reposición documentada | No alertar por la sola reposición |
| Ajustes positivos repetidos | Tres ajustes positivos en 30 días | Candidato F06 con evidencia exacta |
| Ajustes por propietario | Dos o más ajustes del dueño y ≥25 unidades | Candidato F06 |
| Reseñas coordinadas | Dos usuarios comparten ≥3 productos | Un par único F03 |
| Vendedor legítimo de alto volumen | Muchas ventas y reposiciones, sin ajustes dudosos | Sin falso positivo |
| Repetir análisis | Ejecutar dos veces sobre la misma fotografía | Misma huella, un expediente, notas preservadas |
| Neo4j temporalmente caído | Fallar antes/durante lectura del grafo | Sin commit parcial; ejecución fallida auditable |
| Dos recálculos simultáneos | Barrera de hilos/procesos | Uno adquiere lock; el otro informa “en curso” |
| Señal desaparecida | Ejecutar, quitar condición en fixture y repetir | Expediente marcado inactivo/resuelto, no eliminado |
| Reloj controlado | Congelar tiempo en límites 24 h/30 días | Inclusión y exclusión exactas |

## Hallazgos y prioridad

| Prioridad | Hallazgo | Impacto | Corrección comprobable |
|---|---|---|---|
| Alta | F06 no exige venta pagada | Falsos pares y expedientes | Unir salida con pedido/línea/pago aprobado y probar cancelado/reembolsado |
| Alta | Recálculo sin exclusión mutua | Error concurrente o resultados no auditables | Lock MySQL compartido por botón y worker |
| Alta | No existe ejecución horaria ni bitácora | Decisión comercial incumplida | Worker + tabla de ejecuciones + configuración |
| Media | F02 duplica filas | Conteos y UI incorrectos | Reagrupar y retornar una fila por usuario/vendedor |
| Media | Alertas que dejan de cumplirse siguen aparentando vigencia | Revisión engañosa | Campo activo/última ejecución y cierre controlado |
| Media | F05 usa todo el historial y propietario actual | Atribución temporal débil | Ventanas configurables y vigencia de propiedad/snapshot |
| Media | F01–F03 incluyen reseñas históricas no verificadas | Falsos positivos | Separar análisis reciente verificado del histórico |
| Media | F06 permite reutilizar una salida | Evidencia inflada | Correspondencia uno-a-uno determinista |
| Media | Falta rollback/resultado uniforme | Diagnóstico débil ante fallos | Unidad de trabajo con `try/except/rollback/finally` |
| Baja | F04 limita y subcuenta a 50 | Resumen incompleto | Conteo separado y paginación |
| Baja | Umbrales incrustados | Difícil calibración | Configuración versionada y métricas de precisión |
| Baja | Panel no muestra evidencia completa, notas, origen ni última ejecución | Menor explicabilidad | Ampliar la vista actual sin rediseñarla |

## Diseño recomendado para ejecución cada hora

### Elección

Implementar un **proceso Python independiente** con una función de dominio
`run_fraud_analysis_once(origen)` compartida por el worker y el endpoint manual.
En desarrollo, `scripts/start-dev.ps1` lo inicia junto con FastAPI. En un
despliegue administrado debe ejecutarse como servicio. Si se necesita análisis
con FastAPI detenido en la computadora actual, el Programador de tareas de
Windows debe invocar el mismo comando en modo `--once` cada hora.

No se recomienda alojarlo solamente como hilo de FastAPI: con `uvicorn --reload`
puede haber procesos transitorios o duplicados y, si la API está detenida, el
análisis no se ejecuta. Tampoco se recomienda implementar dos lógicas distintas
para servicio y Programador de tareas.

### Configuración propuesta

- `FRAUD_ANALYSIS_ENABLED=false` por defecto hasta completar pruebas.
- `FRAUD_ANALYSIS_INTERVAL_SECONDS=3600`.
- `FRAUD_ANALYSIS_LOCK_NAME=tiendaya:fraud-analysis`.
- `FRAUD_ANALYSIS_LOCK_TIMEOUT_SECONDS=0`.

### Coordinación y estado

1. Worker y botón manual llaman a la misma unidad de trabajo.
2. La unidad intenta adquirir `GET_LOCK()` en MySQL usando una conexión
   dedicada que conserva durante toda la ejecución. Si no lo obtiene, responde
   “análisis en curso” sin ejecutar consultas.
3. Inserta una fila en `fraud_analysis_runs` con origen (`manual` o
   `automatico`), inicio, estado y dueño del proceso.
4. Lee Neo4j y calcula candidatos; las consultas deben ejecutarse fuera de las
   transacciones de checkout.
5. Abre una transacción MySQL breve para aplicar expedientes idempotentes y
   cerrar señales ausentes de la fotografía completa.
6. Registra fin, duración, conteos, éxito/error y mensaje sanitizado.
7. Ejecuta `rollback` explícito ante error y siempre libera sesión, conexión
   Neo4j y lock en `finally`.

La tabla de ejecuciones sirve para observabilidad, no como lock. El advisory
lock evita simultaneidad entre procesos y múltiples instancias. Debe probarse la
liberación por cierre de conexión tras una caída.

El bucle usa `Event.wait(intervalo)` para permitir apagado inmediato. Conviene
calcular la próxima ejecución desde la última ejecución exitosa persistida para
evitar una ráfaga tras reinicios. Un fallo de Neo4j registra la ejecución como
fallida; el siguiente intervalo reintenta creando una sesión nueva.

### Relación con checkout

- El worker usa su propia sesión y no comparte transacciones con pedidos.
- Las consultas analíticas deben limitar resultados e índices y persistir en
  una transacción corta.
- Nunca se adquieren locks de inventario ni pedidos usados por checkout.
- Las alertas siguen siendo informativas; ningún resultado cancela o rechaza
  una venta automáticamente.

### Panel administrativo

Ampliar la vista existente para mostrar:

- última ejecución, último éxito, duración y error;
- origen manual/automático;
- estados pendiente, en revisión, revisada, descartada e inactiva/resuelta;
- motivos y evidencia desplegable (compras, cantidades y movimientos);
- notas de revisión editables;
- etiqueta “histórica” o “reciente”; y
- el botón actual, deshabilitado con mensaje claro mientras existe un análisis.

No es necesario crear una pantalla nueva.

## Matriz de pruebas de la futura implementación

| Área | Prueba |
|---|---|
| Intervalo | Reloj falso dispara a 3600 s y respeta valor configurado |
| Desactivación | Worker no inicia con `ENABLED=false` |
| Arranque/reload | Dos procesos intentan ejecutar; solo uno obtiene lock |
| Manual vs automático | Solicitudes simultáneas producen una ejecución y una respuesta “en curso” |
| Idempotencia | Dos ejecuciones secuenciales conservan una alerta por huella |
| Revisión humana | Estado, revisor y notas sobreviven al recálculo |
| Desaparición | Señal ausente queda inactiva/resuelta sin borrar historia |
| Neo4j caído | Ejecución fallida registrada, sin escrituras parciales, siguiente intento recupera |
| MySQL caído/commit fallido | Rollback y liberación de recursos/lock |
| Apagado | `stop_event` termina el hilo/proceso sin esperar una hora |
| F02 | Una fila por usuario/vendedor con varias reseñas |
| F05 | Ventanas móviles y límites temporales con reloj congelado |
| F06 | Solo salidas con pago aprobado; correspondencia uno-a-uno |
| F07 | Casos positivos, negativos y ambiguos definidos en el documento 35 |
| Rendimiento | El análisis no agota el pool ni degrada una compra concurrente |

## Plan incremental y archivos estimados

1. **Corregir consultas y agregar regresiones:**
   `fraud_detection_service.py`, `test_neo4j_review_integrity.py` y un nuevo
   archivo de pruebas de fraude comercial.
2. **Agregar modelo de ejecuciones/estado de alerta:** nueva migración MySQL,
   modelo `fraud_analysis_run.py` y ampliación de `alerta_fraude.py`.
3. **Extraer unidad de trabajo y lock:** nuevo
   `fraud_analysis_service.py`; adaptar `reviews.py`.
4. **Worker:** nuevo `fraud_analysis_worker.py`, configuración en `config.py`,
   entrada independiente `scripts/run_fraud_analysis.py` y arranque opcional en
   `start-dev.ps1`.
5. **Panel:** `frontend/src/api/reviews.js` y `AdminPage.jsx`.
6. **Documentación/operación:** README de instalación, evidencia funcional y
   comandos del Programador de tareas si se adopta esa modalidad.

## Riesgos y controles

- **Falsos positivos:** señales explicables, revisión humana y umbrales
  configurables; nunca bloqueo automático.
- **Duplicación:** huella única más lock y upsert transaccional.
- **Datos históricos:** etiquetar el origen y no reinterpretarlos como recientes.
- **Indisponibilidad:** ejecución registrada, rollback y reintento posterior.
- **Carga:** índices, ventanas acotadas, lotes y conexión independiente.
- **Reloj/zona horaria:** almacenar UTC y convertir solo en presentación.
- **Múltiples procesos:** no confiar en locks de Python; usar MySQL.

## Estado de esta fase

La sección anterior conserva la auditoría y el diseño original. La
implementación posterior se realizó el 18 de octubre de 2026 en la rama local
`feature/fraude-automatico`, sin aplicar cambios a la base principal.

## Implementación posterior a la auditoría

### Reglas corregidas

- **F01:** separa reseñas verificadas y públicas de las históricas no
  verificadas; conserva ventana y umbral configurables.
- **F02:** agrega por usuario y vendedor con conteos `DISTINCT`, evitando filas
  repetidas.
- **F03:** separa los dos segmentos y normaliza cada pareja con `u1.id < u2.id`
  para impedir pares invertidos.
- **F04:** el límite de elementos de evidencia ya no trunca el conteo total.
- **F05:** utiliza por defecto una ventana móvil de 30 días, permite consultar
  el histórico aparte y declara que solo se conoce el propietario actual del
  vendedor; no inventa propiedad histórica.
- **F06:** una salida solo es comercial cuando posee pedido, líneas de la misma
  oferta cuya suma coincide con la salida, pago aprobado y estado confirmado o
  posterior. Excluye pedidos pendientes, cancelados y reembolsados, salidas
  administrativas, reservas y liberaciones. El emparejamiento es uno a uno y
  solo relaciona reposiciones ocurridas después de la venta, dentro de tres
  días. La reposición frecuente por sí sola no se declara fraude.

F07 permanece expresamente fuera de alcance. No se crearon nodos
`MovimientoInventario`, relaciones `COINCIDE_CANTIDAD` ni coincidencias exactas
de cantidad a 30 días.

### Persistencia y concurrencia

La migración aditiva `database/mysql/23_fraud_automation.sql` crea
`fraud_analysis_runs` y agrega a `alertas_fraude` la vigencia, resolución,
ejecución y origen de la última detección. Estado de detección (`activa`) y
decisión humana (`estado`, revisor y notas) permanecen separados.

`run_fraud_analysis_once(origen)` es la unidad compartida por el botón manual y
el worker. Usa `GET_LOCK` en una conexión MySQL dedicada y transacciones de
negocio en otra sesión. Una segunda ejecución recibe “análisis en curso”; el
lock se libera aun ante error. Una ejecución interrumpida queda marcada como
fallida al recuperar el lock. Solo una ejecución completa inactiva señales
ausentes; las fallidas conservan la vigencia anterior.

### Ejecución automática

El proceso independiente se inicia con:

```powershell
cd backend
.\venv\Scripts\python.exe scripts\run_fraud_analysis.py --once
.\venv\Scripts\python.exe scripts\run_fraud_analysis.py --serve
```

Permanece apagado por defecto. Para habilitarlo:

```dotenv
FRAUD_ANALYSIS_ENABLED=true
FRAUD_ANALYSIS_INTERVAL_SECONDS=3600
FRAUD_ANALYSIS_LOCK_NAME=tiendaya:fraud-analysis
FRAUD_ANALYSIS_LOCK_TIMEOUT_SECONDS=0
FRAUD_SELF_PURCHASE_WINDOW_DAYS=30
```

`scripts/start-dev.ps1` abre el worker como proceso separado únicamente cuando
la bandera está en `true`. El intervalo se calcula desde el último éxito para
evitar duplicados después de reiniciar y `Ctrl+C` produce un apagado ordenado.

Para operar sin FastAPI desde el Programador de tareas de Windows, crear una
tarea horaria cuyo programa sea:

```text
C:\ruta\ProyectoDB2_Guichos\backend\venv\Scripts\python.exe
```

Argumentos:

```text
scripts\run_fraud_analysis.py --once
```

Directorio inicial:

```text
C:\ruta\ProyectoDB2_Guichos\backend
```

No se crea ninguna tarea automáticamente. La variable `FRAUD_ANALYSIS_ENABLED`
debe estar habilitada en `backend/.env` cuando se decida activar la operación.

### Panel y recuperación

La sección existente **Fraude & Reseñas** muestra última ejecución manual,
automática y exitosa, duración, resultado, error, conteos informativos,
expedientes activos/históricos, evidencia desplegable y notas editables. El
botón manual utiliza la misma unidad de trabajo y responde con conflicto si el
lock está ocupado. Las alertas son exclusivamente explicativas: no bloquean
checkout, pagos ni inventario.

### Evidencia de validación aislada

- Migración 23 aplicada dos veces sobre
  `tiendaya_fraud_test_20261018`: idempotente.
- Pruebas específicas unitarias e integración MySQL: **15 aprobadas**.
- Regresión backend completa: **184 aprobadas, 4 omitidas**.
- Frontend: `npm run build` completado correctamente.
- Se validaron lock ocupado, liberación tras error, ejecuciones manual y
  automática secuenciales, preservación de revisión humana, inactivación y
  reactivación, reloj controlado de 3600 segundos y F06 con pedidos pagados,
  pendientes, cancelados, reembolsados, salidas administrativas y pedidos con
  varias líneas.

Las omisiones corresponden a pruebas opt-in que requieren configuraciones
externas específicas; no son fallos.

### Estado operativo local — 18 de octubre de 2026

Después del PREDEPLOY se aplicó exclusivamente la migración 23 sobre `tiendaya`
con respaldo restaurado y SHA-256 comprobado. La ejecución manual `#1` terminó
exitosa en 219 ms. La primera ejecución automática controlada (`#2`) terminó
exitosa en 327 ms y los reinicios posteriores demostraron la recuperación por
último éxito persistido. Tras reiniciar la computadora, el ciclo debido quedó
registrado como ejecución automática `#4`, exitosa en 3,219 ms.

La instancia local tiene actualmente:

- `FRAUD_ANALYSIS_ENABLED=true`.
- Intervalo real de 3,600 segundos.
- Un único worker lógico ejecutado con `run_fraud_analysis.py --serve`.
- Un lock de servicio `tiendaya:fraud-analysis:worker` que rechaza un segundo
  proceso horario antes de que pueda iniciar otro bucle.
- Cero alertas comerciales activas en la última comprobación.
- Veinticinco reseñas históricas sin compra verificable, mostradas solamente
  como información y no convertidas en expedientes comerciales.

El worker depende de que la computadora, Docker y los motores estén encendidos.
No se instaló una tarea de Windows ni un servicio de inicio automático.

Inicio manual desde `backend/`:

```powershell
.\venv\Scripts\python.exe scripts\run_fraud_analysis.py --serve
```

Para detenerlo, cerrar ese proceso de forma ordenada con `Ctrl+C`. Para
comprobarlo, abrir **Admin > Fraude & Reseñas** o consultar el endpoint
administrativo `GET /api/v1/reviews/admin/fraude/estado-analisis`.
