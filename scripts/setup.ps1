# =============================================================================
# TiendaYa — Script de configuración inicial
# Ejecutar desde la raíz del proyecto: .\scripts\setup.ps1
# =============================================================================
param(
  [switch]$SkipDocker,
  [switch]$SkipFrontend
)

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$ErrorActionPreference = "Stop"

Write-Host "`n==========================================" -ForegroundColor Cyan
Write-Host " TiendaYa - Setup inicial" -ForegroundColor Cyan
Write-Host "==========================================`n" -ForegroundColor Cyan

# ── 1. Verificar Python ───────────────────────────────────────────────────────
$ExistingVenvPython = "$Root\backend\venv\Scripts\python.exe"
$LocalPython = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
if (Test-Path $ExistingVenvPython) {
    $PythonExe = $ExistingVenvPython
} elseif (Test-Path $LocalPython) {
    $PythonExe = $LocalPython
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $PythonExe = "python"
} else {
    $PythonExe = $null
}
Write-Host "[1/8] Python: " -NoNewline
if ($PythonExe) {
    $pyver = & $PythonExe --version 2>&1
    Write-Host $pyver -ForegroundColor Green
} else {
    Write-Host "No encontrado. Instalando..." -ForegroundColor Yellow
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw 'Python 3.12 no está instalado y winget no está disponible. Instala Python manualmente y repite el setup.'
    }
    winget install Python.Python.3.12 --accept-package-agreements --accept-source-agreements
    $PythonExe = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
}

# ── 2. Levantar Docker ────────────────────────────────────────────────────────
if (-not $SkipDocker) {
    Write-Host "`n[2/8] Levantando contenedores Docker..." -ForegroundColor Cyan

    # Copiar .env.example si no existe .env
    if (-not (Test-Path "$Root\.env")) {
        Copy-Item "$Root\.env.example" "$Root\.env"
        Write-Host "  Copiado .env.example → .env"
    }
    # Contraseñas y usuarios de las bases NoSQL (se crean si faltan) y contenedores arriba.
    & "$PSScriptRoot\configurar-acceso.ps1"

    Write-Host "  Esperando que MySQL esté saludable..." -ForegroundColor Yellow
    $maxWait = 60
    $waited  = 0
    do {
        Start-Sleep 5
        $waited += 5
        $health = docker inspect --format='{{.State.Health.Status}}' tiendaya_mysql 2>$null
        Write-Host "  MySQL estado: $health ($waited s)" -ForegroundColor Gray
    } while ($health -ne "healthy" -and $waited -lt $maxWait)

    if ($health -ne "healthy") {
        Write-Host "  ADVERTENCIA: MySQL tardó más de lo esperado. Continúa de todos modos..." -ForegroundColor Yellow
    } else {
        Write-Host "  MySQL listo." -ForegroundColor Green
    }

    Write-Host "  Esperando MongoDB..." -ForegroundColor Yellow
    Start-Sleep 5
    $mongoHealth = docker inspect --format='{{.State.Health.Status}}' tiendaya_mongo 2>$null
    Write-Host "  MongoDB estado: $mongoHealth" -ForegroundColor Green

    Write-Host "  Esperando Redis..." -ForegroundColor Yellow
    $redisHealth = docker inspect --format='{{.State.Health.Status}}' tiendaya_redis 2>$null
    $redisWaited = 0
    while ($redisHealth -ne 'healthy' -and $redisWaited -lt 60) {
        Start-Sleep 2
        $redisWaited += 2
        $redisHealth = docker inspect --format='{{.State.Health.Status}}' tiendaya_redis 2>$null
    }
    if ($redisHealth -ne 'healthy') {
        throw 'Redis no estuvo disponible después de 60 segundos.'
    }
    Write-Host "  Redis listo." -ForegroundColor Green

    Write-Host "  Esperando Cassandra (el primer arranque puede tardar hasta 3 minutos)..." -ForegroundColor Yellow
    $cassandraHealth = docker inspect --format='{{.State.Health.Status}}' tiendaya_cassandra 2>$null
    $cassandraWaited = 0
    while ($cassandraHealth -ne 'healthy' -and $cassandraWaited -lt 180) {
        Start-Sleep 5
        $cassandraWaited += 5
        $cassandraHealth = docker inspect --format='{{.State.Health.Status}}' tiendaya_cassandra 2>$null
    }
    if ($cassandraHealth -ne 'healthy') {
        throw 'Cassandra no estuvo disponible después de 180 segundos.'
    }
    Write-Host "  Cassandra lista." -ForegroundColor Green

    Write-Host "  Esperando Neo4j..." -ForegroundColor Yellow
    $neo4jHealth = docker inspect --format='{{.State.Health.Status}}' tiendaya_neo4j 2>$null
    $neo4jWaited = 0
    while ($neo4jHealth -ne 'healthy' -and $neo4jWaited -lt 120) {
        Start-Sleep 5
        $neo4jWaited += 5
        $neo4jHealth = docker inspect --format='{{.State.Health.Status}}' tiendaya_neo4j 2>$null
    }
    if ($neo4jHealth -ne 'healthy') {
        throw 'Neo4j no estuvo disponible después de 120 segundos.'
    }
    Write-Host "  Neo4j listo." -ForegroundColor Green

    Write-Host "  Esperando Elasticsearch..." -ForegroundColor Yellow
    $esHealth = docker inspect --format='{{.State.Health.Status}}' tiendaya_elasticsearch 2>$null
    $esWaited = 0
    while ($esHealth -ne 'healthy' -and $esWaited -lt 180) {
        Start-Sleep 5
        $esWaited += 5
        $esHealth = docker inspect --format='{{.State.Health.Status}}' tiendaya_elasticsearch 2>$null
    }
    if ($esHealth -ne 'healthy') {
        throw 'Elasticsearch no estuvo disponible después de 180 segundos.'
    }
    Write-Host "  Elasticsearch listo." -ForegroundColor Green
} else {
    Write-Host "[2/8] Docker: OMITIDO" -ForegroundColor Gray
}

