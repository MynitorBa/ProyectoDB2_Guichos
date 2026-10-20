param()

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$compose = Join-Path $root 'docker-compose.demo.yml'
$envFile = Join-Path $root 'backend\.env.demo'
$python = Join-Path $root 'backend\venv\Scripts\python.exe'
$npmCommand = Get-Command npm.cmd -ErrorAction SilentlyContinue
if (-not $npmCommand) { throw 'Falta npm.cmd en PATH. Instale Node.js antes de iniciar la presentación.' }
$npm = $npmCommand.Source
$ledger = Join-Path $root 'payment_simulator\ledger.demo.db'
$runtime = Join-Path (Split-Path -Parent $root) '_runtime\tiendaya-demo'
$services = @('mysql', 'mongo', 'redis', 'cassandra', 'neo4j', 'elasticsearch')
$volumeSuffixes = @('mysql_data', 'mongo_data', 'redis_data', 'cassandra_data', 'neo4j_data', 'es_data')

function Invoke-Docker([string[]]$Arguments) {
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $result = & docker @Arguments 2>&1
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousPreference
    }
    if ($exitCode -ne 0) { throw "Docker falló: $($Arguments -join ' ')`n$result" }
    return $result
}

function Assert-FreePort([int]$Port) {
    if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) {
        throw "El puerto $Port ya está ocupado. No se detendrá ningún proceso ajeno."
    }
}

function Wait-Http([string]$Url, [int]$Seconds = 90) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    do {
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 3
            if ($response.StatusCode -eq 200) { return }
        } catch {}
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)
    throw "No respondió: $Url. Revise los logs en $runtime."
}

Write-Host 'TiendaYa DEMO original: verificando antes de iniciar...' -ForegroundColor Cyan
foreach ($path in @($compose, $envFile, $python, $npm, $ledger)) {
    if (-not (Test-Path -LiteralPath $path)) { throw "Falta un archivo necesario: $path" }
}
if (-not (Test-Path -LiteralPath (Join-Path $root 'frontend\node_modules'))) {
    throw 'Faltan dependencias del frontend. No se instalará nada automáticamente.'
}
if (-not (Test-Path -LiteralPath (Join-Path $root 'laboratorio\node_modules'))) {
    throw 'Faltan dependencias del laboratorio. No se instalará nada automáticamente.'
}
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Docker CLI no está instalado.' }
& docker info --format '{{.ServerVersion}}' *> $null
if ($LASTEXITCODE -ne 0) {
    $dockerDesktop = 'C:\Program Files\Docker\Docker\Docker Desktop.exe'
    if (-not (Test-Path -LiteralPath $dockerDesktop)) {
        throw 'Docker Desktop no está listo y no se encontró su instalador habitual.'
    }
    Write-Host 'Abriendo Docker Desktop y esperando a que esté listo...' -ForegroundColor Yellow
    Start-Process -FilePath $dockerDesktop
    $dockerDeadline = (Get-Date).AddMinutes(4)
    do {
        Start-Sleep -Seconds 5
        & docker info --format '{{.ServerVersion}}' *> $null
        if ($LASTEXITCODE -eq 0) { break }
    } while ((Get-Date) -lt $dockerDeadline)
    if ($LASTEXITCODE -ne 0) { throw 'Docker Desktop no estuvo listo en cuatro minutos.' }
}

