# Instalar una DEMO independiente en el equipo de Michael

Esta guía crea datos **sintéticos nuevos**. No copia ni modifica los volúmenes
originales de otra computadora, ni sirve para reconstruir la DEMO histórica.
Rama: `feature/fraude-automatico`. `medium` es el único perfil aceptado por el
instalador; `full` todavía requiere una validación aislada propia.

## Requisitos

Windows con PowerShell, Docker Desktop con WSL2, Python 3, Node.js con npm,
al menos 8 GB de RAM **libre** y 15 GB de disco libre antes de instalar.
La pila DEMO consume varios GB adicionales. El instalador comprueba Docker,
herramientas, puertos y recursos antes de crear bases; no apaga procesos ajenos.
Mantener apagada la instancia PRINCIPAL. No usar datos personales reales.

## Primera instalación (una sola vez)

```powershell
git clone -b feature/fraude-automatico https://github.com/MynitorBa/ProyectoDB2_Guichos.git
cd .\ProyectoDB2_Guichos
Copy-Item backend\.env.demo.example backend\.env.demo
```

Revisar `backend/.env.demo`: debe conservar `TIENDAYA_DEMO=true`, los puertos
DEMO 3317/27117/6389/9142/7787/9210 y los nombres terminados en `_demo`.
Cambiar `SECRET_KEY` por un valor local privado. Si se cambian las contraseñas
del ejemplo, `MYSQL_PASSWORD`, la contraseña del URI MongoDB y
`NEO4J_PASSWORD` deben ser coherentes con la instalación Docker nueva. No
publicar este archivo. Nunca usar `backend/.env` de PRINCIPAL.

```powershell
.\scripts\prepare-presentation-data.ps1 -PreflightOnly
.\scripts\prepare-presentation-data.ps1
```

El proceso instala dependencias, inicia seis motores aislados, aplica las
migraciones oficiales, carga `medium`, construye proyecciones, crea un
`payment_simulator/ledger.demo.db` **vacío**, ejecuta una vez el análisis de
fraude y comprueba el resultado. El ledger vacío es deliberado: los pagos
históricos sintéticos están en MySQL y no se presentan falsamente como cobros
realizados por la pasarela en esta máquina. Las compras nuevas por checkout sí
se registrarán en SQLite con su clave de idempotencia. El archivo SQLite está
excluido de Git.

El reporte de solo lectura se guarda fuera del repositorio en
`../_runtime/tiendaya-demo/reporte-presentacion.json`. Debe decir
`"resultado": "OK"` y mostrar al menos 5 F01, 5 F02, 10 F03, 20 F04, 5 F05,
5 F06 y 5 F07. También incluye conteos comerciales, errores de relaciones y
conteos de las seis proyecciones. Los identificadores de ejemplo permiten
abrir casos concretos en el panel Admin.

La instalación inicial no arranca automáticamente el frontend ni el
laboratorio. Una vez validada:

```powershell
.\scripts\start-presentation.ps1
```

| Aplicación | Dirección |
|---|---|
| Tienda | http://localhost:5173 |
| Laboratorio | http://localhost:5174 |
| API | http://localhost:8000/docs |
| Pasarela | http://localhost:8001/docs |

El administrador académico semilla usa `admin@tiendaya.gt`; consulte las
credenciales de prueba en el README del proyecto. El worker horario y la
inyección de fallas permanecen apagados en la
presentación; el worker Outbox sí sincroniza eventos. Cambiar esa contraseña
si la DEMO se expone fuera de localhost.

## Días siguientes y apagado

No repetir la preparación ni el seed. Usar solo:

```powershell
.\scripts\start-presentation.ps1
.\scripts\stop-presentation.ps1
```

El apagado conserva contenedores, volúmenes, datos y ledger. No ejecutar
`docker compose down -v`.

## Si una instalación falla

El instalador se bloquea al detectar cualquier volumen, contenedor o ledger
DEMO. Esto evita que un segundo intento duplique pedidos o cobros. Conservar
los datos y el mensaje de error; revisar `docker compose -f
docker-compose.demo.yml --project-name tiendaya_demo ps` y la tabla
`demo_seed_runs` antes de decidir cómo reanudar. `seed_demo_large.py` posee
claves deterministas, pero una ejecución interrumpida puede haber dejado
proyecciones o pagos parciales: **no** reiniciar a ciegas. La recuperación
segura requiere auditar ese estado, respaldarlo y volver a verificarlo; nunca
reemplazar volúmenes sin respaldo y autorización.

## Estado de validación

El código y el preflight pueden probarse sin tocar las bases de esta
computadora. La instalación end-to-end y los mínimos F01–F07 **deben ejecutarse
y verificarse en una máquina DEMO nueva** antes de afirmar que el dataset de
Michael está listo. `full` no está certificado. El perfil histórico descrito
en `docs/38-validacion-seed-medium-fraude.md` se generó con otra versión del
seed y no prueba automáticamente esta versión.
