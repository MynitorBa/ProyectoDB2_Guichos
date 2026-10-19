param(
    [ValidateSet('status', 'to-demo', 'to-main')]
    [string]$Action = 'status',
    [switch]$ConfirmSwitch
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$MainCompose = Join-Path $Root 'docker-compose.yml'
$DemoScript = Join-Path $PSScriptRoot 'demo-environment.ps1'
$Python = Join-Path $Root 'backend\venv\Scripts\python.exe'
$MainRuntime = Join-Path (Split-Path -Parent $Root) '_runtime\tiendaya-main'

function Import-DotEnv([string]$Path) {
    foreach ($line in Get-Content -LiteralPath $Path -ErrorAction Stop) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith('#') -or -not $trimmed.Contains('=')) { continue }
        $parts = $trimmed.Split('=', 2)
        [Environment]::SetEnvironmentVariable($parts[0].Trim(), $parts[1].Trim(), 'Process')
    }
}

function Invoke-MainCompose([string[]]$Arguments) {
    & docker compose -f $MainCompose --project-name proyectodb2_guichos @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Compose PRINCIPAL falló: $($Arguments -join ' ')" }
}

function Get-PortProcesses([int]$Port) {
    $connections = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    foreach ($pidValue in @($connections.OwningProcess | Sort-Object -Unique)) {
        Get-CimInstance Win32_Process -Filter "ProcessId=$pidValue"
    }
}

function Assert-OwnedPort([int]$Port, [string]$Pattern) {
    foreach ($process in @(Get-PortProcesses $Port)) {
        if ($process.CommandLine -notmatch $Pattern) {
            throw "El puerto $Port pertenece a un proceso ajeno y no se tocará: $($process.CommandLine)"
        }
    }
}

function Stop-OwnedPort([int]$Port, [string]$Pattern) {
    Assert-OwnedPort $Port $Pattern
    foreach ($process in @(Get-PortProcesses $Port)) {
        Stop-Process -Id $process.ProcessId -ErrorAction SilentlyContinue
        Wait-Process -Id $process.ProcessId -Timeout 5 -ErrorAction SilentlyContinue
        if (Get-Process -Id $process.ProcessId -ErrorAction SilentlyContinue) {
            Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
        }
    }
}

function Stop-MainWorker {
    $workers = @(
        Get-CimInstance Win32_Process | Where-Object {
            $_.CommandLine -match 'run_fraud_analysis\.py\s+--serve'
        }
    )
    $ownedIds = @(
        $workers | Where-Object {
            $_.ExecutablePath -like "$(Join-Path $Root 'backend')*"
        } | Select-Object -ExpandProperty ProcessId
    )
    foreach ($worker in $workers) {
        if ($worker.ProcessId -notin $ownedIds -and $worker.ParentProcessId -notin $ownedIds) {
            throw "Se encontró un worker de fraude ajeno y no se tocará: $($worker.CommandLine)"
        }
    }
    foreach ($worker in $workers | Sort-Object ProcessId -Descending) {
        Stop-Process -Id $worker.ProcessId -ErrorAction SilentlyContinue
    }
    foreach ($worker in $workers) {
        Wait-Process -Id $worker.ProcessId -Timeout 5 -ErrorAction SilentlyContinue
        if (Get-Process -Id $worker.ProcessId -ErrorAction SilentlyContinue) {
            Stop-Process -Id $worker.ProcessId -Force -ErrorAction SilentlyContinue
        }
    }
}

function Stop-MainApps {
    Stop-MainWorker
    Stop-OwnedPort 5173 'vite(\.js)?.*--port\s+5173(?:\s|$)'
    Stop-OwnedPort 8000 'uvicorn app\.main:app .*--port 8000'
    Stop-OwnedPort 8001 'uvicorn payment_simulator\.app:app .*--port 8001'
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
    throw "No respondió a tiempo: $Url"
}

function Start-MainApps {
    foreach ($port in 5173, 8000, 8001) {
        if (Get-PortProcesses $port) { throw "El puerto principal $port ya está ocupado." }
    }
    Import-DotEnv (Join-Path $Root 'backend\.env')
    New-Item -ItemType Directory -Force -Path $MainRuntime | Out-Null
    $env:VITE_DEMO_MODE = 'false'
    $env:VITE_PORT = '5173'
    $env:VITE_API_URL = 'http://localhost:8000/api/v1'
    $env:VITE_BACKEND_URL = 'http://127.0.0.1:8000'
    Start-Process -FilePath $Python -ArgumentList '-m','uvicorn','payment_simulator.app:app','--host','127.0.0.1','--port','8001' -WorkingDirectory $Root -RedirectStandardOutput (Join-Path $MainRuntime 'gateway.out.log') -RedirectStandardError (Join-Path $MainRuntime 'gateway.err.log') -WindowStyle Hidden
    Start-Process -FilePath $Python -ArgumentList '-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8000' -WorkingDirectory (Join-Path $Root 'backend') -RedirectStandardOutput (Join-Path $MainRuntime 'backend.out.log') -RedirectStandardError (Join-Path $MainRuntime 'backend.err.log') -WindowStyle Hidden
    Start-Process -FilePath 'C:\Program Files\nodejs\npm.cmd' -ArgumentList 'run','dev','--','--host','127.0.0.1','--port','5173' -WorkingDirectory (Join-Path $Root 'frontend') -RedirectStandardOutput (Join-Path $MainRuntime 'frontend.out.log') -RedirectStandardError (Join-Path $MainRuntime 'frontend.err.log') -WindowStyle Hidden
    if ($env:FRAUD_ANALYSIS_ENABLED -eq 'true') {
        Start-Process -FilePath $Python -ArgumentList 'scripts\run_fraud_analysis.py','--serve' -WorkingDirectory (Join-Path $Root 'backend') -RedirectStandardOutput (Join-Path $MainRuntime 'fraud-worker.out.log') -RedirectStandardError (Join-Path $MainRuntime 'fraud-worker.err.log') -WindowStyle Hidden
    }
    Wait-Http 'http://localhost:8000/docs'
    Wait-Http 'http://localhost:5173'
    Wait-Http 'http://localhost:8001/docs'
}

function Show-Status {
    foreach ($port in 5173,8000,8001,5175,8005,8006,3307,3317) {
        [pscustomobject]@{
            Port = $port
            Listening = [bool](Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
        }
    }
    docker ps --format 'table {{.Names}}\t{{.Status}}' --filter 'name=tiendaya'
}

if ($Action -ne 'status' -and -not $ConfirmSwitch) {
    throw 'Los cambios de entorno requieren -ConfirmSwitch.'
}

switch ($Action) {
    'status' { Show-Status }
    'to-demo' {
        Stop-MainApps
        # Da tiempo suficiente a los motores persistentes para cerrar sin SIGKILL.
        Invoke-MainCompose @('stop', '--timeout', '60')
        & $DemoScript -Action start
        & $DemoScript -Action start-app
        Show-Status
    }
    'to-main' {
        & $DemoScript -Action stop
        Invoke-MainCompose @('up', '-d')
        Start-MainApps
        Show-Status
    }
}
