$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root 'backend\venv\Scripts\python.exe'
$Backend = Join-Path $Root 'backend'
$Frontend = Join-Path $Root 'frontend'
$ErrorActionPreference = 'Stop'

if (-not (Test-Path $Python)) {
    throw 'No existe backend\venv. Ejecuta primero scripts\setup.ps1.'
}

Write-Host '[1/5] Respaldando y enlazando categorias, referencias y ofertas...' -ForegroundColor Cyan
Push-Location $Backend
try {
    & $Python 'scripts\apply_phase7_reference_integrity.py'
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo aplicar la migracion de integridad.' }

    Write-Host '[2/5] Ejecutando pruebas de backend y bases de datos...' -ForegroundColor Cyan
    & $Python -m pytest tests -q
    if ($LASTEXITCODE -ne 0) { throw 'Fallaron las pruebas despues de la migracion.' }

    Write-Host '[3/5] Verificando MySQL y MongoDB...' -ForegroundColor Cyan
    & $Python 'scripts\verify_setup.py'
    if ($LASTEXITCODE -ne 0) { throw 'Fallo el verificador integral.' }
} finally {
    Pop-Location
}

Write-Host '[4/5] Compilando el frontend...' -ForegroundColor Cyan
Push-Location $Frontend
try {
    npm run build
    if ($LASTEXITCODE -ne 0) { throw 'Fallo la compilacion del frontend.' }
} finally {
    Pop-Location
}

Write-Host '[5/5] Comprobando la API TiendaYa...' -ForegroundColor Cyan
$health = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/health' -TimeoutSec 10
if ($health.status -ne 'ok') { throw 'El backend no respondio con estado saludable.' }

Write-Host 'Fase 7 aplicada y validada completamente.' -ForegroundColor Green
