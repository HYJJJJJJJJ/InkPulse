# InkPulse 工作任务桥(Claude Code ↔ Hub)设计文档

> 日期:2026-06-14 · 状态:已通过设计评审,待写实现计划
> 关联:`/ingest/claude-status` + `hooks/claude_status.sh`(已有的状态上报雏形)· 待办/日程(手工录入 widget)

## 1. 背景与目标

现有 hub 的数据多靠用户在 `/config` 手工增删。本设计打通 **Claude Code 会话 → hub** 的自动管道,把"我正在干什么"实时推上墨水屏,减少手工维护:

- **A 实时镜像(确定性/hook)**:Claude Code 的 TodoWrite 任务列表随会话变化,经 PostToolUse hook 自动推到屏上。
- **B 按需提炼(skill)**:用户在会话里调用一个 skill,让 AI 提炼当前"工作焦点/持久行动项"推上去。

与手工 `todos` **解耦**:Agent 数据进独立存储 + 专属 widget,互不影响。本期只做 **Claude Code**(Codex 以后再加适配脚本,hub 端接口平台无关)。

### 已核实的机制前提(Claude Code hooks)
- `PostToolUse` hook 支持 `"matcher": "TodoWrite"`。
- hook stdin JSON 含:`tool_name`、`tool_input`(TodoWrite 的 `todos` 数组:`content`/`status`/`activeForm`,`status∈{pending,in_progress,completed}`)、`tool_response`、`cwd`、`session_id`、`transcript_path`。
- shell hook 可读 stdin 并 `curl` POST 到本地;`exit 0` 不阻塞会话(沿用 `claude_status.sh` 策略)。

## 2. 范围

### 本期做(In Scope)
- hub 存储 `AgentTaskStore`(`~/inkpulse/agent_tasks.json`):接收/合并/读取"最近活跃"会话快照。
- hub 端点 `POST /ingest/agent-tasks`。
- `state` 注入 `agent_tasks`;屏上 widget `draw_agent_tasks`,注册为 `agent_tasks`。
- 客户端(随仓库发布 + 安装说明):
  - A:`hooks/inkpulse_agent_tasks.sh`(PostToolUse(TodoWrite) 脚本)+ `~/.claude/settings.json` hooks 片段。
  - B:`skills/inkpulse-sync/SKILL.md`(用户调用的提炼-推送技能)。
- 配套测试。

### 本期不做(Out of Scope / YAGNI)
- 多项目并排显示(只显示最近活跃的单一项目)。
- 跨会话历史 / 任务归档。
- 屏 → 会话的反向控制。
- Codex 适配(hub 接口已平台无关,后续加脚本即可)。
- 把 agent 任务回写进手工 `todos`。
- AI 自动(无人触发)提炼——B 需用户显式调用 skill。

## 3. 决策记录(brainstorm 结论)

| 决策点 | 选择 | 理由 |
|---|---|---|
| 平台 | **先 Claude Code** | 已有状态 hook 基础;TodoWrite+PostToolUse 支撑 A;集成面不翻倍 |
| 待办来源 | **A 镜像 + B 提炼都做** | A 实时确定性,B 按需 AI 判断 |
| 存储 | **独立 `agent_tasks` + 专属 widget** | 与手工 `todos`(长期个人提醒)生命周期不同,解耦防冲掉 |
| 多会话 | **最近活跃者胜出,单一视图** | 贴合"我现在在干嘛";屏上信息聚焦 |
| A 机制 | **PostToolUse(TodoWrite) 实时推送** | 已验证可行;比 hub 轮询 transcript 简单实时 |

## 4. 架构总览

```
Claude Code 会话(任一项目)
 ├─ A: PostToolUse hook (matcher "TodoWrite")
 │    hooks/inkpulse_agent_tasks.sh: 读 stdin JSON → 取 tool_input.todos + cwd
 │    → POST /ingest/agent-tasks {project: basename(cwd), tasks:[{content,status}]}
 └─ B: skill /inkpulse-sync(用户调用)
      AI 提炼当前焦点/行动项 → POST /ingest/agent-tasks {project, highlights:[...]}

hub:
 POST /ingest/agent-tasks → AgentTaskStore(cfg.agent_tasks_store) 写入(按 project 合并)
 build_render_state(now) → state["agent_tasks"] = store.current(now)
 render: placement(widget="agent_tasks")
   └─ _agent_tasks 适配器 → draw_agent_tasks(d, z, state["agent_tasks"])
```

