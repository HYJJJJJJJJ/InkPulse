#!/usr/bin/env python3
"""真机验证服务 —— 把某个候选帧按设备 /frame 契约喂给真机。

设备固件里 HUB_FRAME_URL = http://<你的IP>:8080/frame。验证步骤:
  1. 先停掉正在跑的真 Hub(它占着 8080)。
  2. 在同一台机器(设备指向的那台)上跑本脚本:
        python serve_candidate.py A      # 或 C / D
  3. 设备会在下一次轮询(X-Next-Refresh=60s)拉到该候选并刷屏。
     想看下一个候选: Ctrl-C 后换参数再跑(etag 变了, 设备会刷新)。

契约对齐 inkpulse_hub/server.py:
  GET /frame  -> 200, body=96000B(黑plane+红plane), 头含 ETag 与 X-Next-Refresh
                 If-None-Match 命中则 304(设备不刷屏)
  GET /health -> {"ok": true}
  GET /preview.png -> 该候选 png(浏览器里看)
"""
import argparse
import hashlib
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

OUT = os.path.join(os.path.dirname(__file__), "out")
CANDIDATES = {
    "A": "candidate_A_arkpixel12",
    "C": "candidate_C_arkpixel24",
    "D": "candidate_D_superbold",
}
REFRESH_S = 60  # 调短便于切换候选时快速看到效果


def load(cid: str):
    base = os.path.join(OUT, CANDIDATES[cid])
    body = open(base + ".bin", "rb").read()
    png = open(base + ".png", "rb").read()
    etag = '"' + hashlib.sha1(body).hexdigest() + '"'
    return body, png, etag


def make_handler(body, png, etag):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):  # 静默默认日志, 自己打有用的
            pass

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path == "/health":
                self._send(200, b'{"ok": true}', "application/json")
            elif path == "/preview.png":
                self._send(200, png, "image/png")
            elif path == "/frame":
                if self.headers.get("If-None-Match") == etag:
                    print("  -> 304 (设备已是最新, 不刷屏)")
                    self.send_response(304)
                    self.end_headers()
                    return
                print(f"  -> 200 下发 {len(body)}B  etag={etag}")
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("ETag", etag)
                self.send_header("X-Next-Refresh", str(REFRESH_S))
                self.end_headers()
                self.wfile.write(body)
            else:
                self._send(404, b"not found", "text/plain")

        def _send(self, code, data, ctype):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    return H


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("candidate", choices=list(CANDIDATES), help="A / C / D")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8080)
    args = ap.parse_args()

    body, png, etag = load(args.candidate)
    srv = HTTPServer((args.host, args.port), make_handler(body, png, etag))
    print(f"候选 {args.candidate} ({CANDIDATES[args.candidate]}) 已就绪")
    print(f"监听 http://{args.host}:{args.port}/frame  (设备应指向此地址)")
    print(f"浏览器预览: http://localhost:{args.port}/preview.png")
    print("等设备轮询拉帧... (Ctrl-C 退出, 换 A/C/D 再跑切换候选)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已退出")


if __name__ == "__main__":
    main()
