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
        docker compose -f compose.production.yaml up -d --build --wait --wait-timeout 180
        if ($LASTEXITCODE -ne 0) {
            docker compose -f compose.production.yaml ps
            throw "GameCrafter 启动失败。请运行 .\scripts\doctor.ps1 production 查看处理建议。"
        }
        & (Join-Path $PSScriptRoot "doctor.ps1") production
        if ($LASTEXITCODE -ne 0) { throw "GameCrafter 已启动，但自检未通过。" }
        Write-Host "请在浏览器打开：http://127.0.0.1:8080"
    }
    elseif ($Action -eq "down") {
        docker compose -f compose.production.yaml down
        if ($LASTEXITCODE -ne 0) { throw "Production stack failed to stop." }
    }
    else {
        & (Join-Path $PSScriptRoot "doctor.ps1") production
        exit $LASTEXITCODE
    }
}
finally {
    Pop-Location
}
