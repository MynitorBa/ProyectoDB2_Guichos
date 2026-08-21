# =============================================================================
# TiendaYa — Resetear base de datos desde cero
# ADVERTENCIA: borra todos los datos.
# =============================================================================
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "ADVERTENCIA: Esto borrará todos los datos y volúmenes." -ForegroundColor Red
$confirm = Read-Host "Escribe 'si' para continuar"
if ($confirm -ne "si") { Write-Host "Cancelado."; exit }

Write-Host "Bajando contenedores y borrando volúmenes..." -ForegroundColor Yellow
docker compose down -v

Write-Host "Levantando de nuevo..." -ForegroundColor Yellow
docker compose up -d

Write-Host "Esperando MySQL..."
Start-Sleep 30

Write-Host "Re-ejecutando setup..."
& "$Root\scripts\setup.ps1"
