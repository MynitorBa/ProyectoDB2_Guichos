param()

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$compose = Join-Path $root 'docker-compose.yml'
$envFile = Join-Path $root 'backend\.env'
$python = Join-Path $root 'backend\venv\Scripts\python.exe'
$npm = 'C:\Program Files\nodejs\npm.cmd'
$runtime = Join-Path (Split-Path -Parent $root) '_runtime\tiendaya-main'
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

Write-Host 'TiendaYa PRINCIPAL: verificando antes de iniciar...' -ForegroundColor Cyan
foreach ($path in @($compose, $envFile, $python, $npm)) {
    if (-not (Test-Path -LiteralPath $path)) { throw "Falta un archivo necesario: $path" }
}
if (-not (Test-Path -LiteralPath (Join-Path $root 'frontend\node_modules'))) {
    throw 'Faltan dependencias del frontend. No se instalará nada automáticamente.'
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

$settings = @{}
foreach ($line in Get-Content -LiteralPath $envFile) {
    $entry = $line.Trim()
    if (-not $entry -or $entry.StartsWith('#') -or -not $entry.Contains('=')) { continue }
    $parts = $entry.Split('=', 2)
    $settings[$parts[0].Trim()] = $parts[1].Trim()
}
if ($settings['MYSQL_DB'] -ne 'tiendaya' -or $settings['MYSQL_PORT'] -ne '3307' -or
    $settings['MONGO_DB'] -ne 'tiendaya' -or $settings['TIENDAYA_DEMO'] -eq 'true') {
    throw 'backend/.env no identifica inequívocamente la instancia PRINCIPAL.'
}

$os = Get-CimInstance Win32_OperatingSystem
$freeGb = [math]::Round($os.FreePhysicalMemory / 1MB, 2)
if ($freeGb -lt 8) { throw "Hay $freeGb GB de RAM libres; se requieren al menos 8 GB antes de iniciar PRINCIPAL." }
foreach ($suffix in $volumeSuffixes) {
    Invoke-Docker -Arguments @('volume', 'inspect', "proyectodb2_guichos_$suffix", '--format', '{{.Name}}') | Out-Null
}
$demo = @(Invoke-Docker -Arguments @('ps', '--filter', 'label=com.docker.compose.project=tiendaya_demo', '--format', '{{.Names}}'))
if ($demo.Count -gt 0 -and $demo[0]) { throw 'La DEMO original está activa; no se iniciará PRINCIPAL encima.' }
$clean = @(Invoke-Docker -Arguments @('ps', '--filter', 'label=com.docker.compose.project=tiendaya_demo_clean', '--format', '{{.Names}}'))
if ($clean.Count -gt 0 -and $clean[0]) { throw 'La DEMO limpia incompleta está activa; no se iniciará PRINCIPAL encima.' }
foreach ($port in @(3307, 27017, 6379, 9042, 7474, 7687, 9200, 8080, 8081, 8082, 8083, 5173, 8000, 8001)) { Assert-FreePort $port }

foreach ($service in $services) {
    $container = "tiendaya_$service"
    $existing = & docker inspect $container --format '{{.Name}}' 2>$null
    if ($LASTEXITCODE -ne 0) { continue }
    $expectedSuffix = switch ($service) {
        'mysql' { 'mysql_data' } 'mongo' { 'mongo_data' } 'redis' { 'redis_data' }
        'cassandra' { 'cassandra_data' } 'neo4j' { 'neo4j_data' }
        'elasticsearch' { 'es_data' }
    }
    $mounts = @(Invoke-Docker -Arguments @('inspect', $container, '--format', '{{range .Mounts}}{{println .Name}}{{end}}'))
    if ("proyectodb2_guichos_$expectedSuffix" -notin $mounts) {
        throw "$container no usa el volumen PRINCIPAL esperado. No se tocará."
    }
}

foreach ($key in $settings.Keys) { [Environment]::SetEnvironmentVariable($key, $settings[$key], 'Process') }
$env:VITE_DEMO_MODE = 'false'
$env:VITE_PORT = '5173'
$env:VITE_API_URL = '/api/v1'
$env:VITE_BACKEND_URL = 'http://127.0.0.1:8000'

Write-Host 'Iniciando contenedores de PRINCIPAL sin migraciones ni reparaciones...' -ForegroundColor Cyan
Invoke-Docker -Arguments @('compose', '-f', $compose, '--project-name', 'proyectodb2_guichos', 'up', '-d', '--no-recreate') | Out-Host
foreach ($service in $services) {
    $container = "tiendaya_$service"
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
    if ("proyectodb2_guichos_$expectedSuffix" -notin $mounts) {
        throw "$container no usa el volumen PRINCIPAL tras iniciar. Se detiene el arranque de aplicaciones."
    }
}

New-Item -ItemType Directory -Force -Path $runtime | Out-Null
Start-Process -FilePath $python -ArgumentList '-m','uvicorn','payment_simulator.app:app','--host','127.0.0.1','--port','8001' -WorkingDirectory $root -RedirectStandardOutput (Join-Path $runtime 'gateway.out.log') -RedirectStandardError (Join-Path $runtime 'gateway.err.log') -WindowStyle Hidden
Start-Process -FilePath $python -ArgumentList '-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8000' -WorkingDirectory (Join-Path $root 'backend') -RedirectStandardOutput (Join-Path $runtime 'backend.out.log') -RedirectStandardError (Join-Path $runtime 'backend.err.log') -WindowStyle Hidden
Start-Process -FilePath $npm -ArgumentList 'run','dev','--','--host','127.0.0.1','--port','5173' -WorkingDirectory (Join-Path $root 'frontend') -RedirectStandardOutput (Join-Path $runtime 'frontend.out.log') -RedirectStandardError (Join-Path $runtime 'frontend.err.log') -WindowStyle Hidden
if ($settings['FRAUD_ANALYSIS_ENABLED'] -eq 'true') {
    Start-Process -FilePath $python -ArgumentList 'scripts\run_fraud_analysis.py','--serve' -WorkingDirectory (Join-Path $root 'backend') -RedirectStandardOutput (Join-Path $runtime 'fraud-worker.out.log') -RedirectStandardError (Join-Path $runtime 'fraud-worker.err.log') -WindowStyle Hidden
}
Wait-Http 'http://127.0.0.1:8001/docs'
Wait-Http 'http://127.0.0.1:8000/docs'
Wait-Http 'http://127.0.0.1:5173/'
Write-Host 'PRINCIPAL lista: http://localhost:5173' -ForegroundColor Green
Write-Host 'No se ejecutaron migraciones, seeds, backfills, reparaciones ni reindexaciones.'
