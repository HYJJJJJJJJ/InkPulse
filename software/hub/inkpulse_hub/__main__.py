# inkpulse_hub/__main__.py
import os
from .config import load_config, load_runtime
from .server import create_app


def build():
    cfg = load_config(os.environ.get("INKPULSE_CONFIG"))
    load_runtime(cfg, cfg.runtime_store)   # web 配置面板存的运行时设置
    return create_app(cfg)


def main():
    import uvicorn
    import logging
    from .discovery import register_mdns

    port = int(os.environ.get("INKPULSE_PORT", "8080"))
    app = build()

    reg = None
    try:
        reg = register_mdns(port)  # 让设备开机自动发现, 无需写死 IP
    except Exception as e:  # mDNS 失败不应阻止 hub 启动(设备可降级到 NVS/默认地址)
        logging.getLogger("inkpulse").warning("mDNS 注册失败, 跳过: %s", e)

    try:
        uvicorn.run(app, host="0.0.0.0", port=port)
    finally:
        if reg is not None:
            reg.close()


if __name__ == "__main__":
    main()