# ── 3. Configurar entorno Python ──────────────────────────────────────────────
Write-Host "`n[3/8] Configurando entorno Python..." -ForegroundColor Cyan
$venvPath = "$Root\backend\venv"
if (-not (Test-Path $venvPath)) {
    & $PythonExe -m venv $venvPath
    Write-Host "  Entorno virtual creado."
}

$pip = "$venvPath\Scripts\pip.exe"
$python = "$venvPath\Scripts\python.exe"

Write-Host "  Instalando dependencias Python..."
& $pip install -r "$Root\backend\requirements.txt" --quiet

# Copiar .env del backend
if (-not (Test-Path "$Root\backend\.env")) {
    Copy-Item "$Root\backend\.env.example" "$Root\backend\.env"
    Write-Host "  Copiado backend\.env.example → backend\.env"
}

Write-Host "  Python listo." -ForegroundColor Green

# Las migraciones de la instalación crean y modifican colecciones: corren con el dueño de la
# base (tiendaya_admin), no con el usuario del backend. Solo para este proceso; backend\.env
# conserva el usuario de menor privilegio.
$mongoUriBackend = (Get-Content "$Root\backend\.env" | Where-Object { $_ -match '^MONGO_URI=' } | Select-Object -Last 1) -replace '^MONGO_URI=', ''
$mongoAdminPass = (Get-Content "$Root\.env" | Where-Object { $_ -match '^MONGO_ADMIN_PASSWORD=' } | Select-Object -Last 1) -replace '^MONGO_ADMIN_PASSWORD=', ''
if ($mongoUriBackend -match 'tiendaya_api:' -and $mongoAdminPass) {
    $env:MONGO_URI = $mongoUriBackend -replace 'tiendaya_api:[^@]+@', "tiendaya_admin:$mongoAdminPass@"
}
# Igual con Elasticsearch: crear el índice y mover el alias es tarea del indexador.
$esIndexadorPass = (Get-Content "$Root\.env" | Where-Object { $_ -match '^ES_INDEXADOR_PASSWORD=' } | Select-Object -Last 1) -replace '^ES_INDEXADOR_PASSWORD=', ''
if ($esIndexadorPass) {
    $env:ES_USERNAME = 'tiendaya_indexador'
    $env:ES_PASSWORD = $esIndexadorPass
}

# ── 4. Migrar o reconocer el esquema instalado ───────────────────────────────
Write-Host "`n[4/8] Preparando modelo relacional y catálogo..." -ForegroundColor Cyan
Set-Location "$Root\backend"
$schemaState = (& $python scripts\detect_schema_state.py).Trim()
if ($LASTEXITCODE -ne 0) {
    throw 'No se pudo determinar el estado actual de MySQL.'
}

