# Control de acceso del entorno DEMO de la presentación (Entrega final).
#
# Mismas reglas que la instancia principal (ACL de Redis, usuarios de MongoDB, roles de
# Elasticsearch); contraseñas propias en backend\.env.demo (fuera del repositorio).
#
# 1. Contraseñas: adopta las que ya usan los contenedores DEMO existentes (sus volúmenes se
#    crearon con ellas) y genera las que falten. Completa las del backend DEMO: así deja de
#    heredar las credenciales de la instancia principal de backend\.env.
# 2. Recrea los contenedores DEMO que cambiaron (los datos se conservan).
# 3. Crea o actualiza los usuarios de MongoDB y los roles y usuarios de Elasticsearch.
#
# Idempotente. Uso:  .\scripts\configurar-acceso-demo.ps1
#   -SoloCredenciales  solo el paso 1 (lo usa el instalador antes de crear los contenedores)

param([switch]$SoloCredenciales)

# Docker escribe su progreso en stderr: los errores se detectan por $LASTEXITCODE.
$ErrorActionPreference = 'Continue'
$Root = Split-Path $PSScriptRoot -Parent
$EnvDemo = Join-Path $Root 'backend\.env.demo'
$Compose = Join-Path $Root 'docker-compose.demo.yml'
. "$PSScriptRoot\credenciales-comun.ps1"

if (-not (Test-Path $EnvDemo)) {
    Copy-Item (Join-Path $Root 'backend\.env.demo.example') $EnvDemo
    Write-Host '  Copiado backend\.env.demo.example → backend\.env.demo'
}
if ((Get-EnvValue $EnvDemo 'TIENDAYA_DEMO') -ne 'true') { throw 'backend\.env.demo no identifica el entorno DEMO.' }

# ── 1. Contraseñas ────────────────────────────────────────────────────────────
# Adopción: primero lo que ya usaba el backend DEMO, luego lo que tiene el contenedor creado.
$uriActual = Get-EnvValue $EnvDemo 'MONGO_URI'
$adoptar = @(
    @('DEMO_MYSQL_ROOT_PASSWORD', $null, 'tiendaya_demo_mysql', 'MYSQL_ROOT_PASSWORD'),
    @('DEMO_MYSQL_PASSWORD', 'MYSQL_PASSWORD', 'tiendaya_demo_mysql', 'MYSQL_PASSWORD'),
    @('DEMO_MONGO_PASSWORD', $null, 'tiendaya_demo_mongo', 'MONGO_INITDB_ROOT_PASSWORD'),
    @('DEMO_NEO4J_PASSWORD', 'NEO4J_PASSWORD', 'tiendaya_demo_neo4j', 'NEO4J_AUTH')
)
foreach ($fila in $adoptar) {
    if (Get-EnvValue $EnvDemo $fila[0]) { continue }
    $valor = if ($fila[1]) { Get-EnvValue $EnvDemo $fila[1] } else { $null }
    if (-not $valor) {
        $valor = Get-ContainerEnv $fila[2] $fila[3]
        if ($fila[3] -eq 'NEO4J_AUTH' -and $valor) { $valor = $valor -replace '^neo4j/', '' }
    }
    # Antes de la Entrega final, el backend DEMO se conectaba a MongoDB como root.
    if (-not $valor -and $fila[0] -eq 'DEMO_MONGO_PASSWORD' -and $uriActual -match '^mongodb://demo_admin:([^@]+)@') {
        $valor = [uri]::UnescapeDataString($Matches[1])
    }
    if ($valor) { Set-EnvValue $EnvDemo $fila[0] $valor }
}

