# Correcciones del flujo de instalación

Fecha: 25 de agosto de 2026

## Reporte recibido

Al instalar la rama sobre una base creada previamente se observaron estos problemas:

- `seed_mongo_events.py` terminaba con `NameError` por no importar `datetime`.
- `verify_setup.py` no encontraba el índice único `uidx_evento_outbox`.
- Las 65 proyecciones comerciales de MongoDB aparecían divergentes frente a MySQL.
- El administrador de prueba no podía iniciar sesión en el equipo que realizó la revisión.

## Causas

1. El generador de historial importaba `timedelta`, pero usaba también `datetime`.
2. El índice del outbox estaba en el archivo de inicialización de MongoDB y en el arranque de FastAPI, pero la verificación se ejecutaba antes de iniciar la API. Los archivos de inicialización de Docker tampoco se repiten sobre volúmenes existentes.
3. La migración inicial escribía `disponible`, pero no el valor numérico `stock`, y no existía un paso explícito que proyectara todas las ofertas creadas por el backfill.
4. El instalador no comprobaba el código de salida del generador ni del verificador, por lo que podía continuar después de un error.
5. El instalador intentaba localizar Python global antes de reutilizar el entorno virtual existente.
6. En una base ya migrada, repetir todas las migraciones no era apropiado porque la tabla SQL heredada de productos ya había sido retirada.

## Solución aplicada

- Se corrigió la importación de `datetime`.
- El generador de eventos ahora completa solamente los productos sin historial. Ya no elimina eventos salvo que se solicite explícitamente `--reset`.
- Se agregó `sync_mongo_projections.py`, que instala los índices de ejecución y sincroniza precio, moneda, stock, disponibilidad, vendedor, oferta principal y cantidad de ofertas.
- La sincronización es idempotente y no elimina documentos ni eventos.
- El migrador inicial ahora escribe `stock` desde el primer momento.
- Se agregó `detect_schema_state.py` para distinguir un esquema heredado de uno que ya completó la migración.
- `setup.ps1` aplica la migración incremental cuando detecta el esquema heredado y la omite de forma segura cuando detecta el modelo final.
- `setup.ps1` comprueba el resultado de cada comando y se detiene ante cualquier error real.
- El instalador reutiliza `backend\venv` cuando ya existe.
- `verify_setup.py` valida la existencia, estado, contraseña documentada y rol del administrador de prueba.
- Se agregaron pruebas de regresión específicas para el seed, el índice y las proyecciones.

## Validación realizada

```text
Esquema detectado: final
Proyecciones encontradas: 65/65
Primera sincronización: 65 actualizadas
Segunda sincronización: 0 actualizadas
Productos con historial: 65/65
Eventos conservados: 479
Administrador: activo, contraseña válida y rol administrador
Referencias huérfanas: 0
Proyecciones divergentes: 0
Pruebas automatizadas: 34 passed
Frontend: compilación de producción correcta
```

También se ejecutó `setup.ps1 -SkipDocker -SkipFrontend` sobre el esquema final. El instalador reconoció el estado existente, evitó repetir el corte y finalizó con `[OK] Setup completo`.

## Instrucciones para actualizar una instalación existente

Desde la rama de revisión:

```powershell
git switch revision-modelo-relacional-ferxo
git pull
powershell -ExecutionPolicy Bypass -File ".\scripts\setup.ps1"
powershell -ExecutionPolicy Bypass -File ".\scripts\start-dev.ps1"
```

El proceso conserva los datos existentes. No es necesario borrar los volúmenes de Docker.

Credenciales esperadas:

```text
Administrador: admin@tiendaya.gt / password123
Comprador: comprador1@gmail.com / password123
Vendedor: vendedor1@tiendaya.gt / password123
```

Si la verificación indica que la credencial administrativa no coincide, se debe compartir la salida exacta del instalador. El script no reemplaza silenciosamente contraseñas existentes.
