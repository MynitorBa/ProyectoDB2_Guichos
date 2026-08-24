# =============================================================================
# TiendaYa — Aplicar Fase 1 de integridad sobre una base MySQL existente
# No elimina datos. El SQL aborta antes de agregar FKs si detecta huérfanos.
# =============================================================================

$Root = Split-Path -Parent $PSScriptRoot
$ErrorActionPreference = 'Stop'

Set-Location $Root

Write-Host 'Aplicando Fase 1 de integridad...' -ForegroundColor Cyan

$Python = Join-Path $Root 'backend\venv\Scripts\python.exe'
$Runner = Join-Path $Root 'backend\scripts\apply_phase1_integrity.py'

if (-not (Test-Path -LiteralPath $Python)) {
    throw 'No existe el entorno Python del backend. Ejecuta primero scripts\setup.ps1.'
}

& $Python $Runner

if ($LASTEXITCODE -ne 0) {
    throw 'La migración fue abortada. Revisa el error anterior.'
}

& $Python (Join-Path $Root 'backend\scripts\verify_setup.py')

if ($LASTEXITCODE -ne 0) {
    throw 'La migración terminó, pero la verificación integral encontró problemas.'
}
