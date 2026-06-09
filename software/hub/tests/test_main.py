from inkpulse_hub.__main__ import build
from fastapi import FastAPI


def test_build_returns_app(tmp_path, monkeypatch):
    monkeypatch.setenv("INKPULSE_CONFIG", str(tmp_path / "noexist.yaml"))
    app = build()
    assert isinstance(app, FastAPI)
