# Migra el índice de búsqueda de la DEMO al mapping v2 (con vectores) — Entrega final.
#
# Crea un índice nuevo con el vector de cada producto, mueve el alias productos_demo y
# borra el anterior; la búsqueda no se interrumpe. Si el índice ya es v2, solo sincroniza.
# Usa el usuario indexador de la DEMO (el backend no puede crear índices) y el servicio de
# embeddings; si este no está corriendo, lo levanta solo mientras dura la migración.
#
# Requisitos: motores DEMO activos y .\scripts\configurar-acceso-demo.ps1 ya ejecutado.
# Uso:  .\scripts\migrar-indice-demo.ps1

$ErrorActionPreference = 'Stop'
$Root = Split-Path $PSScriptRoot -Parent
$EnvDemo = Join-Path $Root 'backend\.env.demo'
$Python = Join-Path $Root 'backend\venv\Scripts\python.exe'
. "$PSScriptRoot\credenciales-comun.ps1"

if (-not (Test-Path $EnvDemo)) { throw 'Falta backend\.env.demo.' }
$demo = Read-EnvFile $EnvDemo
if ($demo['TIENDAYA_DEMO'] -ne 'true' -or $demo['ES_INDEX_ALIAS'] -ne 'productos_demo') {
    throw 'backend\.env.demo no identifica el entorno DEMO.'
}
if (-not $demo['DEMO_ES_INDEXADOR_PASSWORD']) { throw 'Ejecute primero .\scripts\configurar-acceso-demo.ps1' }

# Configuración de la DEMO para este proceso, con el usuario indexador.
foreach ($nombre in $demo.Keys) { [Environment]::SetEnvironmentVariable($nombre, $demo[$nombre], 'Process') }
$env:ES_USERNAME = 'tiendaya_indexador'
$env:ES_PASSWORD = $demo['DEMO_ES_INDEXADOR_PASSWORD']

$embeddingsPropio = $null
if (-not (Get-NetTCPConnection -LocalPort 8002 -State Listen -ErrorAction SilentlyContinue)) {
    Write-Host '  Levantando el servicio de embeddings durante la migración...' -ForegroundColor Yellow
    $embeddingsPropio = Start-Process -FilePath $Python -ArgumentList '-m', 'uvicorn', 'embeddings_service.app:app',
        '--host', '127.0.0.1', '--port', '8002' -WorkingDirectory $Root -WindowStyle Hidden -PassThru
}
try {
    $limite = (Get-Date).AddMinutes(5)
    do {
        try { $listo = (Invoke-RestMethod 'http://127.0.0.1:8002/health' -TimeoutSec 3).listo } catch { $listo = $false }
        if (-not $listo) { Start-Sleep 2 }
    } while (-not $listo -and (Get-Date) -lt $limite)
    if (-not $listo) { throw 'El servicio de embeddings no quedó listo.' }

    Push-Location (Join-Path $Root 'backend')
    try {
        & $Python scripts\reindex_search.py
        if ($LASTEXITCODE -ne 0) { throw 'Falló la migración del índice DEMO.' }
    } finally { Pop-Location }
} finally {
    if ($embeddingsPropio) { Stop-Process -Id $embeddingsPropio.Id -ErrorAction SilentlyContinue }
}
Write-Host '  Índice DEMO en v2 con vectores.' -ForegroundColor Green
