$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root 'backend\venv\Scripts\python.exe'
$Backend = Join-Path $Root 'backend'
$Frontend = Join-Path $Root 'frontend'
$ErrorActionPreference = 'Stop'

if (-not (Test-Path $Python)) {
    throw 'No existe backend\venv. Ejecuta primero scripts\setup.ps1.'
}

Write-Host '[1/6] Verificando el backend TiendaYa en :8000...' -ForegroundColor Cyan
$listeners = @(Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue)
$backendPids = @($listeners | Select-Object -ExpandProperty OwningProcess -Unique)
$backendWasRunning = $backendPids.Count -gt 0
if ($backendPids.Count -gt 0) {
    try {
        $openApi = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/openapi.json' -TimeoutSec 5
    } catch {
        throw 'Hay un proceso en el puerto 8000, pero no fue posible identificar su API.'
    }
    if ($openApi.info.title -ne 'TiendaYa API') {
        throw "El puerto 8000 no corresponde a TiendaYa: $($openApi.info.title)"
    }
    Write-Host '  TiendaYa API identificada; el corte pendiente se aplicará en línea.' -ForegroundColor Green
}

try {
    Write-Host '[2/6] Respaldando, validando MongoDB y aplicando el corte...' -ForegroundColor Cyan
    Push-Location $Backend
    try {
        & $Python 'scripts\apply_phase6b_cutover.py'
        if ($LASTEXITCODE -ne 0) { throw 'La migración se detuvo sin completar el corte.' }

        Write-Host '[3/6] Ejecutando las pruebas de regresion...' -ForegroundColor Cyan
        & $Python -m pytest tests -q
        if ($LASTEXITCODE -ne 0) { throw 'Fallaron pruebas después del corte.' }

        Write-Host '[4/6] Verificando MySQL y MongoDB...' -ForegroundColor Cyan
        & $Python 'scripts\verify_setup.py'
        if ($LASTEXITCODE -ne 0) { throw 'Falló el verificador integral.' }
    } finally {
        Pop-Location
    }

    Write-Host '[5/6] Compilando el frontend...' -ForegroundColor Cyan
    Push-Location $Frontend
    try {
        npm run build
        if ($LASTEXITCODE -ne 0) { throw 'Falló la compilación del frontend.' }
    } finally {
        Pop-Location
    }
} finally {
    $activeBackend = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
    if (-not $activeBackend) {
        Write-Host '[6/6] Iniciando FastAPI en segundo plano...' -ForegroundColor Cyan
        Start-Process -FilePath $Python `
            -ArgumentList '-m','uvicorn','app.main:app','--reload','--host','0.0.0.0','--port','8000' `
            -WorkingDirectory $Backend -WindowStyle Hidden
    } else {
        Write-Host '[6/6] FastAPI permaneció en línea; no se inicia otra instancia.' -ForegroundColor Green
    }
}

Start-Sleep -Seconds 3
$response = Invoke-WebRequest -Uri 'http://127.0.0.1:8000/health' -UseBasicParsing
if ($response.StatusCode -ne 200) { throw 'El backend no respondió correctamente.' }

Write-Host 'Fase 6B completada y TiendaYa nuevamente en línea.' -ForegroundColor Green
