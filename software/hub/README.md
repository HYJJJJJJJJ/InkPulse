# InkPulse Hub

开发机侧服务：采集 Claude 状态/用量、管理待办/照片，渲染 800×480 三色位图供墨水屏拉取。

## 运行
```bash
conda activate <你的环境>
cd software/hub
pip install -e ".[dev]"
cp config.example.yaml ~/inkpulse-config.yaml   # 按需修改
INKPULSE_CONFIG=~/inkpulse-config.yaml python -m inkpulse_hub
```
- 调布局：浏览器打开 `http://<本机IP>:8080/preview.png`
- 待办：`http://<本机IP>:8080/todos`（手机连同一局域网也能加）
- 设备取帧：`GET /frame`

## 接 Claude Code 状态（hooks）
把 `hooks/claude_status.sh` 接到 `~/.claude/settings.json` 的相应 hook，
在 SessionStart→working、Stop→done、Notification→waiting_for_input 等时机调用并传入状态名。
设 `INKPULSE_HUB` 指向 Hub 地址（默认 `http://127.0.0.1:8080`）。

## 测试
```bash
pytest -q
```
