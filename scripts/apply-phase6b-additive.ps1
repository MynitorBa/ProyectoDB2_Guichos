$Root = Split-Path -Parent $PSScriptRoot
$ErrorActionPreference = 'Stop'
$Python = Join-Path $Root 'backend\venv\Scripts\python.exe'
$Runner = Join-Path $Root 'backend\scripts\apply_phase6b_additive.py'
$Verifier = Join-Path $Root 'backend\scripts\verify_setup.py'

if (-not (Test-Path -LiteralPath $Python)) {
    throw 'No existe el entorno Python del backend.'
}

Set-Location (Join-Path $Root 'backend')
& $Python $Runner
if ($LASTEXITCODE -ne 0) {
    throw 'La Fase 6B aditiva fue abortada.'
}
& $Python $Verifier
if ($LASTEXITCODE -ne 0) {
    throw 'La migración terminó, pero la verificación encontró problemas.'
}
