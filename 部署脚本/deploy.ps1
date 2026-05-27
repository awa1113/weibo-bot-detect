# 微博方向社交机器人检测V1.0

[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent $ScriptDir
$LogsDir = Join-Path $ScriptDir "logs"
$DeployLog = Join-Path $LogsDir "deploy_latest.log"
$Backend = Join-Path $Root "源代码\backend"
$Frontend = Join-Path $Root "源代码\frontend"
$Port = 18081
$PipIndexUrl = if ($env:PIP_INDEX_URL) { $env:PIP_INDEX_URL } else { "http://pypi.tuna.tsinghua.edu.cn/simple" }
$PipTrustedHost = "pypi.tuna.tsinghua.edu.cn"
$ProxyUrl = if ($env:HTTP_PROXY) { $env:HTTP_PROXY } else { "http://127.0.0.1:7890" }

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Write-Info {
    param([string]$Message)
    Write-Host "[信息] $Message" -ForegroundColor DarkCyan
}

function Resolve-PythonLauncher {
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        return @($python.Source)
    }

    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        return @($py.Source, "-3")
    }

    return @()
}

function Ensure-WingetPackage {
    param(
        [string]$PackageId,
        [string]$DisplayName
    )

    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if (-not $winget) {
        throw "未检测到$DisplayName，且当前系统未安装winget，请先手动安装$DisplayName后重试。"
    }

    Write-Step "未检测到$DisplayName，尝试使用winget自动安装"
    & $winget.Source install -e --id $PackageId --accept-source-agreements --accept-package-agreements
    if ($LASTEXITCODE -ne 0) {
        throw "$DisplayName自动安装失败，请手动安装后重试。"
    }
}

function Invoke-PythonCommand {
    param(
        [string[]]$Launcher,
        [string[]]$Arguments
    )

    $command = $Launcher[0]
    $prefix = @()
    if ($Launcher.Count -gt 1) {
        $prefix = $Launcher[1..($Launcher.Count - 1)]
    }

    & $command @prefix @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Python命令执行失败: $($Arguments -join ' ')"
    }
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

$PythonLauncher = Resolve-PythonLauncher
New-Item -ItemType Directory -Force $LogsDir | Out-Null

try {
    Start-Transcript -Path $DeployLog -Force | Out-Null
}
catch {
    Write-Host "[警告] 无法启动部署日志记录，将继续执行。" -ForegroundColor Yellow
}

try {
    Write-Step "检查基础运行环境"

    if (-not $PythonLauncher) {
        Ensure-WingetPackage -PackageId "Python.Python.3.11" -DisplayName "Python3"
        $PythonLauncher = Resolve-PythonLauncher
        if (-not $PythonLauncher) {
            throw "Python3安装完成后仍未检测到python命令，请重新打开终端后再试。"
        }
    }

    $NodeCommand = Get-Command node -ErrorAction SilentlyContinue
    $NpmCommand = Get-Command npm -ErrorAction SilentlyContinue
    if (-not $NodeCommand -or -not $NpmCommand) {
        Ensure-WingetPackage -PackageId "OpenJS.NodeJS.LTS" -DisplayName "Node.js LTS"
        $NodeCommand = Get-Command node -ErrorAction SilentlyContinue
        $NpmCommand = Get-Command npm -ErrorAction SilentlyContinue
        if (-not $NodeCommand -or -not $NpmCommand) {
            throw "Node.js安装完成后仍未检测到node或npm命令，请重新打开终端后再试。"
        }
    }

    Write-Info ("Python命令：{0}" -f ($PythonLauncher -join " "))
    Write-Info ("Node命令：{0}" -f $NodeCommand.Source)
    Write-Info ("npm命令：{0}" -f $NpmCommand.Source)

    $VenvDir = Join-Path $Backend ".venv"
    $VenvPython = Join-Path $VenvDir "Scripts\python.exe"

    Write-Step "检查并准备Python虚拟环境"
    if (-not (Test-Path $VenvPython)) {
        Invoke-PythonCommand -Launcher $PythonLauncher -Arguments @("-m", "venv", $VenvDir)
    } else {
        Write-Info "检测到已有虚拟环境，直接复用。"
    }

    Write-Step "安装或校验后端依赖"
    & $VenvPython -m pip install --upgrade pip -i $PipIndexUrl --trusted-host $PipTrustedHost
    if ($LASTEXITCODE -ne 0) { throw "pip升级失败。" }
    & $VenvPython -m pip install -r (Join-Path $Backend "requirements.txt") -i $PipIndexUrl --trusted-host $PipTrustedHost
    if ($LASTEXITCODE -ne 0) { throw "后端依赖安装失败。" }
    & $VenvPython -m playwright install chromium
    if ($LASTEXITCODE -ne 0) { throw "Playwright Chromium安装失败。" }

    Write-Step "安装或校验前端依赖"
    Push-Location $Frontend
    try {
        & $NpmCommand.Source install
        if ($LASTEXITCODE -ne 0) {
            throw "前端依赖安装失败。"
        }

        Write-Step "构建前端页面"
        & $NpmCommand.Source run build
        if ($LASTEXITCODE -ne 0) {
            throw "前端构建失败。"
        }
    }
    finally {
        Pop-Location
    }

    $EnvFile = Join-Path $Backend ".env"
    if (-not (Test-Path $EnvFile)) {
        Write-Step "生成默认环境配置"
        Copy-Item (Join-Path $Backend ".env.example") $EnvFile
    } else {
        Write-Info "检测到已有环境配置文件，跳过生成。"
    }

    Write-Step "启动系统"
    & (Join-Path $ScriptDir "start.ps1")
    if ($LASTEXITCODE -ne 0) {
        throw "系统启动失败。"
    }

    $LanIp = Get-LanIpAddress
    Write-Host ""
    Write-Host "部署完成。" -ForegroundColor Green
    Write-Host "本机访问: http://127.0.0.1:$Port"
    if ($LanIp) {
        Write-Host "局域网访问: http://$($LanIp):$Port"
    }
    Write-Host "如需通过路由器NAT访问，请将外网端口映射到本机的${Port}端口。"
    Write-Host "部署日志: $DeployLog"
}
finally {
    try {
        Stop-Transcript | Out-Null
    }
    catch {
    }
}
