[CmdletBinding()]
param(
    [ValidateSet("up", "down", "status")]
    [string]$Action = "up"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repoRoot = Split-Path -Parent $PSScriptRoot
Push-Location $repoRoot
try {
    if ($Action -eq "up") {
        docker compose -f compose.production.yaml up -d --build
        if ($LASTEXITCODE -ne 0) { throw "Production stack failed to start." }
        Write-Host "GameCrafter production preview: http://127.0.0.1:8080"
    }
    elseif ($Action -eq "down") {
        docker compose -f compose.production.yaml down
        if ($LASTEXITCODE -ne 0) { throw "Production stack failed to stop." }
    }
    else {
        docker compose -f compose.production.yaml ps
        if ($LASTEXITCODE -ne 0) { throw "Production stack status failed." }
    }
}
finally {
    Pop-Location
}
