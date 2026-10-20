param()

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$compose = Join-Path $root 'docker-compose.demo.yml'
$runtime = Join-Path (Split-Path -Parent $root) '_runtime\tiendaya-demo'
$manifestPath = Join-Path $runtime 'presentation-processes.json'

if (-not (Test-Path -LiteralPath $manifestPath)) {
    throw 'No existe el registro de procesos de esta presentación; no se detendrá nada automáticamente.'
}
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
$expectedPorts = @(5173, 5174, 8000, 8001)
if (@($manifest.app).Count -ne 4 -or @($manifest.app.port | Sort-Object) -join ',' -ne '5173,5174,8000,8001') {
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
}
foreach ($entry in $manifest.app) {
    $port = [int]$entry.port
    $listener = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $listener -or $listener.OwningProcess -ne [int]$entry.pid) {
        throw "El puerto $port ya no pertenece al proceso registrado; no se detendrá nada."
    }
    $process = Get-CimInstance Win32_Process -Filter "ProcessId=$($entry.pid)"
    if (-not $process -or $process.CommandLine -notmatch $patterns[$port] -or
        $process.CreationDate.ToUniversalTime().Ticks -ne ([datetime]$entry.created).ToUniversalTime().Ticks) {
        throw "El proceso del puerto $port no coincide con el registrado; no se detendrá nada."
    }
    if ($port -eq 5173 -and $process.CommandLine -notlike '*ProyectoDB2_Guichos\frontend*') {
        throw 'Frontend no reconocido; no se detendrá nada.'
    }
    if ($port -eq 5174 -and $process.CommandLine -notlike '*ProyectoDB2_Guichos\laboratorio*') {
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
foreach ($entry in $manifest.app) { Stop-Process -Id $entry.pid -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 2
foreach ($port in $expectedPorts) {
    if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) {
        throw "El puerto $port continúa ocupado; los motores permanecen encendidos."
    }
}
& docker compose -f $compose --project-name tiendaya_demo stop --timeout 60
if ($LASTEXITCODE -ne 0) { throw 'No se pudieron detener todos los motores DEMO.' }
Write-Host 'Presentación detenida. Los seis volúmenes originales se conservaron.' -ForegroundColor Green
