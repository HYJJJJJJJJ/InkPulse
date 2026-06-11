#!/usr/bin/env bash
# InkPulse 固件构建脚本 (Linux / macOS / WSL)
#
# 用法:
#   ./build.sh setup          首次: 设置目标芯片 esp32s3
#   ./build.sh build          编译(默认)
#   ./build.sh flash          烧录 (端口用 $PORT 或 -p, 见下)
#   ./build.sh monitor        看串口日志 (Ctrl+] 退出)
#   ./build.sh fm             flash + monitor 一步到位
#   ./build.sh verify         以 bring-up 验证模式编译(温湿度+白黑红, 不联网)
#   ./build.sh clean          清理
#   ./build.sh <任意 idf.py 子命令...>   透传给 idf.py
#
# 串口: 设环境变量 PORT, 例如  PORT=/dev/ttyUSB0 ./build.sh fm
#       或直接   ./build.sh flash -p /dev/ttyUSB0
# ESP-IDF 路径: 默认 ~/esp/esp-idf, 可用 IDF_PATH 覆盖。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

TARGET="esp32s3"
: "${IDF_PATH:=$HOME/esp/esp-idf}"

# 确保 idf.py 在 PATH; 不在则 source export.sh
if ! command -v idf.py >/dev/null 2>&1; then
    if [ -f "$IDF_PATH/export.sh" ]; then
        echo "[build] 激活 ESP-IDF 环境: $IDF_PATH"
        # shellcheck disable=SC1091
        . "$IDF_PATH/export.sh"
    else
        echo "[build] 错误: 找不到 idf.py, 也找不到 $IDF_PATH/export.sh" >&2
        echo "        请先安装 ESP-IDF 或设 IDF_PATH 指向其根目录。" >&2
        exit 1
    fi
fi

PORT_ARGS=()
[ -n "${PORT:-}" ] && PORT_ARGS=(-p "$PORT")

cmd="${1:-build}"
[ $# -gt 0 ] && shift || true

case "$cmd" in
    setup)
        idf.py set-target "$TARGET" ;;
    build)
        # 显式 =0: 清掉 verify 残留在 CMake cache 里的 INKPULSE_VERIFY, 否则会一直跑验证模式
        idf.py -DINKPULSE_VERIFY=0 build ;;
    verify)
        # bring-up 验证模式: 注入 INKPULSE_VERIFY 宏(温湿度 + 白黑红+分屏+棋盘, 不联网)
        idf.py -DINKPULSE_VERIFY=1 build ;;
    flash)
        idf.py "${PORT_ARGS[@]}" flash "$@" ;;
    monitor)
        idf.py "${PORT_ARGS[@]}" monitor "$@" ;;
    fm|flash-monitor)
        idf.py "${PORT_ARGS[@]}" flash monitor "$@" ;;
    clean)
        idf.py fullclean ;;
    *)
        idf.py "$cmd" "$@" ;;
esac
