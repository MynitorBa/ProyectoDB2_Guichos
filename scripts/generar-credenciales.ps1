# Genera las contraseñas de los usuarios de las bases NoSQL (control de acceso, Entrega final).
#
# Idempotente: solo crea las que faltan, nunca cambia una existente.
#   .env (raíz)        lo lee docker-compose para crear los usuarios en cada contenedor
#   backend\.env       el backend usa solo su propio usuario (el de menor privilegio)
# Ambos archivos están fuera del repositorio (.gitignore).
#
# Uso: .\scripts\generar-credenciales.ps1        (setup.ps1 lo llama solo)
#      Después de crear contraseñas nuevas:  docker compose up -d   (recrea los contenedores)

$ErrorActionPreference = 'Stop'
$Root = Split-Path $PSScriptRoot -Parent
$EnvRaiz = Join-Path $Root '.env'
$EnvBackend = Join-Path $Root 'backend\.env'

function Get-EnvValue([string]$Path, [string]$Name) {
    if (-not (Test-Path $Path)) { return $null }
    $linea = Get-Content $Path | Where-Object { $_ -match "^\s*$Name\s*=" } | Select-Object -Last 1
    if (-not $linea) { return $null }
    $valor = ($linea -split '=', 2)[1].Trim()
    if ($valor) { return $valor } else { return $null }
}

function Set-EnvValue([string]$Path, [string]$Name, [string]$Value) {
    $lineas = @(if (Test-Path $Path) { Get-Content $Path } else { @() })
    $encontrada = $false
    $nuevas = foreach ($linea in $lineas) {
        if ($linea -match "^\s*$Name\s*=") { $encontrada = $true; "$Name=$Value" } else { $linea }
    }
    if (-not $encontrada) { $nuevas = @($nuevas) + "$Name=$Value" }
    [System.IO.File]::WriteAllLines($Path, [string[]]$nuevas, (New-Object System.Text.UTF8Encoding $false))
}

function New-Secret {
    $bytes = New-Object byte[] 24
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    # Solo letras y números: se usan en URLs de conexión y en archivos de configuración.
    return (($bytes | ForEach-Object { $_.ToString('x2') }) -join '')
}

foreach ($archivo in @(@($EnvRaiz, '.env.example'), @($EnvBackend, 'backend\.env.example'))) {
    if (-not (Test-Path $archivo[0])) {
        Copy-Item (Join-Path $Root $archivo[1]) $archivo[0]
        Write-Host "  Copiado $($archivo[1]) → $($archivo[0].Replace($Root + '\', ''))"
    }
}

# Contraseñas que viven en el .env de la raíz (una por usuario de cada componente).
$secretos = @(
    'REDIS_API_PASSWORD', 'REDIS_LECTURA_PASSWORD', 'REDIS_ADMIN_PASSWORD',
    'MONGO_API_PASSWORD', 'MONGO_LECTURA_PASSWORD', 'MONGO_ADMIN_PASSWORD',
    'ELASTIC_PASSWORD', 'ES_API_PASSWORD', 'ES_INDEXADOR_PASSWORD', 'ES_LECTURA_PASSWORD'
)
$creadas = 0
foreach ($nombre in $secretos) {
    if (-not (Get-EnvValue $EnvRaiz $nombre)) {
        Set-EnvValue $EnvRaiz $nombre (New-Secret)
        $creadas++
    }
}

# El backend se conecta con su usuario de menor privilegio. Se conserva el servidor
# que ya tuviera configurado MONGO_URI.
$uriActual = Get-EnvValue $EnvBackend 'MONGO_URI'
$servidorMongo = if ($uriActual -match '@([^/?]+)' -or $uriActual -match '^mongodb://([^/?@]+)') { $Matches[1] } else { 'localhost:27017' }
$baseMongo = if (Get-EnvValue $EnvBackend 'MONGO_DB') { Get-EnvValue $EnvBackend 'MONGO_DB' } else { 'tiendaya' }
$usuarioBackend = @{
    'REDIS_USERNAME' = 'tiendaya_api'
    'REDIS_PASSWORD' = (Get-EnvValue $EnvRaiz 'REDIS_API_PASSWORD')
    'ES_USERNAME'    = 'tiendaya_api'
    'ES_PASSWORD'    = (Get-EnvValue $EnvRaiz 'ES_API_PASSWORD')
    'MONGO_URI'      = "mongodb://tiendaya_api:$(Get-EnvValue $EnvRaiz 'MONGO_API_PASSWORD')@$servidorMongo/$baseMongo" + "?authSource=$baseMongo"
}
foreach ($nombre in $usuarioBackend.Keys) {
    if ((Get-EnvValue $EnvBackend $nombre) -ne $usuarioBackend[$nombre]) {
        Set-EnvValue $EnvBackend $nombre $usuarioBackend[$nombre]
    }
}

if ($creadas) {
    Write-Host "  Credenciales: $creadas contraseña(s) nueva(s) en .env; recree los contenedores con 'docker compose up -d'." -ForegroundColor Yellow
} else {
    Write-Host '  Credenciales: ya estaban configuradas.' -ForegroundColor Green
}
