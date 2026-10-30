param(
    [ValidateSet('medium')][string]$Profile = 'medium',
    [string]$RunId = 'presentacion-equipo-v1',
    [switch]$PreflightOnly
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $root 'backend\.env.demo'
$example = Join-Path $root 'backend\.env.demo.example'
$python = Join-Path $root 'backend\venv\Scripts\python.exe'
$ledger = Join-Path $root 'payment_simulator\ledger.demo.db'
$volumeNames = @('mysql_data','mongo_data','redis_data','cassandra_data','neo4j_data','es_data') |
    ForEach-Object { "tiendaya_demo_demo_$_" }

foreach ($program in @('docker','python','node','npm')) {
    if (-not (Get-Command $program -ErrorAction SilentlyContinue)) {
        throw "Falta $program. Instálelo antes de preparar la DEMO."
    }
}
& docker info --format '{{.ServerVersion}}' *> $null
if ($LASTEXITCODE -ne 0) { throw 'Docker Desktop no está listo.' }
$os = Get-CimInstance Win32_OperatingSystem
$freeRamGb = [math]::Round($os.FreePhysicalMemory / 1MB, 2)
$driveName = (Split-Path -Qualifier $root).TrimEnd(':')
$freeDiskGb = [math]::Round((Get-PSDrive -Name $driveName).Free / 1GB, 2)
if ($freeRamGb -lt 8 -or $freeDiskGb -lt 15) {
    throw "Recursos insuficientes: RAM libre $freeRamGb GB (mínimo 8), disco libre $freeDiskGb GB (mínimo 15)."
}
$main = @(& docker ps --filter 'label=com.docker.compose.project=proyectodb2_guichos' --format '{{.Names}}')
if ($main.Count -gt 0 -and $main[0]) { throw 'PRINCIPAL está activa; no se iniciará una segunda pila.' }
$existingVolumes = @(& docker volume ls --format '{{.Name}}')
$existingContainers = @(& docker ps -a --format '{{.Names}}')
$foundVolumes = @($volumeNames | Where-Object { $_ -in $existingVolumes })
$foundContainers = @($existingContainers | Where-Object { $_ -like 'tiendaya_demo_*' })
if ($foundVolumes.Count -or $foundContainers.Count -or (Test-Path -LiteralPath $ledger)) {
    throw 'Ya existe una DEMO o un ledger local. Este instalador es solo para una instalación nueva; use start-presentation.ps1 para inicios cotidianos. No se modificó ningún dato.'
}
foreach ($port in @(3317,27117,6389,9142,7574,7787,9210,5173,5174,8000,8001)) {
    if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) {
        throw "El puerto $port está ocupado; no se detendrá ningún proceso ajeno."
    }
}
if (-not (Test-Path -LiteralPath $envFile)) {
    if ($PreflightOnly) { Write-Host 'Falta backend/.env.demo: se creará desde el ejemplo al instalar.' }
    else { Copy-Item -LiteralPath $example -Destination $envFile }
}
# Contraseñas de los motores y usuarios DEMO (control de acceso), generadas antes de crear nada.
if (-not $PreflightOnly) { & (Join-Path $PSScriptRoot 'configurar-acceso-demo.ps1') -SoloCredenciales }
if (Test-Path -LiteralPath $envFile) {
    $settings = @{}
    foreach ($line in Get-Content -LiteralPath $envFile) {
        $entry = $line.Trim()
        if (-not $entry -or $entry.StartsWith('#') -or -not $entry.Contains('=')) { continue }
        $parts = $entry.Split('=', 2)
        $settings[$parts[0].Trim()] = $parts[1].Trim()
    }
    $mongoUri = [uri]$settings['MONGO_URI']
    $neoUri = [uri]$settings['NEO4J_URI']
    $esUri = [uri]$settings['ES_URL']
    $localHosts = @('localhost','127.0.0.1')
    if ($settings['TIENDAYA_DEMO'] -ne 'true' -or $settings['MYSQL_DB'] -ne 'tiendaya_demo' -or
        $settings['MYSQL_USER'] -ne 'tiendaya_demo' -or
        $settings['MYSQL_PORT'] -ne '3317' -or $settings['MONGO_DB'] -ne 'tiendaya_demo' -or
        $settings['REDIS_PORT'] -ne '6389' -or $settings['CASSANDRA_PORT'] -ne '9142' -or
        $settings['CASSANDRA_KEYSPACE'] -ne 'tiendaya_analytics_demo' -or
        $settings['ES_INDEX_ALIAS'] -ne 'productos_demo' -or
        $settings['MYSQL_HOST'] -notin $localHosts -or
        $settings['REDIS_HOST'] -notin $localHosts -or
        $settings['CASSANDRA_HOST'] -notin $localHosts -or
        $mongoUri.Host -notin $localHosts -or $mongoUri.Port -ne 27117 -or
        $neoUri.Host -notin $localHosts -or $neoUri.Port -ne 7787 -or
        $esUri.Host -notin $localHosts -or $esUri.Port -ne 9210) {
        throw 'backend/.env.demo no apunta exclusivamente a la DEMO local.'
    }
    if (-not $settings['SECRET_KEY'] -or $settings['SECRET_KEY'] -like '*REEMPLAZAR*') {
        throw 'Configure un SECRET_KEY privado en backend/.env.demo antes de instalar.'
    }
    if ($settings['FRAUD_ANALYSIS_ENABLED'] -ne 'false' -or
        $settings['FAULT_INJECTION_ENABLED'] -ne 'false') {
        throw 'Desactive el worker automático y la inyección de fallas antes de instalar.'
    }
    # Incluye las DEMO_* que usa docker-compose.demo.yml (configurar-acceso-demo.ps1).
    foreach ($key in $settings.Keys) { [Environment]::SetEnvironmentVariable($key, $settings[$key], 'Process') }
}
if ($PreflightOnly) {
    Write-Host "Preflight OK. RAM libre: $freeRamGb GB; disco libre: $freeDiskGb GB. No se inició ni modificó ningún servicio."
    return
}

