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
    & $python -m ruff format --check src tests apps/api apps/worker migrations
    if ($LASTEXITCODE -ne 0) { throw "Python formatting check failed." }

    & $python -m ruff check src tests apps/api apps/worker migrations
    if ($LASTEXITCODE -ne 0) { throw "Python lint check failed." }

    & $python -m pytest
    if ($LASTEXITCODE -ne 0) { throw "Python tests failed." }

    & $pnpm.Source check:web
    if ($LASTEXITCODE -ne 0) { throw "Frontend type check failed." }

    & $pnpm.Source test:web
    if ($LASTEXITCODE -ne 0) { throw "Frontend tests failed." }

    & $pnpm.Source build:web
    if ($LASTEXITCODE -ne 0) { throw "Frontend production build failed." }

    Write-Host "All locally available GameCrafter checks passed."
    Write-Host "PostgreSQL tests run when GAMECRAFTER_TEST_DATABASE_URL is configured."
}
finally {
    Pop-Location
}