$secretos = @(
    'DEMO_MYSQL_ROOT_PASSWORD', 'DEMO_MYSQL_PASSWORD', 'DEMO_MONGO_PASSWORD', 'DEMO_NEO4J_PASSWORD',
    'DEMO_REDIS_API_PASSWORD', 'DEMO_REDIS_LECTURA_PASSWORD', 'DEMO_REDIS_ADMIN_PASSWORD',
    'DEMO_MONGO_API_PASSWORD', 'DEMO_MONGO_LECTURA_PASSWORD', 'DEMO_MONGO_ADMIN_PASSWORD',
    'DEMO_ELASTIC_PASSWORD', 'DEMO_ES_API_PASSWORD', 'DEMO_ES_INDEXADOR_PASSWORD', 'DEMO_ES_LECTURA_PASSWORD'
)
$creadas = 0
foreach ($nombre in $secretos) {
    if (-not (Get-EnvValue $EnvDemo $nombre)) { Set-EnvValue $EnvDemo $nombre (New-Secret); $creadas++ }
}

# El backend DEMO con su usuario de menor privilegio en cada motor.
$servidorMongo = if ($uriActual -match '@([^/?]+)' -or $uriActual -match '^mongodb://([^/?@]+)') { $Matches[1] } else { '127.0.0.1:27117' }
$backend = [ordered]@{
    'MYSQL_PASSWORD' = (Get-EnvValue $EnvDemo 'DEMO_MYSQL_PASSWORD')
    'NEO4J_PASSWORD' = (Get-EnvValue $EnvDemo 'DEMO_NEO4J_PASSWORD')
    'MONGO_URI'      = "mongodb://tiendaya_api:$(Get-EnvValue $EnvDemo 'DEMO_MONGO_API_PASSWORD')@$servidorMongo/tiendaya_demo?authSource=tiendaya_demo"
    'REDIS_USERNAME' = 'tiendaya_api'
    'REDIS_PASSWORD' = (Get-EnvValue $EnvDemo 'DEMO_REDIS_API_PASSWORD')
    'ES_USERNAME'    = 'tiendaya_api'
    'ES_PASSWORD'    = (Get-EnvValue $EnvDemo 'DEMO_ES_API_PASSWORD')
}
foreach ($nombre in $backend.Keys) {
    if ((Get-EnvValue $EnvDemo $nombre) -ne $backend[$nombre]) { Set-EnvValue $EnvDemo $nombre $backend[$nombre] }
}
$clave = Get-EnvValue $EnvDemo 'SECRET_KEY'
if (-not $clave -or $clave -like '*REEMPLAZAR*') { Set-EnvValue $EnvDemo 'SECRET_KEY' ((New-Secret) + (New-Secret)); $creadas++ }
Write-Host "  Credenciales DEMO: $creadas nueva(s); las existentes se conservaron." -ForegroundColor Green
if ($SoloCredenciales) { return }

# ── 2 y 3. Contenedores y usuarios ────────────────────────────────────────────
docker compose -f $Compose --env-file $EnvDemo --project-name tiendaya_demo up -d
if ($LASTEXITCODE -ne 0) { throw 'docker compose up de la DEMO falló.' }

$demo = Read-EnvFile $EnvDemo
Write-Host '  Esperando MongoDB DEMO...' -ForegroundColor Yellow
Wait-ContainerHealthy 'tiendaya_demo_mongo' 240
Set-MongoUsuarios 'tiendaya_demo_mongo' 'demo_admin' $demo['DEMO_MONGO_PASSWORD']

Write-Host '  Esperando Elasticsearch DEMO...' -ForegroundColor Yellow
Wait-ContainerHealthy 'tiendaya_demo_elasticsearch' 300
$claves = @{
    'ES_API_PASSWORD'       = $demo['DEMO_ES_API_PASSWORD']
    'ES_INDEXADOR_PASSWORD' = $demo['DEMO_ES_INDEXADOR_PASSWORD']
    'ES_LECTURA_PASSWORD'   = $demo['DEMO_ES_LECTURA_PASSWORD']
}
Set-ElasticsearchSeguridad 'http://127.0.0.1:9210' $demo['DEMO_ELASTIC_PASSWORD'] $claves $Root
Wait-ContainerHealthy 'tiendaya_demo_redis' 60
Write-Host '  Control de acceso de la DEMO configurado.' -ForegroundColor Green