if (-not (Test-Path -LiteralPath $python)) {
    & python -m venv (Join-Path $root 'backend\venv')
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo crear el entorno Python.' }
}
& $python -m pip install -r (Join-Path $root 'backend\requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Falló la instalación de dependencias Python.' }
foreach ($folder in @('frontend','laboratorio')) {
    Push-Location (Join-Path $root $folder)
    try {
        & npm ci
        if ($LASTEXITCODE -ne 0) { throw "Falló npm ci en $folder." }
    } finally { Pop-Location }
}

# No repetir el bootstrap si falló a mitad: una recuperación requiere auditoría
# de los seis motores. Este bloqueo protege contra un seed duplicado.
# Crea los motores con el control de acceso ya activo y sus usuarios.
& (Join-Path $PSScriptRoot 'configurar-acceso-demo.ps1')
& (Join-Path $PSScriptRoot 'demo-environment.ps1') -Action bootstrap
# La carga usa la cuenta de administración de MongoDB solo en este proceso.
$env:DEMO_MONGO_URI_INSTALACION = $env:MONGO_URI -replace 'tiendaya_api:[^@]*@', "tiendaya_admin:$($env:DEMO_MONGO_ADMIN_PASSWORD)@"
& $python (Join-Path $root 'backend\scripts\seed_demo_large.py') --env-file $envFile `
    --profile $Profile --run-id $RunId --seed 20261018 --batch-size 500 --confirm-demo --project
if ($LASTEXITCODE -ne 0) { throw 'Falló la carga sintética; no vuelva a ejecutar el instalador sobre estos volúmenes.' }
Remove-Item Env:DEMO_MONGO_URI_INSTALACION -ErrorAction SilentlyContinue
# Índice v2 con vectores (usa el usuario indexador y el servicio de embeddings).
& (Join-Path $PSScriptRoot 'migrar-indice-demo.ps1')
foreach ($key in $settings.Keys) { [Environment]::SetEnvironmentVariable($key, $settings[$key], 'Process') }

$env:PASARELA_DB = $ledger
Push-Location $root
try {
    & $python -c 'import payment_simulator.app'
} finally { Pop-Location }
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $ledger)) { throw 'No se pudo crear el ledger DEMO vacío.' }
Push-Location (Join-Path $root 'backend')
try {
    & $python -c "from app.services.fraud_analysis_service import run_fraud_analysis_once; print(run_fraud_analysis_once('manual'))"
    if ($LASTEXITCODE -ne 0) { throw 'Falló el análisis inicial de fraude.' }
    & $python scripts\verify_setup.py
    if ($LASTEXITCODE -ne 0) { throw 'verify_setup.py detectó inconsistencias.' }
    & $python scripts\verify_presentation_data.py --env-file $envFile --run-id $RunId
    if ($LASTEXITCODE -ne 0) { throw 'La DEMO no alcanzó los mínimos de validación.' }
} finally { Pop-Location }
Write-Host 'Preparación validada. Para abrir la tienda y el laboratorio: .\scripts\start-presentation.ps1'
