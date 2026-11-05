# =============================================================================
# TiendaYa — Paquete de datos de volumen (los mismos datos en todas las PCs)
#
#   .\scripts\volumen-datos.ps1 -Exportar   Guarda la base llena de esta PC en database\volumen\
#   .\scripts\volumen-datos.ps1 -Cargar     Reemplaza la base de esta PC con ese paquete
#
# Qué contiene el paquete:
#   mysql.sql.gz        MySQL completo (autoridad: usuarios, pedidos, pagos, reseñas, fotos de producto)
#   mongo.archive.gz    MongoDB tiendaya (catálogo, eventos, tiendas)
#   ledger.db           Libro de la pasarela de pagos simulada (debe coincidir con los pagos)
#   resenas.zip         Fotos de reseñas (backend\static\reviews)
#
# Cassandra, Neo4j, Elasticsearch, Redis y las copias de respaldo NO van en el paquete:
# son proyecciones y se reconstruyen desde MySQL/MongoDB al cargar, igual que en setup.ps1.
#
# Solo datos: no toca usuarios ni contraseñas de las bases (cada PC conserva su .env).
# Requisitos para cargar: Docker levantado, setup.ps1 ya ejecutado una vez, y el backend
# y la pasarela APAGADOS (puertos 8000 y 8001 libres).
# =============================================================================
param(
    [switch]$Exportar,
    [switch]$Cargar,
    [switch]$SinConfirmar
)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
. "$PSScriptRoot\credenciales-comun.ps1"

$Paquete = Join-Path $Root 'database\volumen'
$Python = Join-Path $Root 'backend\venv\Scripts\python.exe'
$Ledger = Join-Path $Root 'payment_simulator\ledger.db'
$Resenas = Join-Path $Root 'backend\static\reviews'
$MySQL = 'tiendaya_mysql'
$Mongo = 'tiendaya_mongo'

function Paso([string]$Texto) { Write-Host "`n== $Texto" -ForegroundColor Cyan }

function Exigir([string]$Que) {
    if ($LASTEXITCODE -ne 0) { throw "Falló: $Que (código $LASTEXITCODE)" }
}

function Puerto-Ocupado([int]$Puerto) {
    return [bool](Get-NetTCPConnection -LocalPort $Puerto -State Listen -ErrorAction SilentlyContinue)
}

function Verificar-Contenedores {
    foreach ($c in @($MySQL, $Mongo)) {
        $estado = docker inspect $c --format '{{.State.Health.Status}}' 2>$null
        if ($estado -ne 'healthy') {
            throw "El contenedor $c no está listo ($estado). Ejecute 'docker compose up -d' y espere."
        }
    }
}

if ($Exportar -eq $Cargar) {
    Write-Host 'Uso: .\scripts\volumen-datos.ps1 -Exportar   o   .\scripts\volumen-datos.ps1 -Cargar'
    exit 1
}

Verificar-Contenedores

# ── Exportar ─────────────────────────────────────────────────────────────────
if ($Exportar) {
    if (Puerto-Ocupado 8000) {
        Write-Host 'Aviso: el backend está encendido. Se exporta igual (copia consistente de MySQL),' -ForegroundColor Yellow
        Write-Host 'pero lo ideal es apagarlo para que el outbox no quede a medio procesar.' -ForegroundColor Yellow
    }
    New-Item -ItemType Directory -Force $Paquete | Out-Null

    Paso 'MySQL'
    # Las contraseñas no salen del contenedor: se usan sus propias variables de entorno.
    docker exec $MySQL sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysqldump -uroot --single-transaction --routines --triggers --hex-blob --default-character-set=utf8mb4 --no-tablespaces "${MYSQL_DATABASE:-tiendaya}" | gzip > /tmp/volumen_mysql.sql.gz'
    Exigir 'mysqldump'
    docker cp "${MySQL}:/tmp/volumen_mysql.sql.gz" (Join-Path $Paquete 'mysql.sql.gz'); Exigir 'copiar dump MySQL'
    docker exec $MySQL rm -f /tmp/volumen_mysql.sql.gz | Out-Null

    Paso 'MongoDB'
    docker exec $Mongo sh -c 'mongodump --quiet -u "$MONGO_INITDB_ROOT_USERNAME" -p "$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin --db "${MONGO_INITDB_DATABASE:-tiendaya}" --archive=/tmp/volumen_mongo.archive.gz --gzip'
    Exigir 'mongodump'
    docker cp "${Mongo}:/tmp/volumen_mongo.archive.gz" (Join-Path $Paquete 'mongo.archive.gz'); Exigir 'copiar dump MongoDB'
    docker exec $Mongo rm -f /tmp/volumen_mongo.archive.gz | Out-Null

    Paso 'Pasarela de pagos'
    if (-not (Test-Path $Ledger)) { throw "No existe $Ledger" }
    if (Puerto-Ocupado 8001) {
        # Copia en caliente con la API de respaldo de SQLite (no deja el archivo a medias).
        & $Python -c "import sqlite3,sys; s=sqlite3.connect(sys.argv[1]); d=sqlite3.connect(sys.argv[2]); s.backup(d); d.close(); s.close()" $Ledger (Join-Path $Paquete 'ledger.db')
        Exigir 'copiar ledger'
    } else {
        Copy-Item $Ledger (Join-Path $Paquete 'ledger.db') -Force
    }

    Paso 'Fotos de reseñas'
    $zip = Join-Path $Paquete 'resenas.zip'
    if (Test-Path $zip) { Remove-Item $zip -Force }
    if (Test-Path $Resenas) { Compress-Archive -Path (Join-Path $Resenas '*') -DestinationPath $zip }

    Get-ChildItem $Paquete | Select-Object Name, @{n='MB'; e={[math]::Round($_.Length / 1MB, 1)}} | Format-Table -AutoSize
    Write-Host "Paquete listo en $Paquete" -ForegroundColor Green
    exit 0
}

