#!/usr/bin/env bash
# 下载 InkPulse hub 渲染所需的中文字体(不入库, 体积大)。
#
# 选定字体(2026-06-12 真机验证): 思源黑体 Medium。
# 思源黑 = Adobe Source Han Sans = Google Noto Sans CJK(同源), 这里取 Noto Sans CJK SC Medium。
# widgets.py 默认从本目录加载 SiYuanHei-Medium.otf。
set -euo pipefail
cd "$(dirname "$0")"

declare -A FONTS=(
  ["SiYuanHei-Medium.otf"]="https://raw.githubusercontent.com/notofonts/noto-cjk/main/Sans/OTF/SimplifiedChinese/NotoSansCJKsc-Medium.otf"
)

for out in "${!FONTS[@]}"; do
  echo "下载 $out ..."
  curl -L --retry 4 --retry-all-errors -C - --max-time 300 -o "$out" "${FONTS[$out]}"
  if file "$out" | grep -qE "TrueType|OpenType"; then
    echo "  OK $(du -h "$out" | cut -f1)"
  else
    echo "  ✗ 下载失败(非字体文件): $out" >&2
    rm -f "$out"; exit 1
  fi
done
echo "字体就绪。"
