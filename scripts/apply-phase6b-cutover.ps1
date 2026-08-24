$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root 'backend\venv\Scripts\python.exe'

if (-not (Test-Path $Python)) {
    throw 'No existe el entorno virtual del backend. Ejecuta scripts\setup.ps1.'
}

Push-Location (Join-Path $Root 'backend')
try {
    & $Python 'scripts\apply_phase6b_cutover.py'
    if ($LASTEXITCODE -ne 0) {
        throw 'El corte físico 6B no pudo completarse.'
    }
} finally {
    Pop-Location
}
