param()

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$compose = Join-Path $root 'docker-compose.demo.yml'
$runtime = Join-Path (Split-Path -Parent $root) '_runtime\tiendaya-demo'
$manifestPath = Join-Path $runtime 'presentation-processes.json'
$envFile = Join-Path $root 'backend\.env.demo'

# Proceso que escucha en un puerto local. En algunos equipos Windows reporta el socket que
# escucha con estado CLOSED aunque atiende conexiones; se identifica por el extremo remoto
# vacío (0.0.0.0:0) y se prefiere el que está en Listen.
function Get-ListenerPid([int]$Port) {
    $conexion = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue |
        Where-Object { $_.RemotePort -eq 0 -and $_.OwningProcess -gt 0 } |
        Sort-Object { $_.State -ne 'Listen' } | Select-Object -First 1
    if ($conexion) { return [int]$conexion.OwningProcess } else { return $null }
}

if (-not (Test-Path -LiteralPath $manifestPath)) {
    throw 'No existe el registro de procesos de esta presentación; no se detendrá nada automáticamente.'
}
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
# Desde la Entrega final la presentación también registra el servicio de embeddings (8002);
# se acepta el registro anterior (sin 8002) de una presentación iniciada antes del cambio.
$expectedPorts = @($manifest.app.port | ForEach-Object { [int]$_ } | Sort-Object)
if (($expectedPorts -join ',') -notin @('5173,5174,8000,8001', '5173,5174,8000,8001,8002')) {
    throw 'El registro de procesos no coincide con la arquitectura de presentación.'
}

$runningDemo = @(docker ps --filter 'label=com.docker.compose.project=tiendaya_demo' --format '{{.Names}}')
if ($LASTEXITCODE -ne 0) { throw 'No se pudo verificar Docker; no se detendrá nada.' }
foreach ($service in @('mysql', 'mongo', 'redis', 'cassandra', 'neo4j', 'elasticsearch')) {
    $container = "tiendaya_demo_$service"
    if ($container -notin $runningDemo) { throw "No está activo $container; no se detendrá nada." }
    $mounts = @(docker inspect $container --format '{{range .Mounts}}{{println .Name}}{{end}}')
    $suffix = switch ($service) {
        'mysql' { 'mysql_data' } 'mongo' { 'mongo_data' } 'redis' { 'redis_data' }
        'cassandra' { 'cassandra_data' } 'neo4j' { 'neo4j_data' }
        'elasticsearch' { 'es_data' }
    }
    if ("tiendaya_demo_demo_$suffix" -notin $mounts) {
        throw "$container no utiliza el volumen original; no se detendrá nada."
    }
}

$patterns = @{
    5173 = 'vite\.js.*--port\s+5173'
    5174 = 'vite\.js.*--port\s+5174'
    8000 = 'uvicorn app\.main:app.*--port 8000'
    8001 = 'uvicorn payment_simulator\.app:app.*--port 8001'
    8002 = 'uvicorn embeddings_service\.app:app.*--port 8002'
}
foreach ($entry in $manifest.app) {
    $port = [int]$entry.port
    $listenerPid = Get-ListenerPid $port
    if (-not $listenerPid -or $listenerPid -ne [int]$entry.pid) {
        throw "El puerto $port ya no pertenece al proceso registrado; no se detendrá nada."
    }
    $process = Get-CimInstance Win32_Process -Filter "ProcessId=$($entry.pid)"
    if (-not $process -or $process.CommandLine -notmatch $patterns[$port] -or
        $process.CreationDate.ToUniversalTime().Ticks -ne ([datetime]$entry.created).ToUniversalTime().Ticks) {
        throw "El proceso del puerto $port no coincide con el registrado; no se detendrá nada."
    }
    # Ruta real del repositorio: el clon puede no llamarse ProyectoDB2_Guichos.
    if ($port -eq 5173 -and $process.CommandLine -notlike "*$(Join-Path $root 'frontend')*") {
        throw 'Frontend no reconocido; no se detendrá nada.'
    }
    if ($port -eq 5174 -and $process.CommandLine -notlike "*$(Join-Path $root 'laboratorio')*") {
        throw 'Laboratorio no reconocido; no se detendrá nada.'
    }
}

$outbox = Get-CimInstance Win32_Process -Filter "ProcessId=$($manifest.outbox_launcher)"
if (-not $outbox -or $outbox.CommandLine -notmatch 'scripts[\\/]run_demo_outbox\.py') {
    throw 'El Outbox no coincide con el registrado; no se detendrá nada.'
}
$outboxChildren = @(Get-CimInstance Win32_Process | Where-Object {
    $_.ParentProcessId -eq $outbox.ProcessId -and $_.CommandLine -match 'scripts[\\/]run_demo_outbox\.py'
})
foreach ($process in $outboxChildren) { Stop-Process -Id $process.ProcessId -ErrorAction SilentlyContinue }
Stop-Process -Id $outbox.ProcessId -ErrorAction SilentlyContinue
# Recuperación del checkout (solo en registros de presentaciones que la incluyen).
if ($manifest.recovery_launcher) {
    $recovery = Get-CimInstance Win32_Process -Filter "ProcessId=$($manifest.recovery_launcher)"
    if ($recovery -and $recovery.CommandLine -match 'scripts[\\/]run_demo_recovery\.py') {
        Stop-Process -Id $recovery.ProcessId -ErrorAction SilentlyContinue
    }
}
foreach ($entry in $manifest.app) { Stop-Process -Id $entry.pid -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 2
foreach ($port in $expectedPorts) {
    if (Get-ListenerPid $port) {
        throw "El puerto $port continúa ocupado; los motores permanecen encendidos."
    }
}
& docker compose -f $compose --env-file $envFile --project-name tiendaya_demo stop --timeout 60
if ($LASTEXITCODE -ne 0) { throw 'No se pudieron detener todos los motores DEMO.' }
Write-Host 'Presentación detenida. Los seis volúmenes originales se conservaron.' -ForegroundColor Green
