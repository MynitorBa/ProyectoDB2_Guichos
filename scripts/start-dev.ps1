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
