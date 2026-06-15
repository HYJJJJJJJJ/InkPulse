# Claude Code ↔ InkPulse 工作任务桥:安装

让 Claude Code 会话自动把任务/焦点推到墨水屏。需 hub 已运行(见 deploy/README.md)。

## 1. A:实时镜像 TodoWrite(hook)

把 `software/hub/hooks/inkpulse_agent_tasks.sh` 配成 PostToolUse(TodoWrite) hook。
在 `~/.claude/settings.json` 的 `hooks` 中加(路径换成你的绝对路径):

```json
{
  "hooks": {
    "PostToolUse": [
      { "matcher": "TodoWrite",
        "hooks": [ { "type": "command",
          "command": "/home/zqx/workspace/InkPulse/software/hub/hooks/inkpulse_agent_tasks.sh" } ] }
    ]
  }
}
```

确保脚本可执行:`chmod +x .../hooks/inkpulse_agent_tasks.sh`。
hub 地址非默认时设环境变量 `INKPULSE_HUB=http://<ip>:8080`。

## 2. B:按需提炼焦点(skill)

把 `software/hub/skills/inkpulse-sync/` 放到 Claude Code 能发现 skill 的位置
(如 `~/.claude/skills/inkpulse-sync/SKILL.md`)。会话里调用该 skill 即把焦点推上屏。

## 3. 上屏

把 `agent_tasks`(标签"工作任务")widget 加进某个布局(`/config` 布局编辑器)。
之后:你让 Claude Code 干活、它更新 TodoWrite → 屏上自动出现当前项目任务。
