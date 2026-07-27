[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repoRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    throw "The project environment is missing. Run .\scripts\setup.ps1 first."
}

& $python (Join-Path $PSScriptRoot "dev.py")
exit $LASTEXITCODE
