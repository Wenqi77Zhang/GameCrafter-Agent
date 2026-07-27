[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repoRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    throw "The project environment is missing. Run .\scripts\setup.ps1 first."
}

$pnpm = Get-Command pnpm -ErrorAction SilentlyContinue
if (-not $pnpm) {
    throw "pnpm was not found."
}

Push-Location $repoRoot
try {
    & $python -m ruff format --check src tests apps/api
    & $python -m ruff check src tests apps/api
    & $python -m pytest
    & $pnpm.Source check:web
    & $pnpm.Source test:web
    & $pnpm.Source build:web
    Write-Host "All GameCrafter M0 checks passed."
}
finally {
    Pop-Location
}
