param(
    [ValidateSet('status','start','bootstrap','seed-small','seed-medium','seed-full','start-app','stop')]
    [string]$Action = 'status',
    [string]$RunId = 'entrega3-demo-v1'
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Compose = Join-Path $Root 'docker-compose.demo.yml'
$EnvFile = Join-Path $Root 'backend\.env.demo'
$EnvExample = Join-Path $Root 'backend\.env.demo.example'
$Python = Join-Path $Root 'backend\venv\Scripts\python.exe'
$Runtime = Join-Path (Split-Path -Parent $Root) '_runtime\tiendaya-demo'

function Assert-Resources(
    [double]$MinFreeRamGb = 8,
    [double]$MinFreeDiskGb = 15
) {
    $os = Get-CimInstance Win32_OperatingSystem
    $memory = Get-CimInstance Win32_PerfFormattedData_PerfOS_Memory
    $freeRamGb = [math]::Round($os.FreePhysicalMemory / 1MB, 2)
    $freeDiskGb = [math]::Round((Get-PSDrive C).Free / 1GB, 2)
    $commitPct = [int]$memory.PercentCommittedBytesInUse
    if ($freeRamGb -lt $MinFreeRamGb -or $freeDiskGb -lt $MinFreeDiskGb -or $commitPct -ge 80) {
        throw "Recursos insuficientes para una segunda pila: RAM libre ${freeRamGb}GB (mínimo ${MinFreeRamGb}), memoria comprometida ${commitPct}% (debe ser menor de 80%) y disco libre ${freeDiskGb}GB (mínimo ${MinFreeDiskGb}). La instancia principal no fue modificada."
    }
}

function Ensure-DemoEnv {
    if (-not (Test-Path -LiteralPath $EnvFile)) {
        Copy-Item -LiteralPath $EnvExample -Destination $EnvFile
        Write-Host "Se creó backend/.env.demo desde el ejemplo local."
    }
}

function Import-DemoEnv {
    Ensure-DemoEnv
    foreach ($line in Get-Content -LiteralPath $EnvFile) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith('#')) { continue }
        $parts = $trimmed.Split('=', 2)
        if ($parts.Count -eq 2) {
            [Environment]::SetEnvironmentVariable($parts[0], $parts[1], 'Process')
        }
    }
    if ($env:TIENDAYA_DEMO -ne 'true' -or $env:MYSQL_DB -ne 'tiendaya_demo') {
        throw 'El archivo seleccionado no identifica de forma inequívoca el entorno DEMO.'
    }
}

function Invoke-DemoCompose([string[]]$Arguments) {
    & docker compose -f $Compose --project-name tiendaya_demo @Arguments
    if ($LASTEXITCODE -ne 0) { throw "docker compose falló: $($Arguments -join ' ')" }
}

function Wait-DemoContainersHealthy([int]$Seconds = 360) {
    $names = @(
        'tiendaya_demo_mysql', 'tiendaya_demo_mongo', 'tiendaya_demo_redis',
        'tiendaya_demo_cassandra', 'tiendaya_demo_neo4j',
        'tiendaya_demo_elasticsearch'
    )
    $deadline = (Get-Date).AddSeconds($Seconds)
    do {
        $pending = @()
        foreach ($name in $names) {
            $state = (& docker inspect $name --format '{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' 2>$null)
            if ($LASTEXITCODE -ne 0 -or $state -ne 'running|healthy') { $pending += "$name=$state" }
        }
        if ($pending.Count -eq 0) { return }
        Start-Sleep -Seconds 3
    } while ((Get-Date) -lt $deadline)
    throw "Los motores DEMO no alcanzaron estado healthy: $($pending -join ', ')"
}

function Wait-DemoHttp([string]$Url, [int]$Seconds = 90) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    do {
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 3
            if ($response.StatusCode -eq 200) { return }
        } catch {}
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)
    throw "El servicio DEMO no respondió a tiempo: $Url"
}

