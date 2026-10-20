$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'start-demo-original.ps1')
if ($LASTEXITCODE -ne 0) { throw 'No se pudo iniciar la presentación.' }
