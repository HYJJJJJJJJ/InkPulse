# InkPulse 固件构建脚本 (Windows PowerShell)
#
# 用法:
#   .\build.ps1 setup          首次: 设置目标芯片 esp32s3
#   .\build.ps1 build          编译(默认)
#   .\build.ps1 flash          烧录 (端口用 $env:PORT 或 -p, 见下)
#   .\build.ps1 monitor        看串口日志 (Ctrl+] 退出)
#   .\build.ps1 fm             flash + monitor
#   .\build.ps1 verify         bring-up 验证模式(温湿度+白黑红, 不联网)
#   .\build.ps1 clean          清理
#   .\build.ps1 <idf.py 子命令...>   透传给 idf.py
#
# 串口: 设 $env:PORT='COM5'  或  .\build.ps1 flash -p COM5
# ESP-IDF: 默认 $env:USERPROFILE\esp\esp-idf, 可用 $env:IDF_PATH 覆盖。
$ErrorActionPreference = 'Stop'

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

$Target = 'esp32s3'
if (-not $env:IDF_PATH) { $env:IDF_PATH = Join-Path $env:USERPROFILE 'esp\esp-idf' }

# 确保 idf.py 可用; 不在则跑 export.ps1
if (-not (Get-Command idf.py -ErrorAction SilentlyContinue)) {
    $exportPs1 = Join-Path $env:IDF_PATH 'export.ps1'
    if (Test-Path $exportPs1) {
        Write-Host "[build] 激活 ESP-IDF 环境: $env:IDF_PATH"
        . $exportPs1
    } else {
        Write-Error "找不到 idf.py, 也找不到 $exportPs1. 请安装 ESP-IDF 或设 `$env:IDF_PATH."
        exit 1
    }
}

$PortArgs = @()
if ($env:PORT) { $PortArgs = @('-p', $env:PORT) }

if ($args.Count -gt 0) { $cmd = $args[0]; $rest = $args[1..($args.Count-1)] }
else { $cmd = 'build'; $rest = @() }

switch ($cmd) {
    'setup'   { idf.py set-target $Target }
    'build'   { idf.py build }
    'verify'  { idf.py -DINKPULSE_VERIFY=1 build }
    'flash'   { idf.py @PortArgs flash @rest }
    'monitor' { idf.py @PortArgs monitor @rest }
    { $_ -in 'fm','flash-monitor' } { idf.py @PortArgs flash monitor @rest }
    'clean'   { idf.py fullclean }
    default   { idf.py $cmd @rest }
}