function Bootstrap-Demo {
    Import-DemoEnv
    $rootPassword = $env:DEMO_MYSQL_ROOT_PASSWORD
    if (-not $rootPassword) { $rootPassword = 'demo-root-local' }
    # Solo se cargan directamente el esquema y seed heredados. Las fases 1+
    # deben pasar por sus migradores oficiales porque varias coordinan MySQL
    # con MongoDB y no son correctas si se ejecutan como SQL aislado.
    $baseInstalled = (& docker exec -e "MYSQL_PWD=$rootPassword" tiendaya_demo_mysql mysql -N -B -uroot `
        -e "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='tiendaya_demo' AND table_name='usuarios'").Trim()
    if ($baseInstalled -eq '0') {
        $sqlFiles = @('01_schema.sql','02_indexes.sql','03_procedures.sql','04_seed.sql') |
            ForEach-Object { Get-Item (Join-Path $Root "database\mysql\$_") }
        foreach ($file in $sqlFiles) {
            Write-Host "MySQL DEMO <- $($file.Name)"
            $sql = Get-Content -Raw -LiteralPath $file.FullName
            $sql = $sql.Replace(
                'CREATE DATABASE IF NOT EXISTS tiendaya',
                'CREATE DATABASE IF NOT EXISTS tiendaya_demo'
            )
            $sql = $sql.Replace('USE tiendaya;', 'USE tiendaya_demo;')
            $sql | docker exec -i -e "MYSQL_PWD=$rootPassword" tiendaya_demo_mysql mysql --default-character-set=utf8mb4 -uroot tiendaya_demo
            if ($LASTEXITCODE -ne 0) { throw "Falló $($file.Name); se detuvo el bootstrap DEMO." }
        }
    } else {
        Write-Host 'Esquema base MySQL DEMO ya presente; se reanudan migraciones idempotentes.'
    }

    # Si una ejecución anterior de Fase 3 fue interrumpida dentro del CALL, el
    # procedimiento temporal queda con DEFINER=root. Retirarlo con el root del
    # contenedor DEMO permite que el migrador idempotente lo recree sin tocar
    # rutinas ni datos de la instancia principal.
    & docker exec -e "MYSQL_PWD=$rootPassword" tiendaya_demo_mysql mysql -uroot `
        -e 'DROP PROCEDURE IF EXISTS tiendaya_demo.sp_aplicar_fase3_backfill; DROP PROCEDURE IF EXISTS tiendaya_demo.sp_crear_pedido'
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo retirar la rutina temporal incompleta de Fase 3 en DEMO.' }

    Push-Location (Join-Path $Root 'backend')
    try {
        $schemaState = (& $Python 'scripts\detect_schema_state.py').Trim()
        if ($LASTEXITCODE -ne 0) { throw 'No se pudo detectar el estado del esquema DEMO.' }
    } finally {
        Pop-Location
    }

    $legacyMigrationScripts = @(
        'apply_phase1_integrity.py',
        'apply_phase2_additive.py',
        'migrate_products_to_mongo.py',
        'apply_phase3_backfill.py',
        'apply_phase4_dual_read.py',
        'apply_phase6b_additive.py',
        'apply_phase6b_cutover.py'
    )
    $commonMigrationScripts = @(
        'apply_phase7_reference_integrity.py',
        'apply_catalog_extensions.py',
        'apply_catalog_requests.py',
        'apply_offer_temporal_history.py',
        'apply_dynamic_variants.py',
        'apply_unique_nombre_tiendaya.py',
        'apply_checkout_saga.py',
        'apply_fulfillment.py',
        'migrate_cart_to_redis.py',
        'apply_flash_sales.py',
        'apply_outbox_v2.py',
        'apply_review_authority.py',
        'apply_fraud_alerts.py',
        'apply_fraud_automation.py'
    )
    if ($schemaState -eq 'legacy') {
        $migrationScripts = $legacyMigrationScripts + $commonMigrationScripts
    } elseif ($schemaState -eq 'final') {
        Write-Host 'Esquema final DEMO detectado; no se repite la migración destructiva heredada.'
        $migrationScripts = $commonMigrationScripts
    } else {
        throw "Estado de esquema DEMO desconocido: $schemaState"
    }
    Push-Location (Join-Path $Root 'backend')
    try {
        foreach ($script in $migrationScripts) {
            Write-Host "Migración DEMO <- $script"
            & $Python (Join-Path 'scripts' $script)
            if ($LASTEXITCODE -ne 0) {
                throw "Falló la migración DEMO $script."
            }
        }
    } finally {
        Pop-Location
    }

    $cql = (Get-Content -Raw (Join-Path $Root 'database\cassandra\01_analytics_schema.cql')).Replace('tiendaya_analytics', 'tiendaya_analytics_demo')
    $cql | docker exec -i tiendaya_demo_cassandra cqlsh
    if ($LASTEXITCODE -ne 0) { throw 'Falló el esquema Cassandra DEMO.' }
    Write-Host 'Esquemas DEMO inicializados. No se tocó la instancia principal.'
}

function Seed-Demo([string]$Profile) {
    Import-DemoEnv
    & $Python (Join-Path $Root 'backend\scripts\seed_demo_large.py') `
        --env-file $EnvFile --profile $Profile --run-id $RunId `
        --seed 20261018 --batch-size 500 --confirm-demo --project
    if ($LASTEXITCODE -ne 0) { throw 'La carga DEMO se detuvo; consulte la bitácora antes de reanudar.' }
}

function Start-DemoApps {
    Import-DemoEnv
    New-Item -ItemType Directory -Force -Path $Runtime | Out-Null
    $env:VITE_DEMO_MODE = 'true'
    $env:VITE_PORT = '5175'
    # frontend/.env apunta deliberadamente a la API principal para el uso
    # normal. Esta variable de proceso tiene precedencia únicamente en la
    # instancia DEMO y obliga al cliente a usar el proxy local de Vite.
    $env:VITE_API_URL = '/api/v1'
    $env:VITE_BACKEND_URL = 'http://127.0.0.1:8005'
    Start-Process -FilePath $Python -ArgumentList '-m','uvicorn','payment_simulator.app:app','--host','127.0.0.1','--port','8006' -WorkingDirectory $Root -RedirectStandardOutput (Join-Path $Runtime 'gateway.out.log') -RedirectStandardError (Join-Path $Runtime 'gateway.err.log') -WindowStyle Hidden
    Start-Process -FilePath $Python -ArgumentList '-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8005' -WorkingDirectory (Join-Path $Root 'backend') -RedirectStandardOutput (Join-Path $Runtime 'backend.out.log') -RedirectStandardError (Join-Path $Runtime 'backend.err.log') -WindowStyle Hidden
    Start-Process -FilePath 'C:\Program Files\nodejs\npm.cmd' -ArgumentList 'run','dev','--','--host','127.0.0.1','--port','5175' -WorkingDirectory (Join-Path $Root 'frontend') -RedirectStandardOutput (Join-Path $Runtime 'frontend.out.log') -RedirectStandardError (Join-Path $Runtime 'frontend.err.log') -WindowStyle Hidden
    Wait-DemoHttp 'http://localhost:8005/docs'
    Wait-DemoHttp 'http://localhost:8006/docs'
    Wait-DemoHttp 'http://localhost:5175'
    Write-Host 'DEMO iniciada: frontend http://localhost:5175 · backend http://localhost:8005'
}

function Stop-DemoPort([int]$Port, [string]$Pattern) {
    $connections = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    foreach ($pidValue in @($connections.OwningProcess | Sort-Object -Unique)) {
        $process = Get-CimInstance Win32_Process -Filter "ProcessId=$pidValue"
        if ($process.CommandLine -notmatch $Pattern) {
            throw "El puerto $Port pertenece a un proceso ajeno; no se detendrá: $($process.CommandLine)"
        }
        Stop-Process -Id $pidValue -ErrorAction SilentlyContinue
        Wait-Process -Id $pidValue -Timeout 5 -ErrorAction SilentlyContinue
        if (Get-Process -Id $pidValue -ErrorAction SilentlyContinue) {
            Stop-Process -Id $pidValue -Force -ErrorAction SilentlyContinue
        }
    }
}

switch ($Action) {
    'status' {
        Invoke-DemoCompose @('ps')
        foreach ($port in 3317,27117,6389,9142,7574,7787,9210,5175,8005,8006) {
            $listening = [bool](Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
            [pscustomobject]@{ Port = $port; Listening = $listening }
        }
    }
    'start' {
        Assert-Resources
        Ensure-DemoEnv
        Invoke-DemoCompose @('up','-d')
        Wait-DemoContainersHealthy
    }
    'bootstrap' { Bootstrap-Demo }
    'seed-small' {
        Assert-Resources -MinFreeRamGb 6
        Seed-Demo 'small'
    }
    'seed-medium' {
        Assert-Resources -MinFreeRamGb 7
        Seed-Demo 'medium'
    }
    'seed-full' {
        Assert-Resources -MinFreeRamGb 8
        Seed-Demo 'full'
    }
    'start-app' {
        Assert-Resources
        Start-DemoApps
    }
    'stop' {
        Stop-DemoPort 5175 'vite(\.js)?.*--port\s+5175(?:\s|$)'
        Stop-DemoPort 8005 'uvicorn app\.main:app .*--port 8005'
        Stop-DemoPort 8006 'uvicorn payment_simulator\.app:app .*--port 8006'
        # Los motores JVM (Cassandra, Elasticsearch y Neo4j) pueden necesitar
        # más que los 10 segundos predeterminados para vaciar sus buffers.
        Invoke-DemoCompose @('stop', '--timeout', '60')
        Write-Host 'Entorno DEMO detenido; contenedores y volúmenes DEMO se conservaron.'
    }
}
