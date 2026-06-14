# inkpulse_hub/collectors/market.py
import json
import os
import threading
import urllib.request

REFRESH_S = 300   # 行情缓存 5 分钟过期


def is_stale(fetched_at, now) -> bool:
    return (now - fetched_at) >= REFRESH_S


def parse_tencent(line: str):
    """入参: 一行已 GBK 解码的腾讯返回 v_<code>="1~名称~..~现价~..~涨跌幅~..";
    返回归一 quote 或 None(格式异常)。字段: [1]=名称, [3]=现价, [32]=涨跌幅%。"""
    try:
        head, body = line.split("=", 1)
        code = head.strip()
        if code.startswith("v_"):
            code = code[2:]
        body = body.strip().rstrip(";").strip('"')
        f = body.split("~")
        if len(f) < 33:
            return None
        return {"type": "cn", "code": code, "name": f[1],
                "price": float(f[3]), "change_pct": float(f[32])}
    except (ValueError, IndexError):
        return None


def parse_okx(obj: dict, code: str):
    """入参: OKX ticker JSON + 标的代码。返回归一 quote 或 None。"""
    try:
        d = obj["data"][0]
        last = float(d["last"])
        open24h = float(d["open24h"])
        if open24h == 0:
            return None
        return {"type": "crypto", "code": code, "name": code.split("-")[0],
                "price": last, "change_pct": (last - open24h) / open24h * 100}
    except (KeyError, IndexError, ValueError, TypeError):
        return None


TIMEOUT_S = 8
TENCENT = "https://qt.gtimg.cn/q="
OKX = "https://www.okx.com/api/v5/market/ticker?instId="


def _get_bytes(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
        return r.read()


def fetch_cn(codes: list) -> list:
    """批量抓 A股/指数; 返回归一 quote 列表; 单行坏跳过。codes 空 -> []。"""
    if not codes:
        return []
    text = _get_bytes(TENCENT + ",".join(codes)).decode("gbk", "replace")
    out = []
    for line in text.strip().splitlines():
        if "=" not in line:
            continue
        q = parse_tencent(line)
        if q:
            out.append(q)
    return out


def fetch_crypto(code: str):
    """抓单个加密标的(OKX); 返回归一 quote 或 None。"""
    obj = json.loads(_get_bytes(OKX + code).decode("utf-8", "replace"))
    return parse_okx(obj, code)


class MarketService:
    """带缓存的行情服务。current() 只读缓存(渲染用, 不触网);
    maybe_refresh() 过期/标的变更才起后台线程抓取。"""

    def __init__(self, cache_path: str):
        self.cache_path = cache_path
        os.makedirs(os.path.dirname(os.path.abspath(cache_path)), exist_ok=True)
        self._lock = threading.Lock()
        self._refreshing = False

    def _read_cache(self):
        if not os.path.exists(self.cache_path):
            return None
        try:
            with open(self.cache_path, "r", encoding="utf-8") as f:
                d = json.load(f)
            if not isinstance(d, dict) or "quotes" not in d:
                return None
            return d
        except (json.JSONDecodeError, ValueError, OSError):
            return None

    def _write_cache(self, fetched_at, sig, quotes):
        with open(self.cache_path, "w", encoding="utf-8") as f:
            json.dump({"fetched_at": fetched_at, "sig": sig, "quotes": quotes},
                      f, ensure_ascii=False)

    @staticmethod
    def _sig(symbols):
        return [[s.get("type"), s.get("code")] for s in symbols]

    def current(self):
        c = self._read_cache()
        return c["quotes"] if c else []

    def clear(self):
        try:
            os.remove(self.cache_path)
        except OSError:
            pass

    def _needs_refresh(self, symbols, now):
        c = self._read_cache()
        return (c is None or c.get("sig") != self._sig(symbols)
                or is_stale(c["fetched_at"], now))

    def refresh_now(self, symbols, now, fetch_cn=fetch_cn, fetch_crypto=fetch_crypto):
        """同步抓取并写缓存; 单标的失败跳过; 整体抓不到任何数据则保留旧缓存。"""
        cn_codes = [s["code"] for s in symbols if s.get("type") == "cn"]
        cn_map = {}
        if cn_codes:
            try:
                cn_map = {q["code"]: q for q in fetch_cn(cn_codes)}
            except Exception as e:
                print(f"[market] cn fetch failed: {e}")
        quotes = []
        for s in symbols:
            t, code = s.get("type"), s.get("code")
            if t == "cn":
                if code in cn_map:
                    quotes.append(cn_map[code])
            elif t == "crypto":
                try:
                    q = fetch_crypto(code)
                    if q:
                        quotes.append(q)
                except Exception as e:
                    print(f"[market] crypto {code} failed: {e}")
        if quotes or not symbols:        # 全失败(空)且本有标的 -> 不覆盖旧缓存
            self._write_cache(now, self._sig(symbols), quotes)

    def maybe_refresh(self, symbols, now, fetch_cn=fetch_cn, fetch_crypto=fetch_crypto):
        if not self._needs_refresh(symbols, now):
            return
        with self._lock:
            if self._refreshing:
                return
            self._refreshing = True

        def _job():
            try:
                self.refresh_now(symbols, now, fetch_cn, fetch_crypto)
            finally:
                with self._lock:
                    self._refreshing = False

        threading.Thread(target=_job, daemon=True).start()
