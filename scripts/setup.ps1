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
$PythonExe = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
if (-not (Test-Path $PythonExe)) {
    # Intentar encontrar Python en PATH
    $PythonExe = "python"
}
Write-Host "[1/7] Python: " -NoNewline
try {
    $pyver = & $PythonExe --version 2>&1
    Write-Host $pyver -ForegroundColor Green
} catch {
    Write-Host "No encontrado. Instalando..." -ForegroundColor Yellow
    winget install Python.Python.3.12 --accept-package-agreements --accept-source-agreements
    $PythonExe = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
}

# ── 2. Levantar Docker ────────────────────────────────────────────────────────
if (-not $SkipDocker) {
    Write-Host "`n[2/7] Levantando contenedores Docker..." -ForegroundColor Cyan

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
    Write-Host "[2/7] Docker: OMITIDO" -ForegroundColor Gray
}

# ── 3. Configurar entorno Python ──────────────────────────────────────────────
Write-Host "`n[3/7] Configurando entorno Python..." -ForegroundColor Cyan
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

# ── 4. Migrar productos a MongoDB ─────────────────────────────────────────────
Write-Host "`n[4/7] Migrando productos MySQL → MongoDB..." -ForegroundColor Cyan
Set-Location "$Root\backend"
try {
    & $python scripts\migrate_products_to_mongo.py --reset
    Write-Host "  Migración completada." -ForegroundColor Green
} catch {
    Write-Host "  ADVERTENCIA: Error en migración. Verifica las bases de datos." -ForegroundColor Yellow
    Write-Host "  $_"
}

# ── 5. Sembrar eventos de historial ───────────────────────────────────────────
Write-Host "`n[5/7] Sembrando historial de eventos en MongoDB..." -ForegroundColor Cyan
try {
    & $python scripts\seed_mongo_events.py
    Write-Host "  Eventos generados." -ForegroundColor Green
} catch {
    Write-Host "  ADVERTENCIA: Error al sembrar eventos." -ForegroundColor Yellow
    Write-Host "  $_"
}

Set-Location $Root

# ── 6. Verificar integridad ───────────────────────────────────────────────────
Write-Host "`n[6/7] Verificando integridad del sistema..." -ForegroundColor Cyan
Set-Location "$Root\backend"
try {
    & $python scripts\verify_setup.py
} catch {
    Write-Host "  Verificación con advertencias. Revisa la salida anterior." -ForegroundColor Yellow
}
Set-Location $Root

# ── 7. Instalar dependencias del frontend ─────────────────────────────────────
if (-not $SkipFrontend) {
    Write-Host "`n[7/7] Instalando dependencias del frontend..." -ForegroundColor Cyan
    Set-Location "$Root\frontend"

    if (-not (Test-Path "$Root\frontend\.env")) {
        Copy-Item "$Root\frontend\.env.example" "$Root\frontend\.env"
    }

    node --version
    npm install
    Write-Host "  Frontend listo." -ForegroundColor Green
    Set-Location $Root
} else {
    Write-Host "[7/7] Frontend: OMITIDO" -ForegroundColor Gray
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