# ── Cargar ───────────────────────────────────────────────────────────────────
foreach ($archivo in @('mysql.sql.gz', 'mongo.archive.gz', 'ledger.db')) {
    if (-not (Test-Path (Join-Path $Paquete $archivo))) { throw "Falta $archivo en $Paquete. ¿Hiciste git pull?" }
}
if (-not (Test-Path $Python)) { throw 'No existe backend\venv. Ejecute primero .\scripts\setup.ps1' }
foreach ($puerto in 8000, 8001) {
    if (Puerto-Ocupado $puerto) {
        throw "El puerto $puerto está en uso. Apague el backend y la pasarela (cierre start-dev) antes de cargar."
    }
}

Write-Host 'ADVERTENCIA: se REEMPLAZAN los datos de MySQL, MongoDB y la pasarela de esta PC' -ForegroundColor Red
Write-Host 'por los del paquete. Cassandra, Neo4j, Elasticsearch y Redis se reconstruyen.' -ForegroundColor Red
if (-not $SinConfirmar) {
    if ((Read-Host "Escribe 'si' para continuar") -ne 'si') { Write-Host 'Cancelado.'; exit 1 }
}

$respaldo = Join-Path $Root ("backups\antes-de-volumen-" + (Get-Date -Format 'yyyyMMdd_HHmmss'))
New-Item -ItemType Directory -Force $respaldo | Out-Null

Paso "Respaldo de tus datos actuales en $respaldo"
docker exec $MySQL sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysqldump -uroot --single-transaction --routines --triggers --hex-blob --no-tablespaces "${MYSQL_DATABASE:-tiendaya}" | gzip > /tmp/respaldo_mysql.sql.gz'
Exigir 'respaldo MySQL'
docker cp "${MySQL}:/tmp/respaldo_mysql.sql.gz" (Join-Path $respaldo 'mysql.sql.gz'); Exigir 'copiar respaldo MySQL'
docker exec $Mongo sh -c 'mongodump --quiet -u "$MONGO_INITDB_ROOT_USERNAME" -p "$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin --db "${MONGO_INITDB_DATABASE:-tiendaya}" --archive=/tmp/respaldo_mongo.archive.gz --gzip'
Exigir 'respaldo MongoDB'
docker cp "${Mongo}:/tmp/respaldo_mongo.archive.gz" (Join-Path $respaldo 'mongo.archive.gz'); Exigir 'copiar respaldo MongoDB'
if (Test-Path $Ledger) { Copy-Item $Ledger (Join-Path $respaldo 'ledger.db') }

Paso 'MySQL'
docker cp (Join-Path $Paquete 'mysql.sql.gz') "${MySQL}:/tmp/volumen_mysql.sql.gz"; Exigir 'copiar paquete MySQL'
# El dump incluye DROP TABLE + CREATE de cada tabla: queda idéntico al de origen.
docker exec $MySQL sh -c 'gunzip -c /tmp/volumen_mysql.sql.gz | MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot --default-character-set=utf8mb4 "${MYSQL_DATABASE:-tiendaya}" && rm -f /tmp/volumen_mysql.sql.gz'
Exigir 'restaurar MySQL'

