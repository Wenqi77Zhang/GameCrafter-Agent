[CmdletBinding()]
param(
    [ValidateSet("up", "stop", "status", "migrate")]
    [string]$Action = "up"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repoRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
$docker = Get-Command docker -ErrorAction SilentlyContinue

if (-not $docker) {
    throw "Docker CLI was not found. Install and start Docker Desktop, then reopen PowerShell."
}

Push-Location $repoRoot
try {
    switch ($Action) {
        "up" {
            & $docker.Source compose up -d --wait postgres
            if ($LASTEXITCODE -ne 0) { throw "PostgreSQL failed to start." }
            & $python -m alembic upgrade head
            if ($LASTEXITCODE -ne 0) { throw "Database migration failed." }
            Write-Host "GameCrafter PostgreSQL is healthy and migrated."
        }
        "stop" {
            & $docker.Source compose stop postgres
            if ($LASTEXITCODE -ne 0) { throw "PostgreSQL failed to stop." }
        }
        "status" {
            & $docker.Source compose ps postgres
            if ($LASTEXITCODE -ne 0) { throw "Could not read PostgreSQL status." }
        }
        "migrate" {
            if (-not (Test-Path -LiteralPath $python)) {
                throw "The project environment is missing. Run .\scripts\setup.ps1 first."
            }
            & $python -m alembic upgrade head
            if ($LASTEXITCODE -ne 0) { throw "Database migration failed." }
        }
    }
}
finally {
    Pop-Location
}
