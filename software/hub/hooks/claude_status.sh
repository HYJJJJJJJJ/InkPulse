#!/usr/bin/env bash
# Claude Code hook：把状态上报给 InkPulse Hub。
# 用法：在 ~/.claude/settings.json 的 hooks 中调用，传入状态名作为 $1。
# 例：claude_status.sh working / waiting_for_input / done / error
HUB="${INKPULSE_HUB:-http://127.0.0.1:8080}"
STATE="${1:-idle}"
PROJECT="$(basename "$PWD")"
curl -s -m 2 -X POST "$HUB/ingest/claude-status" \
  -H 'Content-Type: application/json' \
  -d "{\"state\":\"$STATE\",\"project\":\"$PROJECT\"}" >/dev/null 2>&1 || true