Paso 'MongoDB'
docker cp (Join-Path $Paquete 'mongo.archive.gz') "${Mongo}:/tmp/volumen_mongo.archive.gz"; Exigir 'copiar paquete MongoDB'
docker exec $Mongo sh -c 'mongorestore --quiet -u "$MONGO_INITDB_ROOT_USERNAME" -p "$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin --drop --archive=/tmp/volumen_mongo.archive.gz --gzip && rm -f /tmp/volumen_mongo.archive.gz'
Exigir 'restaurar MongoDB'

Paso 'Pasarela de pagos'
Copy-Item (Join-Path $Paquete 'ledger.db') $Ledger -Force

Paso 'Fotos de reseñas'
$zip = Join-Path $Paquete 'resenas.zip'
if (Test-Path $zip) {
    New-Item -ItemType Directory -Force $Resenas | Out-Null
    Expand-Archive -Path $zip -DestinationPath $Resenas -Force
}

# Proyecciones: se reconstruyen desde las autoridades (igual que setup.ps1).
Push-Location (Join-Path $Root 'backend')
try {
    Paso 'Migraciones pendientes (por si el paquete es de una versión anterior)'
    & $Python scripts\apply_historical_reconciliations.py; Exigir 'migración de conciliaciones'

    Paso 'Cassandra'
    & $Python scripts\backfill_cassandra_analytics.py; Exigir 'Cassandra'
    Paso 'Analítica de respaldo en MySQL'
    & $Python scripts\backfill_mysql_analytics.py --apply; Exigir 'analítica MySQL'
    Paso 'Neo4j (compras y reseñas)'
    # El backfill es aditivo: se vacía el grafo (es una proyección de MySQL) para que no
    # queden compras de pedidos que ya no existen en los datos cargados.
    & $Python -c "from app.core.db_neo4j import get_driver; s=get_driver().session(); s.run('MATCH (n) DETACH DELETE n').consume(); s.close(); print('grafo vaciado')"
    Exigir 'vaciar Neo4j'
    & $Python scripts\backfill_neo4j_reviews.py --apply; Exigir 'Neo4j'
    Paso 'Proyecciones de MongoDB y copia del catálogo'
    & $Python scripts\sync_mongo_projections.py; Exigir 'proyecciones MongoDB'
    & $Python scripts\sync_catalogo_respaldo.py; Exigir 'copia del catálogo'

    Paso 'Elasticsearch (búsqueda y vectores)'
    $env:ES_USERNAME = 'tiendaya_indexador'
    $env:ES_PASSWORD = Get-EnvValue (Join-Path $Root '.env') 'ES_INDEXADOR_PASSWORD'
    try {
        & $Python scripts\reindex_search.py --recrear; Exigir 'reindexado'
    } finally {
        Remove-Item Env:ES_USERNAME, Env:ES_PASSWORD -ErrorAction SilentlyContinue
    }

    Paso 'Caché de recomendaciones y análisis de fraude'
    & $Python -c "from app.core.db_mysql import SessionLocal; from app.core.db_neo4j import get_driver; from app.services.recommendation_service import recalcular_cache; n=get_driver().session(); db=SessionLocal(); print('recomendaciones en cache:', recalcular_cache(n, db)); db.close(); n.close()"
    Exigir 'caché de recomendaciones'
    # Directo al servicio: run_fraud_analysis.py --once respeta FRAUD_ANALYSIS_ENABLED=false.
    & $Python -c "from app.services.fraud_analysis_service import run_fraud_analysis_once; r=run_fraud_analysis_once('manual'); print('análisis de fraude:', r.get('estado') if isinstance(r, dict) else r)"
    Exigir 'análisis de fraude'

    Paso 'Verificación'
    & $Python scripts\verify_setup.py
    $setupOk = $LASTEXITCODE -eq 0
} finally {
    Pop-Location
}

Write-Host ''
if ($setupOk) {
    Write-Host 'Datos de volumen cargados. Ya puedes iniciar con .\scripts\start-dev.ps1' -ForegroundColor Green
} else {
    Write-Host 'Datos cargados, pero verify_setup reportó problemas (ver arriba).' -ForegroundColor Yellow
}
Write-Host "Tus datos anteriores quedaron respaldados en $respaldo"
Write-Host 'Las cuentas de prueba de siempre siguen igual (password123).'
