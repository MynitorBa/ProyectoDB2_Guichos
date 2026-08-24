$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root 'backend\venv\Scripts\python.exe'

if (-not (Test-Path $Python)) {
    throw 'No existe backend\venv. Ejecuta primero scripts\setup.ps1.'
}

Push-Location (Join-Path $Root 'backend')
try {
    & $Python 'scripts\apply_phase7_reference_integrity.py'
    if ($LASTEXITCODE -ne 0) {
        throw 'No se pudo aplicar la integridad de referencias de la Fase 7.'
    }
} finally {
    Pop-Location
}
