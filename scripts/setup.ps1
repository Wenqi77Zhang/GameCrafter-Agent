[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repoRoot = Split-Path -Parent $PSScriptRoot
$venvPath = Join-Path $repoRoot ".venv"
$venvPython = Join-Path $venvPath "Scripts\python.exe"

Push-Location $repoRoot
try {
    if (-not (Test-Path -LiteralPath $venvPython)) {
        $python = Get-Command python -ErrorAction SilentlyContinue
        if (-not $python) {
            throw "Python 3.12+ was not found. Install Python and reopen PowerShell."
        }

        $version = & $python.Source -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
        if ([version]$version -lt [version]"3.12") {
            throw "Python 3.12+ is required; found $version."
        }

        & $python.Source -m venv $venvPath
        if ($LASTEXITCODE -ne 0) { throw "Failed to create the project environment." }
    }

    & $venvPython -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw "Failed to upgrade pip." }

    & $venvPython -m pip install -e ".[dev]"
    if ($LASTEXITCODE -ne 0) { throw "Failed to install Python dependencies." }

    $pnpm = Get-Command pnpm -ErrorAction SilentlyContinue
    if (-not $pnpm) {
        throw "pnpm 10+ was not found. Install pnpm and reopen PowerShell."
    }
    & $pnpm.Source install
    if ($LASTEXITCODE -ne 0) { throw "Failed to install frontend dependencies." }

    $envPath = Join-Path $repoRoot ".env"
    if (-not (Test-Path -LiteralPath $envPath)) {
        Copy-Item -LiteralPath (Join-Path $repoRoot ".env.example") -Destination $envPath
        Write-Host "Created .env from safe placeholders. Add keys locally only when needed."
    }

    Write-Host "GameCrafter setup complete."
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        Write-Warning "Docker Desktop is not installed. It is required for M1 PostgreSQL."
    }
    else {
        Write-Host "Next: .\scripts\database.ps1 up"
    }
}
finally {
    Pop-Location
}
