[CmdletBinding()]
param(
    [ValidateSet("install", "status")]
    [string]$Action = "status"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repoRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    throw "The project environment is missing. Run .\scripts\setup.ps1 first."
}

Push-Location $repoRoot
try {
    switch ($Action) {
        "install" {
            & $python -m playwright install --only-shell chromium
            if ($LASTEXITCODE -ne 0) {
                throw "The Playwright Chromium headless shell failed to install."
            }
            Write-Host "The isolated Playwright Chromium headless shell is installed."
        }
        "status" {
            $browserRoot = if ($env:PLAYWRIGHT_BROWSERS_PATH) {
                $env:PLAYWRIGHT_BROWSERS_PATH
            }
            else {
                Join-Path $env:LOCALAPPDATA "ms-playwright"
            }
            if (-not (Test-Path -LiteralPath $browserRoot)) {
                Write-Host "No Playwright browser runtime is installed."
                Write-Host "Install it only when needed with .\scripts\browser.ps1 install."
            }
            else {
                & $python -m playwright install --list
                if ($LASTEXITCODE -ne 0) {
                    throw "Could not read the Playwright browser status."
                }
            }
        }
    }
}
finally {
    Pop-Location
}
