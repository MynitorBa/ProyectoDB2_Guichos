# =============================================================================
# TiendaYa — Aplicar Fase 3 de backfill sobre la base activa
# Valida MongoDB, crea respaldo lógico y ejecuta verificación integral.
# =============================================================================

$Root = Split-Path -Parent $PSScriptRoot
$ErrorActionPreference = 'Stop'

Set-Location $Root

$Python = Join-Path $Root 'backend\venv\Scripts\python.exe'
$Runner = Join-Path $Root 'backend\scripts\apply_phase3_backfill.py'
$Verifier = Join-Path $Root 'backend\scripts\verify_setup.py'

if (-not (Test-Path -LiteralPath $Python)) {
    throw 'No existe el entorno Python del backend. Ejecuta primero scripts\setup.ps1.'
}

Write-Host 'Aplicando Fase 3 con respaldo y validaciones...' -ForegroundColor Cyan
& $Python $Runner
if ($LASTEXITCODE -ne 0) {
    throw 'La Fase 3 fue abortada. Revisa el error anterior.'
}

& $Python $Verifier
if ($LASTEXITCODE -ne 0) {
    throw 'El backfill terminó, pero la verificación integral encontró problemas.'
}
