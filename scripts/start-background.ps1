[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repoRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
$pnpm = (Get-Command pnpm.cmd -ErrorAction SilentlyContinue).Source
$runtimeDir = Join-Path $repoRoot "data\runtime"
$pidFile = Join-Path $runtimeDir "local-services.json"

if (-not (Test-Path -LiteralPath $python)) {
    throw "The project environment is missing. Run .\scripts\setup.ps1 first."
}
if (-not $pnpm) {
    throw "pnpm was not found. Run .\scripts\setup.ps1 after installing pnpm."
}

function Test-Endpoint {
    param([Parameter(Mandatory)][string]$Uri)

    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $Uri -TimeoutSec 2
        return $response.StatusCode -ge 200 -and $response.StatusCode -lt 500
    }
    catch {
        return $false
    }
}

if ((Test-Endpoint "http://127.0.0.1:5173") -and (Test-Endpoint "http://127.0.0.1:8000/health")) {
    Write-Host "GameCrafter is already running."
    Write-Host "Web: http://127.0.0.1:5173"
    Write-Host "API: http://127.0.0.1:8000/health"
    exit 0
}

New-Item -ItemType Directory -Path $runtimeDir -Force | Out-Null
$existingPythonPath = $env:PYTHONPATH
$env:PYTHONPATH = Join-Path $repoRoot "src"
if ($existingPythonPath) {
    $env:PYTHONPATH += [System.IO.Path]::PathSeparator + $existingPythonPath
}

try {
    $api = Start-Process -FilePath $python `
        -ArgumentList @("-m", "uvicorn", "apps.api.main:app", "--host", "127.0.0.1", "--port", "8000", "--log-level", "info") `
        -WorkingDirectory $repoRoot -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $runtimeDir "api.stdout.log") `
        -RedirectStandardError (Join-Path $runtimeDir "api.stderr.log")

    $worker = Start-Process -FilePath $python `
        -ArgumentList @("-m", "apps.worker.main") `
        -WorkingDirectory $repoRoot -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $runtimeDir "worker.stdout.log") `
        -RedirectStandardError (Join-Path $runtimeDir "worker.stderr.log")

    $web = Start-Process -FilePath $pnpm `
        -ArgumentList @("--dir", "apps/web", "dev", "--", "--host", "127.0.0.1", "--port", "5173", "--strictPort") `
        -WorkingDirectory $repoRoot -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $runtimeDir "web.stdout.log") `
        -RedirectStandardError (Join-Path $runtimeDir "web.stderr.log")
}
finally {
    if ($null -eq $existingPythonPath) { Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue }
    else { $env:PYTHONPATH = $existingPythonPath }
}

@{
    api = $api.Id
    worker = $worker.Id
    web = $web.Id
    started_at = (Get-Date).ToUniversalTime().ToString("o")
} | ConvertTo-Json | Set-Content -LiteralPath $pidFile -Encoding utf8

$deadline = (Get-Date).AddSeconds(30)
do {
    if ((Test-Endpoint "http://127.0.0.1:5173") -and (Test-Endpoint "http://127.0.0.1:8000/health")) {
        Write-Host "GameCrafter started in the background."
        Write-Host "Web: http://127.0.0.1:5173"
        Write-Host "API: http://127.0.0.1:8000/health"
        Write-Host "Stop: .\scripts\stop-background.ps1"
        exit 0
    }
    Start-Sleep -Milliseconds 500
} while ((Get-Date) -lt $deadline)

throw "GameCrafter did not become healthy. Check data\runtime\*.stderr.log."
