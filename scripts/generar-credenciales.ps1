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

. "$PSScriptRoot\credenciales-comun.ps1"

foreach ($archivo in @(@($EnvRaiz, '.env.example'), @($EnvBackend, 'backend\.env.example'))) {
    if (-not (Test-Path $archivo[0])) {
        Copy-Item (Join-Path $Root $archivo[1]) $archivo[0]
        Write-Host "  Copiado $($archivo[1]) → $($archivo[0].Replace($Root + '\', ''))"
    }
}

# Una instalación existente ya creó sus volúmenes con las contraseñas de antes (venían fijas en
# el ejemplo o como valor por defecto): se adoptan, nunca se cambian. Primero la de backend\.env;
# si no está, la del contenedor ya creado. Solo en una instalación nueva se genera una.
foreach ($nombre in @('MYSQL_PASSWORD', 'NEO4J_PASSWORD')) {
    $enBackend = Get-EnvValue $EnvBackend $nombre
    if (-not (Get-EnvValue $EnvRaiz $nombre) -and $enBackend) { Set-EnvValue $EnvRaiz $nombre $enBackend }
}
$enContenedores = @(
    @('MYSQL_ROOT_PASSWORD', 'tiendaya_mysql', 'MYSQL_ROOT_PASSWORD'),
    @('MYSQL_PASSWORD', 'tiendaya_mysql', 'MYSQL_PASSWORD'),
    @('MONGO_ROOT_PASSWORD', 'tiendaya_mongo', 'MONGO_INITDB_ROOT_PASSWORD'),
    @('NEO4J_PASSWORD', 'tiendaya_neo4j', 'NEO4J_AUTH')
)
foreach ($fila in $enContenedores) {
    if (Get-EnvValue $EnvRaiz $fila[0]) { continue }
    $valor = Get-ContainerEnv $fila[1] $fila[2]
    if ($fila[2] -eq 'NEO4J_AUTH' -and $valor) { $valor = $valor -replace '^neo4j/', '' }
    if ($valor) { Set-EnvValue $EnvRaiz $fila[0] $valor }
}

# Contraseñas que viven en el .env de la raíz (una por usuario de cada componente).
$secretos = @(
    'MYSQL_ROOT_PASSWORD', 'MYSQL_PASSWORD', 'MONGO_ROOT_PASSWORD', 'NEO4J_PASSWORD',
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
    'MYSQL_PASSWORD' = (Get-EnvValue $EnvRaiz 'MYSQL_PASSWORD')
    'NEO4J_PASSWORD' = (Get-EnvValue $EnvRaiz 'NEO4J_PASSWORD')
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

# Clave con la que el backend firma las sesiones (JWT). Se genera si falta o si sigue siendo
# el texto de ejemplo; cambiarla solo obliga a iniciar sesión de nuevo.
$clave = Get-EnvValue $EnvBackend 'SECRET_KEY'
if (-not $clave -or $clave -match '^(cambia_esto|CAMBIA_ESTO)') {
    Set-EnvValue $EnvBackend 'SECRET_KEY' ((New-Secret) + (New-Secret))
    $creadas++
}

if ($creadas) {
    Write-Host "  Credenciales: $creadas contraseña(s) nueva(s) en .env; recree los contenedores con 'docker compose up -d'." -ForegroundColor Yellow
} else {
    Write-Host '  Credenciales: ya estaban configuradas.' -ForegroundColor Green
}
