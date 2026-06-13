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

## 一键启动（多平台）

仓库提供幂等启动脚本：自动找 Python(≥3.11) → 没 venv 就建 → 没装依赖就 `pip install -e .` → 选配置 → 起服务。venv/依赖已在则秒起。

| 平台 | 脚本 | 用法（在 `software/hub`） |
|---|---|---|
| Linux / macOS / WSL | `run.sh` | `./run.sh` |
| Windows | `run.ps1` | `.\run.ps1`（被拦就 `powershell -ExecutionPolicy Bypass -File .\run.ps1`） |

环境变量 `INKPULSE_PORT` / `INKPULSE_CONFIG` 均生效；后者不设时自动用 `~/inkpulse-config.yaml`（存在才用）。

## 开机自起（systemd user 服务，Linux/WSL）

让 Hub 随系统启动、崩溃自动重启，无需手动开终端。

```bash
mkdir -p ~/.config/systemd/user
cat > ~/.config/systemd/user/inkpulse-hub.service <<'EOF'
[Unit]
Description=InkPulse Hub (e-ink 渲染服务)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=%h/workspace/InkPulse/software/hub
ExecStart=%h/workspace/InkPulse/software/hub/run.sh
Environment=PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
Restart=always
RestartSec=5
# 可选覆盖：
# Environment=INKPULSE_PORT=8080
# Environment=INKPULSE_CONFIG=%h/inkpulse-config.yaml

[Install]
WantedBy=default.target
EOF

loginctl enable-linger "$USER"          # 不登录终端也常驻（WSL 一启动就拉起）
systemctl --user daemon-reload
systemctl --user enable --now inkpulse-hub.service
```

> `WorkingDirectory`/`ExecStart` 按你的仓库实际路径改（上面用 `%h` 代表家目录）。

运维：

```bash
systemctl --user status inkpulse-hub        # 状态
systemctl --user restart inkpulse-hub       # 改代码/布局后重启
journalctl --user -u inkpulse-hub -f        # 实时日志
```

> **WSL 注意**：需 `/etc/wsl.conf` 开 `[boot] systemd=true`；且 WSL 在你首次打开任意终端时才启动（`wsl --shutdown` 后服务也随之停，再次打开终端会自动拉起）。

## 模块结构

```
inkpulse_hub/
├── __main__.py        入口：起 uvicorn，读 INKPULSE_CONFIG / INKPULSE_PORT
├── config.py          Config dataclass + YAML 加载（refresh / sources / layout）
├── server.py          FastAPI 应用与全部 HTTP 端点
├── state.py           HubState：聚合状态/待办/温湿度 + 时钟 + 农历(cnlunar)，供渲染
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
  layouts_store: ~/inkpulse/layouts.json   # 自定义布局存储(网页编辑器写入)
layout:
  # 当前生效布局名(对应 layouts.json 里的 key);内置: dash/photo/usage/todo/clock/split
  name: dash
usage:
  window_token_limit: 2000000   # 5h 窗口 token 上限，进度条按此算占用
  budget_usd: null              # 今日花费预算(USD)，超过则花费数字标红；null=不启用
```

任一采集器失败 → 对应 widget 显示 `n/a`，不拖垮整帧（按 widget 隔离容错）。

## 仪表盘渲染规则

- **头部两行**：第一行完整日期时间 `2026-06-12 11:23 周五`（红色强调）+ 温湿度；第二行**农历**（`cnlunar` 纯算法算出"农历日期 · 生肖年 · 节气"，遇节日自动标红）。
- **红色策略（强调 + 告警，但克制护刷新/防残影）**：固定强调红 = 日期；告警红 = Claude 等输入/出错、窗口占用 >90%、超预算（需配 `budget_usd`）、节日。分区标题栏用黑底白字（结构，不用红），正文/待办/温湿度保持黑色。
- **丰富元素**：黑底白字分区标题栏、放大的花费 hero 数字、状态持续时长（`已 N 分钟`）、今日会话数、窗口占用百分比、真复选框 ☑/☐（完成项删除线）。
- e-ink 约束:只有黑/白/红，全刷约 20s，红刷新更慢/残影更顽固;`engine.py` 关抗锯齿（`fontmode="1"`）保证红字为纯 `(255,0,0)`。
- **布局自定义**:屏幕为 8×6 网格,布局是数据(`layouts.json`)。浏览器开 `/config` 的"布局编辑器"可点格子放 widget、存成命名布局。加新 widget = 在 `render/registry.py` 注册一个绘制函数。

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