合并规则(单一"最近活跃"快照):
- POST 带 `project` + (可选)`tasks` 和/或 `highlights` + 服务器侧记 `updated_at`。
- **同项目**:更新本次 POST 提供的字段(只给 tasks 则只更新 tasks,highlights 保留;反之亦然)。
- **不同项目**:整体替换为新快照(新 project + 本次字段;另一字段清空)。

### 模块划分(单一职责)
- `collectors/agent_tasks.py`(新增):`AgentTaskStore` —— 读写 + 合并 + `current`。
- `config.py`(改):`agent_tasks_store` 路径字段 + sources 覆盖。
- `state.py`(改):`HubState` 持 store;`build_render_state` 注入 `agent_tasks`。
- `server.py`(改):`POST /ingest/agent-tasks`。
- `render/widgets.py`(改):`draw_agent_tasks`。
- `render/registry.py`(改):注册 `agent_tasks`。
- 客户端:`hooks/inkpulse_agent_tasks.sh`、`skills/inkpulse-sync/SKILL.md`、安装说明(`deploy/README.md` 增补或新文件)。

## 5. 数据模型

### 5.1 存储(`~/inkpulse/agent_tasks.json`)
单一"最近活跃"快照:
```jsonc
{
  "project": "InkPulse",
  "updated_at": 1718000000.0,
  "tasks": [{"content": "写 ingest 端点", "status": "in_progress"},
            {"content": "实现 widget", "status": "pending"}],
  "highlights": ["记得给解析加测试"]
}
```
- `status ∈ {pending, in_progress, completed}`(与 TodoWrite 一致;未知值当 pending)。
- `highlights`:字符串列表(B 提炼),可空。
- 文件不存在/损坏(非 dict / JSON 错)→ 视为空(`current` 返回 None),不抛异常。

### 5.2 `AgentTaskStore`(`collectors/agent_tasks.py`)
```python
class AgentTaskStore:
    def __init__(self, path): ...
    def ingest(self, now, project, tasks=None, highlights=None) -> None:
        # 读旧快照; 若旧.project == project: 合并(仅覆盖传入的非 None 字段);
        # 否则: 新建快照(project + 传入字段, 另一字段为 [] )。统一写 updated_at=now。
        # tasks 规范化: 每项取 {content:str, status:str(三值, 否则 pending)}, 丢弃空 content。
    def current(self, now) -> dict | None:
        # 返回 {project, tasks, highlights, age_s}; 无快照 -> None
```
- `ingest` 的 `tasks`/`highlights` 任一可为 None(表示"本次不更新该字段")。

## 6. 屏上 widget(`draw_agent_tasks`)

```
┌ 工作中 · InkPulse ──────┐
│ ■ 写 ingest 端点           │  ← in_progress
│ □ 实现 agent_tasks widget  │  ← pending
│ ✓ 探索 hook 机制           │  ← completed(带删除线)
│ · 记得给解析加测试          │  ← highlights(有才显示)
│              活跃于 2 分钟前 │
└──────────────────────────┘
```
- 顶部 `_title_bar(f"工作中 · {project}")`(project 超长截断;无 project 兜底「工作中」)。
- `agent_tasks` 为 None → 居中提示「无活动会话」,return。
- 任务行(按存储顺序,按高度截断):状态标记 + content(超长截断):
  - `in_progress` → `■`;`completed` → `✓` + 删除线;其余(pending) → `□`。(字形:`■`/`□`/`✓` 思源黑已确认存在。)
- highlights(若非空):分隔后每条前缀 `·`,同样截断。
- 右下角:`age_s` → 「活跃于 X 分钟前」;若 `age_s` 超过 `STALE_S`(2 小时)→ 显示「会话可能已结束」。
- 纯黑,无红。
- 签名 `draw_agent_tasks(d, z, data)`,`data` 为 `current(now)` 的返回(含 `age_s`)或 None。

