# Configura el control de acceso de las bases NoSQL en un equipo (Entrega final).
#
# 1. Genera las contraseñas que falten (generar-credenciales.ps1).
# 2. Recrea los contenedores para que tomen las contraseñas (los datos se conservan).
# 3. Crea o actualiza los usuarios de MongoDB (database/mongo/03_usuarios.js), que en una
#    base ya existente Docker no vuelve a ejecutar.
# 4. Crea o actualiza los roles y usuarios de Elasticsearch (database/elasticsearch/seguridad.json).
#
# Idempotente. setup.ps1 lo llama solo; en un equipo ya instalado basta con:
#     .\scripts\configurar-acceso.ps1

# Docker escribe su progreso en stderr: los errores se detectan por $LASTEXITCODE.
$ErrorActionPreference = 'Continue'
$Root = Split-Path $PSScriptRoot -Parent

. "$PSScriptRoot\credenciales-comun.ps1"
& "$PSScriptRoot\generar-credenciales.ps1"

Push-Location $Root
try {
    docker compose up -d
    if ($LASTEXITCODE -ne 0) { throw 'docker compose up falló.' }

    $envRaiz = Read-EnvFile (Join-Path $Root '.env')
    Write-Host '  Esperando MongoDB...' -ForegroundColor Yellow
    Wait-ContainerHealthy 'tiendaya_mongo' 120
    $rootUser = if ($envRaiz['MONGO_ROOT_USER']) { $envRaiz['MONGO_ROOT_USER'] } else { 'admin' }
    Set-MongoUsuarios 'tiendaya_mongo' $rootUser $envRaiz['MONGO_ROOT_PASSWORD']

    Write-Host '  Esperando Elasticsearch...' -ForegroundColor Yellow
    Wait-ContainerHealthy 'tiendaya_elasticsearch' 180
    Set-ElasticsearchSeguridad 'http://127.0.0.1:9200' $envRaiz['ELASTIC_PASSWORD'] $envRaiz $Root
} finally {
    Pop-Location
}
Write-Host '  Control de acceso configurado.' -ForegroundColor Green
