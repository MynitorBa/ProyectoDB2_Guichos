# Funciones compartidas del control de acceso (entorno principal y DEMO).
# Se cargan con:  . "$PSScriptRoot\credenciales-comun.ps1"

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

function Read-EnvFile([string]$Path) {
    $valores = @{}
    Get-Content $Path | Where-Object { $_ -match '^\s*[A-Za-z_][A-Za-z0-9_]*\s*=' } | ForEach-Object {
        $nombre, $valor = $_ -split '=', 2
        $valores[$nombre.Trim()] = $valor.Trim()
    }
    return $valores
}

function New-Secret {
    $bytes = New-Object byte[] 24
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    # Solo letras y números: se usan en URLs de conexión y en archivos de configuración.
    return (($bytes | ForEach-Object { $_.ToString('x2') }) -join '')
}

# Valor de una variable de entorno de un contenedor ya creado (la contraseña con la que se creó
# su volumen). $null si el contenedor no existe.
function Get-ContainerEnv([string]$Contenedor, [string]$Variable) {
    $valores = docker inspect $Contenedor --format '{{range .Config.Env}}{{println .}}{{end}}' 2>$null
    if ($LASTEXITCODE -ne 0) { return $null }
    $linea = $valores | Where-Object { $_ -like "$Variable=*" } | Select-Object -First 1
    if ($linea) { return ($linea -split '=', 2)[1] } else { return $null }
}

function Wait-ContainerHealthy([string]$Contenedor, [int]$Segundos = 240) {
    $limite = (Get-Date).AddSeconds($Segundos)
    while ((docker inspect $Contenedor --format '{{.State.Health.Status}}' 2>$null) -ne 'healthy') {
        if ((Get-Date) -gt $limite) { throw "$Contenedor no quedó saludable." }
        Start-Sleep 2
    }
}

# Crea o actualiza los usuarios de MongoDB con database/mongo/03_usuarios.js, montado en el
# contenedor; las contraseñas las toma del entorno del contenedor.
function Set-MongoUsuarios([string]$Contenedor, [string]$RootUser, [string]$RootPass) {
    if (-not $RootPass) { throw "Falta la contraseña root de $Contenedor." }
    docker exec $Contenedor mongosh --quiet -u $RootUser -p $RootPass --authenticationDatabase admin `
        /docker-entrypoint-initdb.d/03_usuarios.js
    if ($LASTEXITCODE -ne 0) { throw "No se pudieron crear los usuarios de MongoDB en $Contenedor." }
}

# Crea o actualiza los roles y usuarios de database/elasticsearch/seguridad.json. $Claves asocia
# el nombre de variable de cada usuario (ES_API_PASSWORD…) con su contraseña.
function Set-ElasticsearchSeguridad([string]$Url, [string]$ElasticPass, [hashtable]$Claves, [string]$Root) {
    if (-not $ElasticPass) { throw 'Falta la contraseña del superusuario elastic.' }
    $par = "elastic:$ElasticPass"
    $cabeceras = @{ Authorization = 'Basic ' + [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($par)) }
    $seguridad = Get-Content (Join-Path $Root 'database\elasticsearch\seguridad.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    foreach ($rol in $seguridad.roles.PSObject.Properties) {
        $cuerpo = $rol.Value | Select-Object cluster, indices | ConvertTo-Json -Depth 6
        Invoke-RestMethod -Method Put -Uri "$Url/_security/role/$($rol.Name)" -Headers $cabeceras `
            -ContentType 'application/json' -Body $cuerpo | Out-Null
    }
    foreach ($usuario in $seguridad.usuarios.PSObject.Properties) {
        $clave = $Claves[$usuario.Value.variable]
        if (-not $clave) { throw "Falta $($usuario.Value.variable)." }
        $cuerpo = @{ password = $clave; roles = @($usuario.Value.roles) } | ConvertTo-Json
        Invoke-RestMethod -Method Put -Uri "$Url/_security/user/$($usuario.Name)" -Headers $cabeceras `
            -ContentType 'application/json' -Body $cuerpo | Out-Null
    }
    Write-Host "  Usuarios de Elasticsearch: $(($seguridad.usuarios.PSObject.Properties.Name) -join ', ')"
}
