# 微博方向社交机器人检测V1.0

[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent $ScriptDir
$LogsDir = Join-Path $ScriptDir "logs"
$StopLog = Join-Path $LogsDir "stop_latest.log"
$Backend = Join-Path $Root "源代码\backend"
$PidFile = Join-Path $Backend "storage\app.pid"

New-Item -ItemType Directory -Force $LogsDir | Out-Null
try {
    Start-Transcript -Path $StopLog -Force | Out-Null
}
catch {
}

try {
    if (-not (Test-Path $PidFile)) {
        Write-Host "未发现运行中的系统进程。"
        exit 0
    }

    $pidValue = Get-Content $PidFile -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $pidValue) {
        Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
        Write-Host "PID文件为空，已清理。"
        exit 0
    }

    $process = Get-Process -Id $pidValue -ErrorAction SilentlyContinue
    if ($process) {
        Stop-Process -Id $pidValue -Force
    }

    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
    Write-Host "系统已停止。"
    Write-Host "停止日志: $StopLog"
}
finally {
    try {
        Stop-Transcript | Out-Null
    }
    catch {
    }
}
