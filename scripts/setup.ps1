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
    }

    & $venvPython -m pip install --upgrade pip
    & $venvPython -m pip install -e ".[dev]"

    $pnpm = Get-Command pnpm -ErrorAction SilentlyContinue
    if (-not $pnpm) {
        throw "pnpm 10+ was not found. Install pnpm and reopen PowerShell."
    }
    & $pnpm.Source install

    $envPath = Join-Path $repoRoot ".env"
    if (-not (Test-Path -LiteralPath $envPath)) {
        Copy-Item -LiteralPath (Join-Path $repoRoot ".env.example") -Destination $envPath
        Write-Host "Created .env from safe placeholders. Add keys locally only when needed."
    }

    Write-Host "GameCrafter setup complete."
}
finally {
    Pop-Location
}
