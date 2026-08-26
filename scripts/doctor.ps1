[CmdletBinding()]
param(
    [ValidateSet("auto", "production", "development")]
    [string]$Mode = "auto"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repoRoot = Split-Path -Parent $PSScriptRoot
$expectedVersion = "1.0.0"
$expectedPhase = "M14-local"
$problems = [System.Collections.Generic.List[string]]::new()

function Test-HttpEndpoint {
    param([Parameter(Mandatory)][string]$Uri)

    try {
        return Invoke-RestMethod -Uri $Uri -TimeoutSec 5
    }
    catch {
        return $null
    }
}

function Add-Problem {
    param([Parameter(Mandatory)][string]$Message)

    $problems.Add($Message)
    Write-Host "[需要处理] $Message" -ForegroundColor Yellow
}

Push-Location $repoRoot
try {
    $productionHealth = Test-HttpEndpoint "http://127.0.0.1:8080/health"
    $developmentHealth = Test-HttpEndpoint "http://127.0.0.1:8000/health"
    if ($Mode -eq "auto") {
        if ($productionHealth) { $Mode = "production" }
        elseif ($developmentHealth) { $Mode = "development" }
        else { $Mode = "production" }
    }

    Write-Host "GameCrafter 本地自检（$Mode）"
    Write-Host "--------------------------------"

    if ($Mode -eq "production") {
        $docker = Get-Command docker -ErrorAction SilentlyContinue
        if (-not $docker) {
            Add-Problem "未找到 Docker。请安装并启动 Docker Desktop。"
        }
        else {
            & $docker.Source info *> $null
            if ($LASTEXITCODE -ne 0) {
                Add-Problem "Docker Desktop 尚未启动。启动后运行 .\scripts\production.ps1 up。"
            }
            else {
                Write-Host "[正常] Docker Desktop 已连接。" -ForegroundColor Green
                $running = @(& $docker.Source compose -f compose.production.yaml ps --services --filter status=running)
                foreach ($service in @("postgres", "api", "worker", "web")) {
                    if ($running -notcontains $service) {
                        Add-Problem "服务 $service 未运行。运行 .\scripts\production.ps1 up 可自动恢复。"
                    }
                }
                if (@("postgres", "api", "worker", "web") | Where-Object { $running -notcontains $_ }) {
                    & $docker.Source compose -f compose.production.yaml ps
                }
                else {
                    Write-Host "[正常] 数据库、接口、后台任务和网页服务均在运行。" -ForegroundColor Green
                }
            }
        }
        $health = $productionHealth
        $webUri = "http://127.0.0.1:8080/"
        $operationsUri = "http://127.0.0.1:8080/api/operations/status"
    }
    else {
        $health = $developmentHealth
        $webUri = "http://127.0.0.1:5173/"
        $operationsUri = "http://127.0.0.1:8000/api/operations/status"
        if (-not (Test-Path -LiteralPath ".venv\Scripts\python.exe")) {
            Add-Problem "项目环境不存在。运行 .\scripts\setup.ps1 完成首次安装。"
        }
    }

    if (-not $health) {
        Add-Problem "接口无法访问。生产模式请运行 .\scripts\production.ps1 up；开发模式请运行 .\scripts\start-background.ps1。"
    }
    elseif ($health.status -ne "ok" -or $health.version -ne $expectedVersion -or $health.phase -ne $expectedPhase) {
        Add-Problem "当前接口不是预期的 GameCrafter $expectedVersion / $expectedPhase，请重新构建并启动。"
    }
    else {
        Write-Host "[正常] 接口版本 $($health.version)，阶段 $($health.phase)。" -ForegroundColor Green
    }

    if (-not (Test-HttpEndpoint $webUri)) {
        Add-Problem "网页无法访问：$webUri"
    }
    else {
        Write-Host "[正常] 网页可访问：$webUri" -ForegroundColor Green
    }

    $operations = Test-HttpEndpoint $operationsUri
    if (-not $operations) {
        Add-Problem "运行状态暂时不可读；若启用了账号，请登录后在“账号”页面查看运行诊断。"
    }
    elseif ($operations.status -ne "ready") {
        Add-Problem "后台任务需要关注：$($operations.attention_codes -join ', ')"
    }
    else {
        Write-Host "[正常] 后台任务可执行，排队 $($operations.queue.queued) 个。" -ForegroundColor Green
    }

    Write-Host "--------------------------------"
    if ($problems.Count -eq 0) {
        Write-Host "自检通过，可以开始使用 GameCrafter。" -ForegroundColor Green
        exit 0
    }

    Write-Host "发现 $($problems.Count) 个需要处理的问题；请按上方提示操作。" -ForegroundColor Yellow
    exit 1
}
finally {
    Pop-Location
}
