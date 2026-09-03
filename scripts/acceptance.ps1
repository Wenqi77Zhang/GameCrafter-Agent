[CmdletBinding()]
param(
    [string]$DatabaseUrl = $env:GAMECRAFTER_TEST_DATABASE_URL
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repoRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    throw "The project environment is missing. Run .\scripts\setup.ps1 first."
}
if ([string]::IsNullOrWhiteSpace($DatabaseUrl)) {
    throw "Set GAMECRAFTER_TEST_DATABASE_URL to a disposable local database whose name contains 'test' or 'acceptance'."
}

$safetyCode = 'import sys; from sqlalchemy.engine import make_url; url = make_url(sys.argv[1]); host = (url.host or "").lower(); database = (url.database or "").lower(); message = "acceptance database must use localhost" if host not in {"127.0.0.1", "localhost"} else ("acceptance database name must contain test or acceptance" if "test" not in database and "acceptance" not in database else ""); sys.exit(message) if message else print("safe")'
$safety = & $python -c $safetyCode $DatabaseUrl
if ($LASTEXITCODE -ne 0 -or $safety -ne "safe") {
    throw "Acceptance database safety validation failed."
}

$previousDatabaseUrl = $env:GAMECRAFTER_DATABASE_URL
$previousTestUrl = $env:GAMECRAFTER_TEST_DATABASE_URL
$tempName = ".pytest-acceptance-$PID"

Push-Location $repoRoot
try {
    $env:GAMECRAFTER_DATABASE_URL = $DatabaseUrl
    $env:GAMECRAFTER_TEST_DATABASE_URL = $DatabaseUrl
    & $python -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) { throw "Acceptance database migration failed." }
    & $python -m pytest -q tests/postgres/test_nte_knowledge_acceptance.py tests/postgres/test_portability_recovery_acceptance.py --basetemp=$tempName
    if ($LASTEXITCODE -ne 0) { throw "PostgreSQL knowledge/recovery acceptance failed." }
    Write-Host "PostgreSQL acceptance passed: NTE exact offline replay used zero tokens and private evidence survived verified export/delete/restore."
}
finally {
    if ($null -eq $previousDatabaseUrl) {
        Remove-Item Env:GAMECRAFTER_DATABASE_URL -ErrorAction SilentlyContinue
    }
    else {
        $env:GAMECRAFTER_DATABASE_URL = $previousDatabaseUrl
    }
    if ($null -eq $previousTestUrl) {
        Remove-Item Env:GAMECRAFTER_TEST_DATABASE_URL -ErrorAction SilentlyContinue
    }
    else {
        $env:GAMECRAFTER_TEST_DATABASE_URL = $previousTestUrl
    }
    Pop-Location
}
