# Configura el control de acceso de las bases NoSQL en un equipo (Entrega final).
#
# 1. Genera las contraseñas que falten (generar-credenciales.ps1).
# 2. Recrea los contenedores para que tomen las contraseñas (los datos se conservan).
# 3. Crea o actualiza los usuarios de MongoDB (database/mongo/03_usuarios.js), que en una
#    base ya existente Docker no vuelve a ejecutar.
#
# Idempotente. setup.ps1 lo llama solo; en un equipo ya instalado basta con:
#     .\scripts\configurar-acceso.ps1

# Docker escribe su progreso en stderr: los errores se detectan por $LASTEXITCODE.
$ErrorActionPreference = 'Continue'
$Root = Split-Path $PSScriptRoot -Parent

& "$PSScriptRoot\generar-credenciales.ps1"

Push-Location $Root
try {
    docker compose up -d
    if ($LASTEXITCODE -ne 0) { throw 'docker compose up falló.' }

    Write-Host '  Esperando MongoDB...' -ForegroundColor Yellow
    $intentos = 0
    while ((docker inspect tiendaya_mongo --format '{{.State.Health.Status}}') -ne 'healthy') {
        if (++$intentos -gt 60) { throw 'MongoDB no quedó saludable.' }
        Start-Sleep 2
    }

    $envRaiz = @{}
    Get-Content (Join-Path $Root '.env') | Where-Object { $_ -match '^\s*[A-Z_]+\s*=' } | ForEach-Object {
        $nombre, $valor = $_ -split '=', 2
        $envRaiz[$nombre.Trim()] = $valor.Trim()
    }
    $rootUser = if ($envRaiz['MONGO_ROOT_USER']) { $envRaiz['MONGO_ROOT_USER'] } else { 'admin' }
    $rootPass = if ($envRaiz['MONGO_ROOT_PASSWORD']) { $envRaiz['MONGO_ROOT_PASSWORD'] } else { 'adminpassword' }
    docker exec tiendaya_mongo mongosh --quiet -u $rootUser -p $rootPass --authenticationDatabase admin `
        /docker-entrypoint-initdb.d/03_usuarios.js
    if ($LASTEXITCODE -ne 0) { throw 'No se pudieron crear los usuarios de MongoDB.' }
} finally {
    Pop-Location
}
Write-Host '  Control de acceso configurado.' -ForegroundColor Green
