# =============================================================================
# TiendaYa — Arrancar el sistema en modo desarrollo
# Ejecutar: .\scripts\start-dev.ps1
# =============================================================================
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "`nArrancar TiendaYa..." -ForegroundColor Cyan

# 1. Contenedores Docker
Write-Host "Levantando contenedores..." -ForegroundColor Yellow
docker compose up -d

# Un pull puede incorporar migraciones aditivas nuevas. Aplicarlas aquí evita
# iniciar una API nueva contra un esquema anterior (la causa típica de 500 tras
# actualizar la rama). Las operaciones son idempotentes.
$python = "$Root\backend\venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw 'No existe el entorno Python. Ejecuta primero .\scripts\setup.ps1.'
}
Write-Host "Esperando MySQL y aplicando actualizaciones seguras..." -ForegroundColor Yellow
$ready = $false
for ($attempt = 1; $attempt -le 30; $attempt++) {
    $schemaState = & $python "$Root\backend\scripts\detect_schema_state.py" 2>$null
    if ($LASTEXITCODE -eq 0 -and $schemaState -in @('legacy', 'final')) {
        $ready = $true
        break
    }
    Start-Sleep -Seconds 2
}
if (-not $ready) { throw 'MySQL no estuvo disponible después de 60 segundos.' }
if ($schemaState -eq 'legacy') {
    throw 'Se detectó el esquema heredado. Ejecuta .\scripts\setup.ps1 para completar la migración.'
}
Push-Location "$Root\backend"
try {
    & $python scripts\apply_catalog_extensions.py
    if ($LASTEXITCODE -ne 0) { throw 'Falló la actualización de imágenes y categorías.' }
    & $python scripts\apply_catalog_requests.py
    if ($LASTEXITCODE -ne 0) { throw 'Falló la actualización de solicitudes de catálogo.' }
    & $python scripts\apply_unique_nombre_tiendaya.py
    if ($LASTEXITCODE -ne 0) { throw 'Falló la actualización de reglas del catálogo.' }
    & $python scripts\apply_fulfillment.py
    if ($LASTEXITCODE -ne 0) { throw 'Falló la actualización de envíos y variantes.' }
    & $python scripts\repair_catalog_data.py --apply
    if ($LASTEXITCODE -ne 0) { throw 'Falló la reconciliación de atributos.' }
} finally {
    Pop-Location
}

# 2. Backend (en proceso separado)
Write-Host "Iniciando backend FastAPI en :8000..." -ForegroundColor Yellow
$backendJob = Start-Process -FilePath "cmd" -ArgumentList "/c cd `"$Root\backend`" && `"$Root\backend\venv\Scripts\uvicorn.exe`" app.main:app --reload --host 0.0.0.0 --port 8000" -PassThru -WindowStyle Normal

# 3. Frontend (en proceso separado)
Write-Host "Iniciando frontend React en :5173..." -ForegroundColor Yellow
$frontendJob = Start-Process -FilePath "cmd" -ArgumentList "/c cd `"$Root\frontend`" && npm run dev" -PassThru -WindowStyle Normal

Start-Sleep 3

Write-Host "`n==========================================" -ForegroundColor Green
Write-Host " Sistema iniciado" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Frontend:     http://localhost:5173" -ForegroundColor Cyan
Write-Host "  Backend API:  http://localhost:8000/docs" -ForegroundColor Cyan
Write-Host "  Adminer:      http://localhost:8080  (server: mysql, user: tiendaya, pass: tiendaya123)" -ForegroundColor Cyan
Write-Host "  Mongo Express: http://localhost:8081" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Admin: admin@tiendaya.gt / password123" -ForegroundColor Yellow
Write-Host ""
Write-Host "Presiona Ctrl+C para detener los procesos (cierra las ventanas manualmente)." -ForegroundColor Gray
