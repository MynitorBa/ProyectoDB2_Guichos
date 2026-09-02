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

    docker compose up -d

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

Set-Location $Root

# ── 6. Verificar integridad ───────────────────────────────────────────────────
Write-Host "`n[7/8] Verificando integridad del sistema..." -ForegroundColor Cyan
Set-Location "$Root\backend"
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