## 7. API(`server.py`)

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/ingest/agent-tasks` | body `{project, tasks?, highlights?}`;`project` 空 → 400;`tasks`/`highlights` 缺省表示不更新该字段;调用 `store.ingest(time.time(), ...)` |

- 与现有 `/ingest/claude-status` 同风格(内网上报口,轻校验)。
- `tasks` 元素非 dict / 缺 content 的由 store 规范化时丢弃。

## 8. 客户端(随仓库发布)

### 8.1 A:`hooks/inkpulse_agent_tasks.sh`(PostToolUse TodoWrite)
- 读 stdin JSON;用 `python3 -c`(或 jq)取 `tool_input.todos`(→ `[{content,status}]`)与 `cwd`;`project=basename(cwd)`。
- `curl -s -m 2 -X POST $HUB/ingest/agent-tasks -d '{"project":...,"tasks":[...]}'`;`|| true`;`exit 0`。
- `~/.claude/settings.json` 片段:`hooks.PostToolUse[{matcher:"TodoWrite", hooks:[{type:"command", command:".../inkpulse_agent_tasks.sh"}]}]`。

### 8.2 B:`skills/inkpulse-sync/SKILL.md`
- 描述:用户调用后,让模型**提炼当前会话的工作焦点/持久行动项**(2~5 条简短中文),取当前项目名,`curl` POST 到 `/ingest/agent-tasks` 的 `highlights`(不动 tasks)。
- 仅在用户显式调用时运行(不自动)。

### 8.3 安装说明
- 在 `deploy/README.md`(或新增 `deploy/claude-code.md`)写清:拷脚本、配 settings.json hooks、放 skill、`INKPULSE_HUB` 环境变量。

## 9. 错误处理

- agent_tasks.json 不存在/损坏 → `current` 返回 None,widget 显示「无活动会话」,不崩。
- POST 空 project → 400;tasks 元素畸形 → store 规范化丢弃,不崩。
- hook:hub 不可达 → `curl ... || true` + `exit 0`,绝不阻塞 Claude Code 会话。
- 过期快照(`age_s > STALE_S`)→ widget 标「会话可能已结束」(不自动删除,留最后状态)。
- 单 widget 异常仍由引擎 per-widget 隔离画 `n/a`。

## 10. 测试计划(pytest + 少量 hook 解析测)

- `AgentTaskStore`:首次 ingest 写 tasks;同项目再 ingest highlights → 两者并存;不同项目 ingest → 整体替换(旧字段清空);tasks 规范化(丢空 content / 未知 status→pending);坏文件 → current None;`current` 含 age_s。
- `state`:无快照 → `agent_tasks` None;注入新鲜快照 → dict。
- API:`POST /ingest/agent-tasks` 正常 / 空 project 400 / 只传 highlights 不动 tasks。
- `draw_agent_tasks`:各状态标记(■/□/✓)画出黑像素;highlights 段;空 → 提示不崩;过期 → 「会话可能已结束」;长内容截断不崩。
- `registry`:`agent_tasks` 已注册,注入 state 下绘制不抛错。
- hook 脚本:把 stdin 解析逻辑写成可独立调用的小段(`python3 -c` 同款),给样例 TodoWrite stdin JSON 验证产出的 POST body(`tasks`+`project`)。

## 11. 新增依赖

无。hub 端标准库 + 现有栈;客户端用 `python3`/`curl`(系统自带)。

## 12. 验收标准

1. Claude Code 会话里 TodoWrite 变化时,屏上 `agent_tasks` widget 自动显示该会话任务(状态标记)+ 项目名 + 新鲜度。
2. 用户调用 `/inkpulse-sync` skill 后,屏上出现 AI 提炼的焦点(highlights),不影响 tasks。
3. 多会话切换时屏跟随最近活跃项目;无活动/坏文件不崩;过期标注会话可能已结束;hook 失败不阻塞会话。
4. 全部测试通过。
