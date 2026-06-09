# inkpulse_hub/__main__.py
import os
from .config import load_config
from .server import create_app


def build():
    cfg = load_config(os.environ.get("INKPULSE_CONFIG"))
    return create_app(cfg)


def main():
    import uvicorn
    uvicorn.run(build(), host="0.0.0.0", port=int(os.environ.get("INKPULSE_PORT", "8080")))


if __name__ == "__main__":
    main()
