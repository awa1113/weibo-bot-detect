# 微博方向社交机器人检测V1.0

[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent $ScriptDir
$LogsDir = Join-Path $ScriptDir "logs"
$StartLog = Join-Path $LogsDir "start_latest.log"
$Backend = Join-Path $Root "源代码\backend"
$Storage = Join-Path $Backend "storage"
$PidFile = Join-Path $Storage "app.pid"
$StdoutLog = Join-Path $Storage "backend_stdout.log"
$StderrLog = Join-Path $Storage "backend_stderr.log"
$VenvPython = Join-Path $Backend ".venv\Scripts\python.exe"
$Port = 18081

function Test-PortInUse {
    param([int]$TestPort)

    try {
        $listener = [System.Net.Sockets.TcpClient]::new()
        $async = $listener.BeginConnect("127.0.0.1", $TestPort, $null, $null)
        $wait = $async.AsyncWaitHandle.WaitOne(500)
        if (-not $wait) {
            $listener.Close()
            return $false
        }
        $listener.EndConnect($async)
        $listener.Close()
        return $true
    }
    catch {
        return $false
    }
}

function Wait-Health {
    param([int]$TimeoutSeconds = 30)

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/api/health" -UseBasicParsing -TimeoutSec 2
            if ($response.StatusCode -eq 200) {
                return $true
            }
        }
        catch {
            Start-Sleep -Seconds 1
        }
    }
    return $false
}

function Get-LanIpAddress {
    $addresses = @(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object {
            $_.IPAddress -notlike "127.*" -and
            $_.IPAddress -notlike "169.254.*" -and
            $_.InterfaceAlias -notmatch "Loopback|vEthernet|Hyper-V|WSL"
        } |
        Select-Object -ExpandProperty IPAddress)

    if ($addresses.Count -gt 0) {
        return $addresses[0]
    }

    return $null
}

New-Item -ItemType Directory -Force $LogsDir | Out-Null
try {
    Start-Transcript -Path $StartLog -Force | Out-Null
}
catch {
}

try {
New-Item -ItemType Directory -Force $Storage | Out-Null

if (-not (Test-Path $VenvPython)) {
    throw "未检测到虚拟环境，请先运行部署脚本。"
}

& $VenvPython -c "import uvicorn, fastapi" *> $null
if ($LASTEXITCODE -ne 0) {
    throw "检测到虚拟环境存在，但核心依赖未安装完整，请先运行一键部署脚本。"
}

if (Test-Path $PidFile) {
    $existingPid = (Get-Content $PidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
    if ($existingPid) {
        $process = Get-Process -Id $existingPid -ErrorAction SilentlyContinue
        if ($process) {
            if (Wait-Health -TimeoutSeconds 2) {
                Write-Host "系统已经在运行，PID=$existingPid" -ForegroundColor Yellow
                Write-Host "本机访问: http://127.0.0.1:$Port"
                $lanIp = Get-LanIpAddress
                if ($lanIp) {
                    Write-Host "局域网访问: http://$($lanIp):$Port"
                }
                exit 0
            }
        }
    }
}

if (Test-PortInUse -TestPort $Port) {
    if (Wait-Health -TimeoutSeconds 2) {
        Write-Host "检测到18081端口已有可用服务，本次不重复启动。" -ForegroundColor Yellow
        Write-Host "本机访问: http://127.0.0.1:$Port"
        exit 0
    }
    throw "18081端口已被其他程序占用，请先释放端口后重试。"
}

$arguments = @("-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "$Port")
$process = Start-Process -FilePath $VenvPython -ArgumentList $arguments -WorkingDirectory $Backend -RedirectStandardOutput $StdoutLog -RedirectStandardError $StderrLog -PassThru -WindowStyle Hidden
Set-Content -Path $PidFile -Value $process.Id -Encoding utf8

if (-not (Wait-Health -TimeoutSeconds 30)) {
    throw "系统启动超时，请检查日志：`n$StdoutLog`n$StderrLog"
}

$lanIp = Get-LanIpAddress
Write-Host "系统启动成功。" -ForegroundColor Green
Write-Host "本机访问: http://127.0.0.1:$Port"
if ($lanIp) {
    Write-Host "局域网访问: http://$($lanIp):$Port"
}
Write-Host "日志文件: $StdoutLog"
Write-Host "启动日志: $StartLog"
}
finally {
    try {
        Stop-Transcript | Out-Null
    }
    catch {
    }
}