$os = Get-CimInstance Win32_OperatingSystem
$freeGb = [math]::Round($os.FreePhysicalMemory / 1MB, 2)
$allOriginalRunning = $true
foreach ($service in $services) {
    $state = & docker inspect "tiendaya_demo_$service" --format '{{.State.Status}}' 2>$null
    if ($LASTEXITCODE -ne 0 -or $state -ne 'running') { $allOriginalRunning = $false; break }
}
$requiredGb = if ($allOriginalRunning) { 4 } else { 8 }
if ($freeGb -lt $requiredGb) {
    throw "Hay $freeGb GB de RAM libres; se requieren al menos $requiredGb GB para este arranque."
}
foreach ($suffix in $volumeSuffixes) {
    $volume = "tiendaya_demo_demo_$suffix"
    Invoke-Docker -Arguments @('volume', 'inspect', $volume, '--format', '{{.Name}}') | Out-Null
}
$main = @(Invoke-Docker -Arguments @('ps', '--filter', 'label=com.docker.compose.project=proyectodb2_guichos', '--format', '{{.Names}}'))
if ($main.Count -gt 0 -and $main[0]) { throw 'La instancia PRINCIPAL tiene contenedores activos; no se iniciará una segunda pila.' }
$clean = @(Invoke-Docker -Arguments @('ps', '--filter', 'label=com.docker.compose.project=tiendaya_demo_clean', '--format', '{{.Names}}'))
if ($clean.Count -gt 0 -and $clean[0]) { throw 'La DEMO limpia incompleta está activa; no se iniciará la original.' }
foreach ($port in @(5173, 5174, 5175, 8000, 8001, 8005, 8006)) { Assert-FreePort $port }
$motorPorts = @(
    @{ Port = 3317; Name = 'mysql' }, @{ Port = 27117; Name = 'mongo' },
    @{ Port = 6389; Name = 'redis' }, @{ Port = 9142; Name = 'cassandra' },
    @{ Port = 7574; Name = 'neo4j' }, @{ Port = 7787; Name = 'neo4j' },
    @{ Port = 9210; Name = 'elasticsearch' }
)
foreach ($entry in $motorPorts) {
    if (-not (Get-NetTCPConnection -LocalPort $entry.Port -State Listen -ErrorAction SilentlyContinue)) { continue }
    $state = & docker inspect "tiendaya_demo_$($entry.Name)" --format '{{.State.Status}}' 2>$null
    if ($LASTEXITCODE -ne 0 -or $state -ne 'running') {
        throw "El puerto $($entry.Port) está ocupado y el motor DEMO esperado no está activo."
    }
}

foreach ($service in $services) {
    $container = "tiendaya_demo_$service"
    $existing = & docker inspect $container --format '{{.Name}}' 2>$null
    if ($LASTEXITCODE -ne 0) { continue }
    $expectedSuffix = switch ($service) {
        'mysql' { 'mysql_data' } 'mongo' { 'mongo_data' } 'redis' { 'redis_data' }
        'cassandra' { 'cassandra_data' } 'neo4j' { 'neo4j_data' }
        'elasticsearch' { 'es_data' }
    }
    $mounts = @(Invoke-Docker -Arguments @('inspect', $container, '--format', '{{range .Mounts}}{{println .Name}}{{end}}'))
    if ("tiendaya_demo_demo_$expectedSuffix" -notin $mounts) {
        throw "$container no usa el volumen original esperado. No se tocará."
    }
}

$settings = @{}
foreach ($line in Get-Content -LiteralPath $envFile) {
    $entry = $line.Trim()
    if (-not $entry -or $entry.StartsWith('#') -or -not $entry.Contains('=')) { continue }
    $parts = $entry.Split('=', 2)
    $settings[$parts[0].Trim()] = $parts[1].Trim()
}
if ($settings['TIENDAYA_DEMO'] -ne 'true' -or $settings['MYSQL_DB'] -ne 'tiendaya_demo' -or
    $settings['MYSQL_PORT'] -ne '3317' -or $settings['MONGO_DB'] -ne 'tiendaya_demo' -or
    $settings['REDIS_PORT'] -ne '6389' -or $settings['CASSANDRA_PORT'] -ne '9142' -or
    $settings['ES_INDEX_ALIAS'] -ne 'productos_demo') {
    throw 'backend/.env.demo no identifica inequívocamente la DEMO original.'
}
$mongoUri = [uri]$settings['MONGO_URI']
$neoUri = [uri]$settings['NEO4J_URI']
$esUri = [uri]$settings['ES_URL']
if ($mongoUri.Port -ne 27117 -or $neoUri.Port -ne 7787 -or $esUri.Port -ne 9210 -or
    $mongoUri.Host -notin @('127.0.0.1', 'localhost') -or
    $neoUri.Host -notin @('127.0.0.1', 'localhost') -or
    $esUri.Host -notin @('127.0.0.1', 'localhost')) {
    throw 'Una conexión de MongoDB, Neo4j o Elasticsearch no apunta a los puertos locales de DEMO.'
}
foreach ($key in $settings.Keys) { [Environment]::SetEnvironmentVariable($key, $settings[$key], 'Process') }
$env:FRAUD_ANALYSIS_ENABLED = 'false'
$env:FAULT_INJECTION_ENABLED = 'false'
$env:VITE_DEMO_MODE = 'true'
$env:VITE_PORT = '5173'
$env:VITE_API_URL = '/api/v1'
$env:VITE_BACKEND_URL = 'http://127.0.0.1:8000'
$env:FRONTEND_URL = 'http://localhost:5173'
$env:LAB_URL = 'http://localhost:5174'
$env:BACKEND_PORT = '8000'
$env:PAYMENT_GATEWAY_URL = 'http://127.0.0.1:8001'
$env:PASARELA_DB = $ledger

