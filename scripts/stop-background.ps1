[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repoRoot = Split-Path -Parent $PSScriptRoot
$pidFile = Join-Path $repoRoot "data\runtime\local-services.json"

if (-not (Test-Path -LiteralPath $pidFile)) {
    Write-Host "No background GameCrafter process record was found."
    exit 0
}

$processes = Get-Content -LiteralPath $pidFile -Raw | ConvertFrom-Json
foreach ($name in @("web", "worker", "api")) {
    $processId = $processes.$name
    if ($processId -and (Get-Process -Id $processId -ErrorAction SilentlyContinue)) {
        & taskkill.exe /PID $processId /T /F | Out-Null
    }
}

Remove-Item -LiteralPath $pidFile -Force
Write-Host "GameCrafter background services stopped."
