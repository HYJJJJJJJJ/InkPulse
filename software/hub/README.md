# InkPulse Hub

开发机侧服务：采集 Claude 状态/用量、管理待办/照片，把整屏渲染成 **800×480 三色位图**供墨水屏设备拉取。基于 FastAPI + Pillow。

> 设计背景见 [显示系统设计文档](../docs/superpowers/specs/2026-06-09-inkpulse-display-system-design.md)。

## 运行

```bash
cd software/hub
pip install -e ".[dev]"
cp config.example.yaml ~/inkpulse-config.yaml      # 按需修改
INKPULSE_CONFIG=~/inkpulse-config.yaml python -m inkpulse_hub
```

- 监听 `0.0.0.0:8080`（环境变量 `INKPULSE_PORT` 可改）。
- `INKPULSE_CONFIG` 不设时全部用默认值。
- 调布局（无需设备）：浏览器开 `http://<本机IP>:8080/preview.png`
- 待办网页：`http://<本机IP>:8080/todos`（手机连同一局域网也能加）
- 设备取帧：`GET /frame`

## 模块结构

```
inkpulse_hub/
├── __main__.py        入口：起 uvicorn，读 INKPULSE_CONFIG / INKPULSE_PORT
├── config.py          Config dataclass + YAML 加载（refresh / sources / layout）
├── server.py          FastAPI 应用与全部 HTTP 端点
├── state.py           HubState：聚合 Claude 状态 + 待办 + 温湿度，供渲染
├── models.py          数据类：ClaudeStatus / Usage / TodoItem / Photo
├── collectors/        采集器
│   ├── usage.py       解析 ~/.claude/projects/**/*.jsonl → 今日 token/花费/窗口比例
│   ├── todos.py       TodoStore：JSON 文件 CRUD（list/add/toggle/delete）
│   └── photos.py      pick_photo：扫描照片目录选一张
├── render/            渲染
│   ├── engine.py      render_frame：排版 → 量化双 plane → 出 Frame(body/etag/png)
│   ├── widgets.py     draw_header / draw_claude_status / draw_usage / draw_todos
│   ├── planes.py      RGB → 黑/红双 plane 编码（96000B）；ETag 哈希
│   └── dither.py      dither_bwr：照片 Floyd–Steinberg 三色抖动
├── web/todos.html     待办 Web UI（单文件，Fetch API）
└── hooks/             见下「接 Claude Code 状态」
```

**采集模型是推拉混合**：用量/待办/照片是 Hub 主动拉（解析日志/读文件），Claude 状态是 hook 主动 POST 推送。

## HTTP 端点

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/health` | 健康检查 `{"ok": true}` |
| GET | `/frame?t=<温度>&h=<湿度>` | 96000B 双 plane 帧；带 `ETag`/`X-Next-Refresh`；`If-None-Match` 命中返回 304 |
| GET | `/preview.png` | 当前帧渲染成 PNG，电脑上肉眼调布局 |
| GET | `/todos` | 待办 Web UI 页面 |
| GET | `/api/todos` | 待办列表 JSON |
| POST | `/api/todos` | 新增待办，body `{"text": "..."}` |
| POST | `/api/todos/{id}/toggle` | 切换完成状态 |
| DELETE | `/api/todos/{id}` | 删除待办 |
| POST | `/ingest/claude-status` | 接收 hook 上报，body `{"state": "...", "project": "..."}` |

## 配置（config.yaml）

```yaml
refresh:
  min_interval_s: 60       # 最小刷新间隔（防抖）
  periodic_s: 600          # 周期刷新（用量/时钟）
sources:
  claude_logs: ~/.claude/projects     # Claude Code 会话日志目录
  photos_dir: ~/inkpulse/photos        # 照片目录
  todos_store: ~/inkpulse/todos.json   # 待办存储
layout:
  widgets: [header_clock_env, claude_status, usage, todos]
  # 改成 [photo] 即全屏照片布局
```

任一采集器失败 → 对应 widget 显示 `n/a`，不拖垮整帧（按 widget 隔离容错）。

## 接 Claude Code 状态（hooks）

把 `hooks/claude_status.sh` 接到 `~/.claude/settings.json` 的相应 hook，在
SessionStart→`working`、Stop→`done`、Notification→`waiting_for_input` 等时机调用并传入状态名：

```bash
claude_status.sh working        # 状态 ∈ {idle, working, waiting_for_input, done, error}
```

脚本自动取 `basename "$PWD"` 作项目名，POST 到 `$INKPULSE_HUB`（默认 `http://127.0.0.1:8080`），2 秒超时、失败静默（不阻塞 Claude Code）。

## 测试

```bash
pytest -q       # 覆盖 config/state/models/采集器/渲染/HTTP 端点
```

测试覆盖配置加载、采集器解析与容错、双 plane 编码、各 widget 绘制、HTTP 端点契约。
