#!/usr/bin/env bash
# Claude Code PostToolUse(TodoWrite) hook: 把当前会话任务镜像到 InkPulse Hub。
# 配置: ~/.claude/settings.json 的 hooks.PostToolUse, matcher "TodoWrite", command 指向本脚本。
# stdin 收到 PostToolUse JSON(含 tool_input.todos 与 cwd)。失败绝不阻塞会话。
HUB="${INKPULSE_HUB:-http://127.0.0.1:8080}"
BODY="$(python3 -c '
import sys, json, os
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)
todos = (d.get("tool_input") or {}).get("todos") or []
tasks = [{"content": t.get("content",""), "status": t.get("status","pending")}
         for t in todos if t.get("content")]
project = os.path.basename((d.get("cwd") or "").rstrip("/")) or "?"
print(json.dumps({"project": project, "tasks": tasks}, ensure_ascii=False))
' 2>/dev/null)"
[ -z "$BODY" ] && exit 0
curl -s -m 2 -X POST "$HUB/ingest/agent-tasks" \
  -H 'Content-Type: application/json' -d "$BODY" >/dev/null 2>&1 || true
exit 0