if ($schemaState -eq 'legacy') {
    Write-Host "  Esquema heredado detectado; aplicando migración incremental." -ForegroundColor Yellow

    & $python scripts\apply_phase1_integrity.py
    if ($LASTEXITCODE -ne 0) { throw 'Falló la corrección inicial de integridad.' }

    & $python scripts\apply_phase2_additive.py
    if ($LASTEXITCODE -ne 0) { throw 'Falló la creación de estructuras aditivas.' }

    & $python scripts\migrate_products_to_mongo.py
    if ($LASTEXITCODE -ne 0) { throw 'Falló la migración del catálogo hacia MongoDB.' }

    & $python scripts\apply_phase3_backfill.py
    if ($LASTEXITCODE -ne 0) { throw 'Falló el backfill de ofertas e inventario.' }

    & $python scripts\apply_phase4_dual_read.py
    if ($LASTEXITCODE -ne 0) { throw 'Falló la preparación del carrito por oferta.' }

    & $python scripts\apply_phase6b_additive.py
    if ($LASTEXITCODE -ne 0) { throw 'Falló la preparación del corte de productos SQL.' }

    & $python scripts\apply_phase6b_cutover.py
    if ($LASTEXITCODE -ne 0) { throw 'Falló el retiro del esquema heredado.' }

    & $python scripts\apply_phase7_reference_integrity.py
    if ($LASTEXITCODE -ne 0) { throw 'Falló la integridad entre categorías, referencias y ofertas.' }
} elseif ($schemaState -eq 'final') {
    Write-Host "  Esquema final detectado; no se repetirán migraciones destructivas." -ForegroundColor Green
} else {
    throw "Estado de esquema desconocido: $schemaState"
}

# Esta extensión es aditiva e idempotente, tanto para instalaciones migradas
# como para instancias que ya estaban en el esquema final.
& $python scripts\apply_catalog_extensions.py
if ($LASTEXITCODE -ne 0) {
    throw 'Falló la instalación de imágenes SQL y categorías múltiples.'
}

& $python scripts\apply_catalog_requests.py
if ($LASTEXITCODE -ne 0) {
    throw 'Falló la instalación del flujo de solicitudes de vendedores.'
}

& $python scripts\apply_offer_temporal_history.py
if ($LASTEXITCODE -ne 0) {
    throw 'Falló la instalación del historial temporal de ofertas.'
}

& $python scripts\apply_dynamic_variants.py
if ($LASTEXITCODE -ne 0) {
    throw 'Falló la instalación del registro de variantes dinámicas.'
}

& $python scripts\apply_unique_nombre_tiendaya.py
if ($LASTEXITCODE -ne 0) {
    throw 'Falló la migración de unicidad de nombre y columna es_tiendaya.'
}

# apply_fulfillment importa el modelo ORM actual de Pedido. En una base que
# todavía no recibió la migración 20, ese modelo ya espera las columnas de la
# saga y la consulta de compatibilidad falla antes de que setup pueda crearlas.
# La migración es aditiva e idempotente, por lo que debe instalarse antes de
# cualquier script que cargue el modelo actual de pedidos.
& $python scripts\apply_checkout_saga.py
if ($LASTEXITCODE -ne 0) { throw 'Falló la instalación del checkout como saga.' }

& $python scripts\apply_fulfillment.py
if ($LASTEXITCODE -ne 0) { throw 'Falló la migración de envíos parciales y solicitudes de variantes.' }

& $python scripts\migrate_cart_to_redis.py
if ($LASTEXITCODE -ne 0) { throw 'Falló la migración idempotente de carritos a Redis.' }

& $python scripts\apply_flash_sales.py
if ($LASTEXITCODE -ne 0) { throw 'Falló la instalación de ventas flash.' }

& $python scripts\apply_outbox_v2.py
if ($LASTEXITCODE -ne 0) { throw 'Falló la instalación del outbox por destino.' }

& $python scripts\apply_review_authority.py
if ($LASTEXITCODE -ne 0) { throw 'Falló la migración durable de reseñas.' }

& $python scripts\apply_fraud_alerts.py
if ($LASTEXITCODE -ne 0) { throw 'Falló la instalación del expediente de alertas de fraude.' }

& $python scripts\apply_fraud_automation.py
if ($LASTEXITCODE -ne 0) { throw 'Falló la instalación de automatización de fraude.' }

& $python scripts\apply_respaldo_redis.py
if ($LASTEXITCODE -ne 0) { throw 'Falló la instalación del respaldo de Redis en MySQL.' }

& $python scripts\apply_respaldo_catalogo.py
if ($LASTEXITCODE -ne 0) { throw 'Falló la instalación de la copia del catálogo en MySQL.' }

& $python scripts\sync_catalogo_respaldo.py
if ($LASTEXITCODE -ne 0) { throw 'Falló la copia inicial del catálogo en MySQL.' }

& $python scripts\apply_recomendaciones_cache.py
if ($LASTEXITCODE -ne 0) { throw 'Falló la instalación de la caché de recomendaciones.' }

& $python scripts\apply_respaldo_analitica.py
if ($LASTEXITCODE -ne 0) { throw 'Falló la instalación del respaldo analítico MySQL.' }
& $python scripts\backfill_mysql_analytics.py --apply-if-needed
if ($LASTEXITCODE -ne 0) { throw 'Falló la proyección analítica inicial en MySQL.' }

& $python scripts\backfill_cassandra_analytics.py
if ($LASTEXITCODE -ne 0) { throw 'Falló la proyección analítica inicial en Cassandra.' }

