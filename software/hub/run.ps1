# InkPulse Hub 一键启动 — Windows (PowerShell / pwsh)
#
# 用法 (在 software\hub 目录):
#   .\run.ps1
#   $env:INKPULSE_PORT=9000; .\run.ps1
#   $env:INKPULSE_CONFIG="$HOME\my.yaml"; .\run.ps1
# 若提示脚本被禁止运行:
#   powershell -ExecutionPolicy Bypass -File .\run.ps1
#
# 幂等: venv 已在则跳过创建; 依赖已装则跳过安装。删掉 .venv 即可重建。
$ErrorActionPreference = "Stop"

# 切到脚本所在目录
Set-Location -Path $PSScriptRoot

$Venv  = ".venv"
$PyBin = Join-Path $Venv "Scripts\python.exe"

# 1) 找一个 >=3.11 的解释器(仅在需要新建 venv 时用)
function Find-Python {
  # Windows 优先 py -3.x 启动器, 再退回 python
  foreach ($args in @("-3.13","-3.12","-3.11")) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
      & py $args -c "import sys; sys.exit(0 if sys.version_info>=(3,11) else 1)" 2>$null
      if ($LASTEXITCODE -eq 0) { return @("py", $args) }
    }
  }
  foreach ($c in @("python","python3")) {
    if (Get-Command $c -ErrorAction SilentlyContinue) {
      & $c -c "import sys; sys.exit(0 if sys.version_info>=(3,11) else 1)" 2>$null
      if ($LASTEXITCODE -eq 0) { return @($c) }
    }
  }
  return $null
}

# 2) 没有 venv 就创建
if (-not (Test-Path $PyBin)) {
  Write-Host "[run] 未发现 venv, 正在创建 $Venv ..."
  $hostPy = Find-Python
  if ($null -eq $hostPy) {
    Write-Error "[run] 找不到 Python >=3.11, 请先安装 (https://www.python.org/downloads/)。"
    exit 1
  }
  & $hostPy[0] $hostPy[1..($hostPy.Length-1)] -m venv $Venv
}

# 3) 依赖没装好就安装
& $PyBin -c "import uvicorn, inkpulse_hub" 2>$null
if ($LASTEXITCODE -ne 0) {
  Write-Host "[run] 安装依赖 (pip install -e .) ..."
  & $PyBin -m pip install --upgrade pip | Out-Null
  & $PyBin -m pip install -e .
}

# 4) 选配置
if (-not $env:INKPULSE_CONFIG) {
  $defaultCfg = Join-Path $HOME "inkpulse-config.yaml"
  if (Test-Path $defaultCfg) { $env:INKPULSE_CONFIG = $defaultCfg }
}

$port = if ($env:INKPULSE_PORT) { $env:INKPULSE_PORT } else { "8080" }
$cfg  = if ($env:INKPULSE_CONFIG) { $env:INKPULSE_CONFIG } else { "<默认值>" }
Write-Host "[run] 启动 InkPulse Hub (端口 $port)"
Write-Host "[run] 配置: $cfg"
& $PyBin -m inkpulse_hub
