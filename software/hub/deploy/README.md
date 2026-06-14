# 部署:systemd 开机自起

把 InkPulse Hub 注册为 systemd 服务,随 WSL/systemd 启动自动拉起,崩溃自动重启。

> 前提:WSL 已开启 systemd(`/etc/wsl.conf` 含 `[boot]\nsystemd=true`,本机已配)。
> 注意:WSL 下"开机自起"= **WSL 发行版启动时**自动起(打开终端 / `wsl` 命令 / Windows 任务计划拉起 WSL),并非 Windows 登录即起,除非你另行让 WSL 随 Windows 自启。

## 安装(需要 sudo)

```bash
sudo install -m644 /home/zqx/workspace/InkPulse/software/hub/deploy/inkpulse-hub.service \
  /etc/systemd/system/inkpulse-hub.service
sudo systemctl daemon-reload
sudo systemctl enable --now inkpulse-hub
```

## 验证

```bash
systemctl status inkpulse-hub          # active (running) 即成功
curl -s localhost:8080/health          # {"ok":true}
journalctl -u inkpulse-hub -f          # 跟踪日志
```

## 常用操作

```bash
sudo systemctl restart inkpulse-hub    # 改代码后重启
sudo systemctl stop inkpulse-hub       # 临时停(开发时手动 run.sh 前先停, 免端口冲突)
sudo systemctl disable inkpulse-hub    # 取消自起
```

## 自定义

- 换端口/配置:在 `[Service]` 段加 `Environment=INKPULSE_PORT=9000` 或 `Environment=INKPULSE_CONFIG=/home/zqx/my.yaml`,改后 `daemon-reload` + `restart`。
- 首次启动若 `.venv` 不存在,`run.sh` 会自动建 venv 并 `pip install -e .`(需联网,耗时);稳态下已建好则直接起。