# ── 5. Sincronizar MongoDB ────────────────────────────────────────────────────
Write-Host "`n[5/8] Instalando índices y sincronizando proyecciones MongoDB..." -ForegroundColor Cyan
& $python scripts\sync_mongo_projections.py
if ($LASTEXITCODE -ne 0) {
    throw 'No se pudieron sincronizar las proyecciones comerciales de MongoDB.'
}
Write-Host "  Proyecciones e índices sincronizados." -ForegroundColor Green

# Reconcilia atributos históricos con los esquemas actuales. Es idempotente y
# crea un respaldo antes de modificar cualquier documento.
& $python scripts\repair_catalog_data.py --apply
if ($LASTEXITCODE -ne 0) {
    throw 'No se pudieron reconciliar los atributos históricos del catálogo.'
}

# Corrige nombres guardados con doble codificación UTF-8 antes de indexarlos.
# No modifica SKU ni el historial de eventos; respalda antes de escribir.
& $python scripts\repair_text_encoding.py --apply
if ($LASTEXITCODE -ne 0) {
    throw 'No se pudo reparar el texto mal codificado del catálogo.'
}

Write-Host "`n[6/8] Completando historial faltante en MongoDB..." -ForegroundColor Cyan
& $python scripts\repair_mongo_product_history.py --apply
if ($LASTEXITCODE -ne 0) {
    throw 'No se pudo separar el historial documental del historial operativo.'
}
& $python scripts\seed_mongo_events.py
if ($LASTEXITCODE -ne 0) {
    throw 'No se pudo completar el historial de productos.'
}
Write-Host "  Historial verificado." -ForegroundColor Green

# Neo4j es una proyección reconstruible. Conserva las compras y reseñas reales
# del esquema heredado; no utiliza el generador de datos de demostración.
Write-Host "  Reconstruyendo compras y reseñas reales en Neo4j..." -ForegroundColor Yellow
& $python scripts\backfill_neo4j_reviews.py --apply
if ($LASTEXITCODE -ne 0) {
    throw 'No se pudo reconstruir la proyección de compras y reseñas en Neo4j.'
}

# El índice de búsqueda es una proyección: se crea si falta y se sincroniza
# con el estado actual de MongoDB, MySQL y Neo4j. Es idempotente.
Write-Host "  Construyendo índice de búsqueda en Elasticsearch..." -ForegroundColor Yellow
& $python scripts\reindex_search.py
if ($LASTEXITCODE -ne 0) {
    throw 'No se pudo construir el índice de búsqueda en Elasticsearch.'
}
Write-Host "  Índice de búsqueda listo." -ForegroundColor Green

Set-Location $Root

# ── 6. Verificar integridad ───────────────────────────────────────────────────
Write-Host "`n[7/8] Verificando integridad del sistema..." -ForegroundColor Cyan
Set-Location "$Root\backend"
# La verificación final usa la configuración real del backend (su propio usuario).
Remove-Item Env:MONGO_URI, Env:ES_USERNAME, Env:ES_PASSWORD -ErrorAction SilentlyContinue
& $python scripts\verify_setup.py
if ($LASTEXITCODE -ne 0) {
    throw 'La verificación final detectó errores; la instalación no está completa.'
}
Set-Location $Root

# ── 7. Instalar dependencias del frontend ─────────────────────────────────────
if (-not $SkipFrontend) {
    Write-Host "`n[8/8] Instalando dependencias del frontend..." -ForegroundColor Cyan
    Set-Location "$Root\frontend"

    if (-not (Test-Path "$Root\frontend\.env")) {
        Copy-Item "$Root\frontend\.env.example" "$Root\frontend\.env"
    }

    node --version
    npm install
    Write-Host "  Frontend listo." -ForegroundColor Green

    # Laboratorio de consistencia: herramienta de desarrollo aparte de la tienda.
    Set-Location "$Root\laboratorio"
    npm install
    Write-Host "  Laboratorio de consistencia listo (se usa con FAULT_INJECTION_ENABLED=true)." -ForegroundColor Green
    Set-Location $Root
} else {
    Write-Host "[8/8] Frontend: OMITIDO" -ForegroundColor Gray
}

# ── Resumen ───────────────────────────────────────────────────────────────────
Write-Host "`n==========================================" -ForegroundColor Green
Write-Host " Setup completo. Credenciales de prueba:" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Admin:      admin@tiendaya.gt     / password123" -ForegroundColor Yellow
Write-Host "  Comprador:  comprador1@gmail.com  / password123" -ForegroundColor Yellow
Write-Host "  Vendedor:   vendedor1@tiendaya.gt / password123" -ForegroundColor Yellow
Write-Host ""
Write-Host "  Ahora ejecuta: .\scripts\start-dev.ps1" -ForegroundColor Cyan
Write-Host ""