Write-Host 'Iniciando únicamente los seis motores DEMO originales...' -ForegroundColor Cyan
Invoke-Docker -Arguments @('compose', '-f', $compose, '--project-name', 'tiendaya_demo', 'up', '-d', '--no-recreate') | Out-Host
foreach ($service in $services) {
    $container = "tiendaya_demo_$service"
    $deadline = (Get-Date).AddMinutes(7)
    do {
        $state = Invoke-Docker -Arguments @('inspect', $container, '--format', '{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}')
        if ($state -eq 'running|healthy') { break }
        Start-Sleep -Seconds 3
    } while ((Get-Date) -lt $deadline)
    if ($state -ne 'running|healthy') { throw "$container no alcanzó estado healthy: $state" }
    $expectedSuffix = switch ($service) {
        'mysql' { 'mysql_data' } 'mongo' { 'mongo_data' } 'redis' { 'redis_data' }
        'cassandra' { 'cassandra_data' } 'neo4j' { 'neo4j_data' }
        'elasticsearch' { 'es_data' }
    }
    $mounts = @(Invoke-Docker -Arguments @('inspect', $container, '--format', '{{range .Mounts}}{{println .Name}}{{end}}'))
    if ("tiendaya_demo_demo_$expectedSuffix" -notin $mounts) {
        throw "$container no usa el volumen original tras iniciar. Se detiene el arranque de aplicaciones."
    }
}

New-Item -ItemType Directory -Force -Path $runtime | Out-Null
Start-Process -FilePath $python -ArgumentList '-m','uvicorn','payment_simulator.app:app','--host','127.0.0.1','--port','8001' -WorkingDirectory $root -RedirectStandardOutput (Join-Path $runtime 'gateway.out.log') -RedirectStandardError (Join-Path $runtime 'gateway.err.log') -WindowStyle Hidden
Start-Process -FilePath $python -ArgumentList '-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8000','--lifespan','off' -WorkingDirectory (Join-Path $root 'backend') -RedirectStandardOutput (Join-Path $runtime 'backend.out.log') -RedirectStandardError (Join-Path $runtime 'backend.err.log') -WindowStyle Hidden
$outboxProcess = Start-Process -FilePath $python -ArgumentList 'scripts\run_demo_outbox.py' -WorkingDirectory (Join-Path $root 'backend') -RedirectStandardOutput (Join-Path $runtime 'outbox.out.log') -RedirectStandardError (Join-Path $runtime 'outbox.err.log') -WindowStyle Hidden -PassThru
Start-Process -FilePath $npm -ArgumentList 'run','dev','--','--host','127.0.0.1','--port','5173' -WorkingDirectory (Join-Path $root 'frontend') -RedirectStandardOutput (Join-Path $runtime 'frontend.out.log') -RedirectStandardError (Join-Path $runtime 'frontend.err.log') -WindowStyle Hidden
$env:VITE_API_URL = 'http://localhost:8000/api/v1'
Start-Process -FilePath $npm -ArgumentList 'run','dev','--','--host','127.0.0.1','--port','5174' -WorkingDirectory (Join-Path $root 'laboratorio') -RedirectStandardOutput (Join-Path $runtime 'laboratorio.out.log') -RedirectStandardError (Join-Path $runtime 'laboratorio.err.log') -WindowStyle Hidden
Wait-Http 'http://127.0.0.1:8001/docs'
Wait-Http 'http://127.0.0.1:8000/docs'
Wait-Http 'http://127.0.0.1:5173/'
Wait-Http 'http://127.0.0.1:5174/'
$owned = @()
foreach ($port in @(5173, 5174, 8000, 8001)) {
    $listener = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction Stop | Select-Object -First 1
    $process = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)"
    $owned += @{ port = $port; pid = $process.ProcessId; created = $process.CreationDate.ToString('o') }
}
@{ app = $owned; outbox_launcher = $outboxProcess.Id } | ConvertTo-Json -Depth 4 |
    Set-Content -LiteralPath (Join-Path $runtime 'presentation-processes.json') -Encoding UTF8
Write-Host 'TiendaYa con DEMO original: http://localhost:5173' -ForegroundColor Green
Write-Host 'Laboratorio original: http://localhost:5174'
Write-Host 'API: http://localhost:8000/docs | Pasarela: http://localhost:8001/docs'
Write-Host 'Outbox activo. No se ejecutaron seeds, migraciones, backfills ni otros workers.'
