#!/usr/bin/env bash
# InkPulse Hub 一键启动 — Linux / macOS / WSL
#
# 用法:
#   ./run.sh                      # 自动建 venv、装依赖、起服务(0.0.0.0:8080)
#   INKPULSE_PORT=9000 ./run.sh   # 换端口
#   INKPULSE_CONFIG=~/my.yaml ./run.sh
#
# 幂等: venv 已在则跳过创建; 依赖已装则跳过安装。删掉 .venv 即可重建。
set -euo pipefail

# 切到脚本所在目录(无论从哪调用)
cd "$(dirname "$(readlink -f "$0" 2>/dev/null || echo "$0")")"

VENV=".venv"
PY_BIN="$VENV/bin/python"

# 1) 找一个 >=3.11 的解释器(仅在需要新建 venv 时用)
find_python() {
  for c in python3.13 python3.12 python3.11 python3 python; do
    if command -v "$c" >/dev/null 2>&1; then
      if "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)' 2>/dev/null; then
        echo "$c"; return 0
      fi
    fi
  done
  return 1
}

# 2) 没有 venv 就创建
if [ ! -x "$PY_BIN" ]; then
  echo "[run] 未发现 venv, 正在创建 $VENV ..."
  HOST_PY="$(find_python)" || {
    echo "[run] 错误: 找不到 Python >=3.11, 请先安装。" >&2
    exit 1
  }
  "$HOST_PY" -m venv "$VENV"
fi

# 3) 依赖没装好就安装(以能否 import uvicorn+inkpulse_hub 判断)
if ! "$PY_BIN" -c 'import uvicorn, inkpulse_hub' >/dev/null 2>&1; then
  echo "[run] 安装依赖 (pip install -e .) ..."
  "$PY_BIN" -m pip install --upgrade pip >/dev/null
  "$PY_BIN" -m pip install -e .
fi

# 4) 选配置: 已设 INKPULSE_CONFIG 则尊重; 否则默认 ~/inkpulse-config.yaml(存在才用)
if [ -z "${INKPULSE_CONFIG:-}" ] && [ -f "$HOME/inkpulse-config.yaml" ]; then
  export INKPULSE_CONFIG="$HOME/inkpulse-config.yaml"
fi

echo "[run] 启动 InkPulse Hub (端口 ${INKPULSE_PORT:-8080})"
echo "[run] 配置: ${INKPULSE_CONFIG:-<默认值>}"
exec "$PY_BIN" -m inkpulse_hub
