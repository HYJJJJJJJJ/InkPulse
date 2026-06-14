# 行情 widget 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 屏上显示一组自选标的(A股/指数 + 加密)的现价与涨跌幅(涨红跌黑);标的网页管理;数据走腾讯(A股,GBK)+ OKX(加密,JSON),后台抓取+缓存,渲染不阻塞。

**Architecture:** 复用天气的联网范式。新增 `collectors/market.py`:纯解析(`parse_tencent`/`parse_okx`/`is_stale`)+ 薄网络层(`_get_bytes`/`fetch_cn`/`fetch_crypto`)+ `MarketService`(缓存 + stale-while-revalidate 后台线程,单标的失败跳过、整源失败保留旧缓存)。state 注入 `market`;`draw_market` 纯绘制;`/api/market*` + `/config` 行情卡片。

**Tech Stack:** Python 3.11 · Pillow · FastAPI · pytest · 标准库 `urllib`/`json`/`threading`/`bytes.decode("gbk")`(无新依赖)。

设计来源:`docs/superpowers/specs/2026-06-14-inkpulse-market-design.md`。所有路径相对 `software/hub/`。

---

## 关键约定(全任务通用,先读)

- **测试命令**:`.venv/bin/python -m pytest`(系统 python3 是 3.10 缺 cnlunar;venv 是 3.11)。
- **已知预存失败**:`tests/test_discovery.py::test_register_mdns_is_discoverable_then_unregistered`(WSL2 mDNS/网络),忽略;除它之外必须全绿。
- **绝不真连网络**:所有测试 mock `_get_bytes` / 注入假 `fetch_cn`/`fetch_crypto` / 用新鲜缓存。涉及标的的 state/api 测试不得触发后台线程真连。
- **实测字段**(贯穿):腾讯一行 `v_sh000001="1~上证指数~000001~4031.51~3987.01~..~涨跌幅~..";`,GBK 解码后按 `~` 拆:**[1]=名称、[3]=现价、[32]=涨跌幅%**(共 88 字段)。OKX:`data[0].last`=现价、`data[0].open24h`=24h 开盘。
- **归一 quote**:`{"type":"cn"|"crypto","code":str,"name":str,"price":float,"change_pct":float}`。
- 每个任务结束 `commit`,运行目录 `software/hub/`。

---

## 文件结构

| 文件 | 动作 | 职责 |
|---|---|---|
| `inkpulse_hub/collectors/market.py` | 新增 | 常量 + parse + 网络层 + `MarketService` |
| `inkpulse_hub/config.py` | 改 | `market_cache` 字段 + `market_symbols` 进 RUNTIME_FIELDS |
| `inkpulse_hub/state.py` | 改 | `HubState` 持 `MarketService`;注入 `market` + 非阻塞刷新 |
| `inkpulse_hub/render/widgets.py` | 改 | 新增 `draw_market` |
| `inkpulse_hub/render/registry.py` | 改 | 注册 `market` |
| `inkpulse_hub/server.py` | 改 | `/api/market*` 端点 |
| `inkpulse_hub/web/config.html` | 改 | 行情卡片 |
| `tests/test_market_parse.py` / `test_market_net.py` / `test_market_service.py` / `test_widget_market.py` / `test_market_api.py` | 新增 | 各层测试 |
| `tests/test_config.py` / `test_state_phase2.py` / `test_registry.py` | 改 | 追加断言 |

---

## Task 1: market.py —— 常量 + parse_tencent/parse_okx + is_stale(纯)

**Files:**
- Create: `inkpulse_hub/collectors/market.py`
- Test: `tests/test_market_parse.py`

- [ ] **Step 1: 写失败测试**

`tests/test_market_parse.py`:

```python
from inkpulse_hub.collectors.market import parse_tencent, parse_okx, is_stale, REFRESH_S

# 一行腾讯返回(已 GBK 解码的字符串形态)
TENCENT_LINE = ('v_sh000001="1~上证指数~000001~4031.51~3987.01~4017.86~743131092'
                + "~0" * 25 + '~44.50~1.12' + "~x" * 53 + '";')


def test_parse_tencent_basic():
    q = parse_tencent(TENCENT_LINE)
    assert q["type"] == "cn" and q["code"] == "sh000001"
    assert q["name"] == "上证指数" and q["price"] == 4031.51 and q["change_pct"] == 1.12


def test_parse_tencent_malformed_returns_none():
    assert parse_tencent('v_x="1~只有~几个~字段";') is None
    assert parse_tencent("garbage no equals") is None


def test_parse_okx_basic():
    obj = {"data": [{"last": "64544.6", "open24h": "63879.2"}]}
    q = parse_okx(obj, "BTC-USDT")
    assert q["type"] == "crypto" and q["code"] == "BTC-USDT" and q["name"] == "BTC"
    assert q["price"] == 64544.6
    assert abs(q["change_pct"] - (64544.6 - 63879.2) / 63879.2 * 100) < 1e-6


def test_parse_okx_malformed_returns_none():
    assert parse_okx({"data": []}, "BTC-USDT") is None
    assert parse_okx({}, "BTC-USDT") is None
    assert parse_okx({"data": [{"last": "1", "open24h": "0"}]}, "X") is None   # 除零


def test_is_stale_boundary():
    assert is_stale(1000.0, 1000.0 + REFRESH_S) is True
    assert is_stale(1000.0, 1000.0 + REFRESH_S - 1) is False
```

注:`TENCENT_LINE` 用拼接保证字段 [3]=现价、[32]=涨跌幅 落位正确(前缀 7 段 + 25 个"0" = 到 index 31 是"44.50"前;`~44.50~1.12` 使 [31]=44.50、[32]=1.12)。

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest tests/test_market_parse.py -v`
Expected: FAIL —— `ModuleNotFoundError: No module named 'inkpulse_hub.collectors.market'`

- [ ] **Step 3: 写实现**

`inkpulse_hub/collectors/market.py`(本任务仅纯逻辑部分):

```python
# inkpulse_hub/collectors/market.py
REFRESH_S = 300   # 行情缓存 5 分钟过期


def is_stale(fetched_at, now) -> bool:
    return (now - fetched_at) >= REFRESH_S


def parse_tencent(line: str):
    """入参: 一行已 GBK 解码的腾讯返回 v_<code>="1~名称~..~现价~..~涨跌幅~..";
    返回归一 quote 或 None(格式异常)。"""
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
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/python -m pytest tests/test_market_parse.py -v`
Expected: PASS(5 passed)

- [ ] **Step 5: 提交**

```bash
git add inkpulse_hub/collectors/market.py tests/test_market_parse.py
git commit -m "feat(market): parse_tencent/parse_okx + is_stale(纯逻辑)"
```

---

## Task 2: market.py —— 网络层 fetch_cn/fetch_crypto(mock 测)

**Files:**
- Modify: `inkpulse_hub/collectors/market.py`
- Test: `tests/test_market_net.py`

- [ ] **Step 1: 写失败测试**

`tests/test_market_net.py`:

```python
import inkpulse_hub.collectors.market as M

TENCENT_LINE = ('v_sh000001="1~上证指数~000001~4031.51~3987.01~4017.86~743131092'
                + "~0" * 25 + '~44.50~1.12' + "~x" * 53 + '";')


def test_fetch_cn_batch_parses(monkeypatch):
    captured = {}
    def fake(url):
        captured["url"] = url
        # 两行(第二行故意坏 -> 跳过)
        return (TENCENT_LINE + "\n" + 'v_bad="1~少~字段";').encode("gbk")
    monkeypatch.setattr(M, "_get_bytes", fake)
    out = M.fetch_cn(["sh000001", "bad"])
    assert "q=sh000001,bad" in captured["url"]
    assert [q["code"] for q in out] == ["sh000001"]     # 坏行被跳过


def test_fetch_cn_empty_codes(monkeypatch):
    monkeypatch.setattr(M, "_get_bytes", lambda url: (_ for _ in ()).throw(AssertionError("不应请求")))
    assert M.fetch_cn([]) == []


def test_fetch_crypto_parses(monkeypatch):
    import json
    monkeypatch.setattr(M, "_get_bytes",
        lambda url: json.dumps({"data": [{"last": "1672.7", "open24h": "1674.46"}]}).encode("utf-8"))
    q = M.fetch_crypto("ETH-USDT")
    assert q["type"] == "crypto" and q["name"] == "ETH" and q["price"] == 1672.7
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest tests/test_market_net.py -v`
Expected: FAIL —— `AttributeError: module ... has no attribute '_get_bytes'`

- [ ] **Step 3: 写实现**

在 `inkpulse_hub/collectors/market.py` 顶部 import 区加:
```python
import json
import urllib.request
```
追加(在 `parse_okx` 之后):
```python
TIMEOUT_S = 8
TENCENT = "https://qt.gtimg.cn/q="
OKX = "https://www.okx.com/api/v5/market/ticker?instId="


def _get_bytes(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=TIMEOUT_S) as r:
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
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/python -m pytest tests/test_market_net.py -v`
Expected: PASS(3 passed)

- [ ] **Step 5: 提交**

```bash
git add inkpulse_hub/collectors/market.py tests/test_market_net.py
git commit -m "feat(market): fetch_cn(腾讯GBK批量)/fetch_crypto(OKX) 网络层"
```

---

## Task 3: market.py —— MarketService(缓存 + SWR)

**Files:**
- Modify: `inkpulse_hub/collectors/market.py`
- Test: `tests/test_market_service.py`

- [ ] **Step 1: 写失败测试**

`tests/test_market_service.py`:

```python
from inkpulse_hub.collectors.market import MarketService, REFRESH_S

NOW = 1749880000.0
SYMS = [{"type": "cn", "code": "sh000001"}, {"type": "crypto", "code": "BTC-USDT"}]


def _fake_cn(codes):
    return [{"type": "cn", "code": c, "name": c, "price": 1.0, "change_pct": 1.0} for c in codes]


def _fake_crypto(code):
    return {"type": "crypto", "code": code, "name": code.split("-")[0], "price": 2.0, "change_pct": -1.0}


def _svc(tmp_path):
    return MarketService(str(tmp_path / "m.json"))


def test_current_empty_when_no_cache(tmp_path):
    assert _svc(tmp_path).current() == []


def test_refresh_now_writes_and_current_reads(tmp_path):
    s = _svc(tmp_path)
    s.refresh_now(SYMS, NOW, fetch_cn=_fake_cn, fetch_crypto=_fake_crypto)
    q = s.current()
    assert [x["code"] for x in q] == ["sh000001", "BTC-USDT"]   # 保持 symbols 顺序


def test_needs_refresh_logic(tmp_path):
    s = _svc(tmp_path)
    assert s._needs_refresh(SYMS, NOW) is True                          # 无缓存
    s.refresh_now(SYMS, NOW, fetch_cn=_fake_cn, fetch_crypto=_fake_crypto)
    assert s._needs_refresh(SYMS, NOW + 10) is False                    # 新鲜
    assert s._needs_refresh(SYMS, NOW + REFRESH_S + 1) is True          # 过期
    assert s._needs_refresh(SYMS + [{"type": "cn", "code": "sz000002"}], NOW + 10) is True  # 标的变更


def test_single_symbol_failure_skipped(tmp_path):
    s = _svc(tmp_path)
    def boom_crypto(code):
        raise RuntimeError("okx down")
    s.refresh_now(SYMS, NOW, fetch_cn=_fake_cn, fetch_crypto=boom_crypto)
    assert [x["code"] for x in s.current()] == ["sh000001"]   # 加密失败跳过, A股仍在


def test_total_failure_keeps_old_cache(tmp_path):
    s = _svc(tmp_path)
    s.refresh_now(SYMS, NOW, fetch_cn=_fake_cn, fetch_crypto=_fake_crypto)   # 先有好缓存
    def boom_cn(codes):
        raise RuntimeError("tencent down")
    def boom_crypto(code):
        raise RuntimeError("okx down")
    s.refresh_now(SYMS, NOW + 5, fetch_cn=boom_cn, fetch_crypto=boom_crypto)  # 全失败
    assert len(s.current()) == 2   # 旧缓存保留(没被空覆盖)


def test_clear(tmp_path):
    s = _svc(tmp_path)
    s.refresh_now(SYMS, NOW, fetch_cn=_fake_cn, fetch_crypto=_fake_crypto)
    s.clear()
    assert s.current() == []


def test_maybe_refresh_noop_when_fresh(tmp_path):
    s = _svc(tmp_path)
    s.refresh_now(SYMS, NOW, fetch_cn=_fake_cn, fetch_crypto=_fake_crypto)
    def boom(*a):
        raise AssertionError("不应刷新")
    s.maybe_refresh(SYMS, NOW + 10, fetch_cn=boom, fetch_crypto=boom)
    assert len(s.current()) == 2
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest tests/test_market_service.py -v`
Expected: FAIL —— `ImportError: cannot import name 'MarketService'`

- [ ] **Step 3: 写实现**

在 `inkpulse_hub/collectors/market.py` 顶部 import 区加:
```python
import os
import threading
```
文件末尾追加:
```python
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
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/python -m pytest tests/test_market_service.py -v`
Expected: PASS(7 passed)

- [ ] **Step 5: 提交**

```bash
git add inkpulse_hub/collectors/market.py tests/test_market_service.py
git commit -m "feat(market): MarketService 缓存 + SWR(单标的失败跳过/整源失败留旧缓存)"
```

---

## Task 4: config.py —— market_cache 字段 + market_symbols 进 RUNTIME

**Files:**
- Modify: `inkpulse_hub/config.py`
- Test: `tests/test_config.py`(追加)

- [ ] **Step 1: 追加失败测试**

在 `tests/test_config.py` 末尾追加:

```python
def test_market_config_fields(tmp_path):
    from inkpulse_hub.config import Config, load_config, RUNTIME_FIELDS, save_runtime, load_runtime
    c = Config()
    assert c.market_cache.endswith("inkpulse/market_cache.json")
    assert c.market_symbols == []
    assert "market_symbols" in RUNTIME_FIELDS
    p = tmp_path / "c.yaml"
    p.write_text("sources:\n  market_cache: /tmp/m.json\n", encoding="utf-8")
    assert load_config(str(p)).market_cache == "/tmp/m.json"
    # runtime 往返 market_symbols
    c.market_symbols = [{"type": "cn", "code": "sh000001"}]
    rt = tmp_path / "rt.json"
    save_runtime(c, str(rt))
    c2 = Config()
    load_runtime(c2, str(rt))
    assert c2.market_symbols == [{"type": "cn", "code": "sh000001"}]
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest tests/test_config.py::test_market_config_fields -v`
Expected: FAIL —— `AttributeError: 'Config' object has no attribute 'market_cache'`

- [ ] **Step 3: 实现**

`inkpulse_hub/config.py`:

1. 在 `Config` 数据类里、`events_store` 字段下一行加:
```python
    market_cache: str = os.path.expanduser("~/inkpulse/market_cache.json")
    market_symbols: list = field(default_factory=list)
```
(`field` 已在 config.py 顶部 `from dataclasses import dataclass, field` 导入——确认;`layout` 字段已用 `field(default_factory=...)`。)

2. 在 `load_config` 内、`cfg.events_store = ...` 那行下一行加:
```python
    cfg.market_cache = os.path.expanduser(sources.get("market_cache", cfg.market_cache))
```

3. `RUNTIME_FIELDS` 列表追加 `"market_symbols"`:
```python
RUNTIME_FIELDS = [
    "layout_name", "usage_budget_usd", "usage_window_token_limit", "refresh_periodic_s",
    "photo_pinned",
    "weather_lat", "weather_lon", "weather_place",
    "market_symbols",
]
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/python -m pytest tests/test_config.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add inkpulse_hub/config.py tests/test_config.py
git commit -m "feat(config): market_cache 字段 + market_symbols 进 RUNTIME_FIELDS"
```

---

## Task 5: state.py —— 注入 market

**Files:**
- Modify: `inkpulse_hub/state.py`
- Test: `tests/test_state_phase2.py`(追加)

- [ ] **Step 1: 追加失败测试**

在 `tests/test_state_phase2.py` 末尾追加:

```python
def test_render_state_market_empty_without_symbols(tmp_path):
    cfg = Config()
    cfg.claude_logs = str(tmp_path / "logs")
    cfg.todos_store = str(tmp_path / "todos.json")
    cfg.photos_dir = str(tmp_path / "photos")
    cfg.habits_store = str(tmp_path / "habits.json")
    cfg.env_history_store = str(tmp_path / "env.json")
    cfg.weather_cache = str(tmp_path / "w.json")
    cfg.events_store = str(tmp_path / "events.json")
    cfg.market_cache = str(tmp_path / "m.json")
    st = HubState(cfg)
    state = st.build_render_state(now=1718000000.0)
    assert state["market"] == []


def test_render_state_market_from_fresh_cache(tmp_path):
    import json
    now = 1718000000.0
    quotes = [{"type": "cn", "code": "sh000001", "name": "上证指数", "price": 4031.51, "change_pct": 1.12}]
    mpath = tmp_path / "m.json"
    sig = [["cn", "sh000001"]]
    mpath.write_text(json.dumps({"fetched_at": now, "sig": sig, "quotes": quotes}), encoding="utf-8")
    cfg = Config()
    cfg.claude_logs = str(tmp_path / "logs")
    cfg.todos_store = str(tmp_path / "todos.json")
    cfg.photos_dir = str(tmp_path / "photos")
    cfg.habits_store = str(tmp_path / "habits.json")
    cfg.env_history_store = str(tmp_path / "env.json")
    cfg.weather_cache = str(tmp_path / "w.json")
    cfg.events_store = str(tmp_path / "events.json")
    cfg.market_cache = str(mpath)
    cfg.market_symbols = [{"type": "cn", "code": "sh000001"}]   # 与缓存 sig 一致 -> 不触发刷新线程
    st = HubState(cfg)
    state = st.build_render_state(now=now)
    assert [q["code"] for q in state["market"]] == ["sh000001"]
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest tests/test_state_phase2.py::test_render_state_market_empty_without_symbols -v`
Expected: FAIL —— `KeyError: 'market'`

- [ ] **Step 3: 实现**

`inkpulse_hub/state.py`:

1. import 区,在 `from .collectors.events import EventStore, AGENDA_LIMIT` 下一行加:
```python
from .collectors.market import MarketService
```

2. `HubState.__init__`,在 `self.events = EventStore(cfg.events_store)` 下一行加:
```python
        self.market = MarketService(cfg.market_cache)
```

3. `build_render_state` 内,`now = now if now is not None else time.time()` 之后加:
```python
        syms = self.cfg.market_symbols or []
        if syms:
            self.market.maybe_refresh(syms, now)
            market = self.market.current()
        else:
            market = []
```

4. 返回 dict 里加一个键(放在 `"events": ...,` 之后):
```python
            "market": market,
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/python -m pytest tests/test_state_phase2.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add inkpulse_hub/state.py tests/test_state_phase2.py
git commit -m "feat(state): 注入 market + 非阻塞 maybe_refresh"
```

---

## Task 6: draw_market widget

**Files:**
- Modify: `inkpulse_hub/render/widgets.py`(末尾新增)
- Test: `tests/test_widget_market.py`

- [ ] **Step 1: 写失败测试**

`tests/test_widget_market.py`:

```python
from PIL import Image, ImageDraw
from inkpulse_hub.render.widgets import draw_market, Zone


def _img(w=400, h=240):
    img = Image.new("RGB", (w, h), (255, 255, 255))
    d = ImageDraw.Draw(img)
    d.fontmode = "1"
    return img, d


def _has(img, color):
    return any(img.getpixel((x, y)) == color
              for x in range(img.width) for y in range(img.height))


def _q(name, price, pct, t="cn", code="x"):
    return {"type": t, "code": code, "name": name, "price": price, "change_pct": pct}


def test_up_is_red_down_is_black():
    img, d = _img()
    draw_market(d, Zone(0, 0, 400, 240),
                [_q("上证指数", 4031.51, 1.12), _q("某跌票", 10.0, -2.0)])
    assert _has(img, (0, 0, 0)) and _has(img, (255, 0, 0))   # 有黑(名/价/跌) + 有红(涨)


def test_all_down_no_red():
    img, d = _img()
    draw_market(d, Zone(0, 0, 400, 240), [_q("跌一", 10.0, -1.0), _q("跌二", 5.0, -0.5)])
    assert _has(img, (0, 0, 0)) and not _has(img, (255, 0, 0))


def test_empty_shows_hint_no_crash():
    img, d = _img()
    draw_market(d, Zone(0, 0, 400, 240), [])
    assert _has(img, (0, 0, 0))


def test_long_name_truncated_no_crash():
    img, d = _img(280, 100)
    draw_market(d, Zone(0, 0, 280, 100), [_q("超长名称" * 8, 1.0, 0.0)])
    assert _has(img, (0, 0, 0))
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest tests/test_widget_market.py -v`
Expected: FAIL —— `ImportError: cannot import name 'draw_market'`

- [ ] **Step 3: 写实现**

在 `inkpulse_hub/render/widgets.py` 末尾追加(复用 `_title_bar`/`_center_text`/`_font`/`Zone`/`BLACK`/`RED`):

```python
def draw_market(d: ImageDraw.ImageDraw, z: Zone, quotes) -> None:
    """自选行情列表。quotes=[{name,price,change_pct,...}]; 涨=红 跌/平=黑, 名称/现价恒黑。"""
    cy = _title_bar(d, z, "行情")
    if not quotes:
        _center_text(d, z, "无标的 · 去网页添加", _font(18), BLACK)
        return
    f = _font(18)
    row_h = 30
    max_rows = max(1, (z.y + z.h - cy - 4) // row_h)
    name_w = z.w * 0.42
    price_x = z.x + int(z.w * 0.44)
    for i, q in enumerate(quotes[:max_rows]):
        y = cy + i * row_h
        name = q.get("name", "")
        while name and d.textlength(name, font=f) > name_w:
            name = name[:-1]
        d.text((z.x + 6, y), name, fill=BLACK, font=f)
        d.text((price_x, y), f"{q.get('price', 0):.2f}", fill=BLACK, font=f)
        pct = q.get("change_pct", 0.0)
        s = f"{pct:+.2f}%"
        col = RED if pct > 0 else BLACK
        pw = d.textlength(s, font=f)
        d.text((z.x + z.w - pw - 6, y), s, fill=col, font=f)
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/python -m pytest tests/test_widget_market.py -v`
Expected: PASS(4 passed)

- [ ] **Step 5: 提交**

```bash
git add inkpulse_hub/render/widgets.py tests/test_widget_market.py
git commit -m "feat(widget): draw_market 行情列表(涨红跌黑/截断)"
```

---

## Task 7: registry —— 注册 market widget

**Files:**
- Modify: `inkpulse_hub/render/registry.py`
- Test: `tests/test_registry.py`(`_state()` 补字段 + 断言)

- [ ] **Step 1: 改测试(先让其失败)**

`tests/test_registry.py` 的 `_state()` 返回 dict 内追加一键:

```python
        "market": [{"type": "cn", "code": "sh000001", "name": "上证指数",
                    "price": 4031.51, "change_pct": 1.12}],
```

把 `test_existing_widgets_registered` 的 `expected` 集合加入 `"market"`:

```python
    expected = {"header", "claude_status", "usage", "usage_ring",
                "todos", "big_clock", "calendar", "photo",
                "usage_trend", "project_dist", "habits", "temp_trend", "weather",
                "agenda", "market"}
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest tests/test_registry.py -v`
Expected: FAIL —— `market` 不在 REGISTRY

- [ ] **Step 3: 实现**

`inkpulse_hub/render/registry.py`:

1. 在 `_agenda` 适配器之后加:
```python
def _market(d, img, z, state, cfg, p):
    W.draw_market(d, z, state.get("market", []))
```

2. `REGISTRY` 字典里(`"agenda": ...` 之后)加一条:
```python
    "market":        WidgetSpec("market", "行情", _market, {"cols": 4, "rows": 3}),
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/python -m pytest tests/test_registry.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add inkpulse_hub/render/registry.py tests/test_registry.py
git commit -m "feat(registry): 注册 market widget 与适配器"
```

---

## Task 8: server —— /api/market* 端点

**Files:**
- Modify: `inkpulse_hub/server.py`
- Test: `tests/test_market_api.py`

- [ ] **Step 1: 写失败测试**

`tests/test_market_api.py`:

```python
from fastapi.testclient import TestClient
from inkpulse_hub.server import create_app
from inkpulse_hub.config import Config


def _app(tmp_path):
    cfg = Config(claude_logs=str(tmp_path / "l"),
                 photos_dir=str(tmp_path / "p"),
                 todos_store=str(tmp_path / "todos.json"),
                 market_cache=str(tmp_path / "m.json"),
                 runtime_store=str(tmp_path / "rt.json"))
    return create_app(cfg)


def test_get_market_empty(tmp_path):
    r = TestClient(_app(tmp_path)).get("/api/market").json()
    assert r["symbols"] == [] and r["quotes"] == []


def test_add_symbol_and_list(tmp_path):
    app = _app(tmp_path)
    c = TestClient(app)
    assert c.post("/api/market/symbols", json={"type": "cn", "code": "SH000001"}).status_code == 200
    syms = c.get("/api/market/symbols").json()
    assert syms == [{"type": "cn", "code": "sh000001"}]          # cn 规范化小写
    assert app.state.cfg.market_symbols == [{"type": "cn", "code": "sh000001"}]


def test_add_crypto_uppercased(tmp_path):
    c = TestClient(_app(tmp_path))
    c.post("/api/market/symbols", json={"type": "crypto", "code": "btc-usdt"})
    assert c.get("/api/market/symbols").json() == [{"type": "crypto", "code": "BTC-USDT"}]


def test_add_rejects_bad_type(tmp_path):
    assert TestClient(_app(tmp_path)).post("/api/market/symbols",
        json={"type": "fund", "code": "x"}).status_code == 400


def test_add_rejects_blank_code(tmp_path):
    assert TestClient(_app(tmp_path)).post("/api/market/symbols",
        json={"type": "cn", "code": "  "}).status_code == 400


def test_add_duplicate_ignored(tmp_path):
    c = TestClient(_app(tmp_path))
    c.post("/api/market/symbols", json={"type": "cn", "code": "sh000001"})
    c.post("/api/market/symbols", json={"type": "cn", "code": "sh000001"})
    assert len(c.get("/api/market/symbols").json()) == 1


def test_delete_symbol(tmp_path):
    c = TestClient(_app(tmp_path))
    c.post("/api/market/symbols", json={"type": "cn", "code": "sh000001"})
    assert c.request("DELETE", "/api/market/symbols",
                     json={"type": "cn", "code": "sh000001"}).status_code == 200
    assert c.get("/api/market/symbols").json() == []
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest tests/test_market_api.py -v`
Expected: FAIL —— GET `/api/market` 返回 404

- [ ] **Step 3: 实现**

`inkpulse_hub/server.py`:在 events 端点之后、`# ---- 配置中心` 之前插入(`Request`/`JSONResponse`/`save_runtime` 已导入,复用):

```python
    def _norm_symbol(data):
        t = data.get("type")
        code = (data.get("code") or "").strip()
        if t not in ("cn", "crypto") or not code:
            return None
        code = code.lower() if t == "cn" else code.upper()
        return {"type": t, "code": code}

    @app.get("/api/market")
    def api_market_get():
        return {"symbols": cfg.market_symbols, "quotes": state.market.current()}

    @app.get("/api/market/symbols")
    def api_market_symbols():
        return cfg.market_symbols

    @app.post("/api/market/symbols")
    async def api_market_add(request: Request):
        sym = _norm_symbol(await request.json())
        if sym is None:
            return JSONResponse({"error": "invalid symbol"}, status_code=400)
        if sym not in cfg.market_symbols:
            cfg.market_symbols = cfg.market_symbols + [sym]
            save_runtime(cfg, cfg.runtime_store)
            state.market.clear()
        return {"ok": True}

    @app.delete("/api/market/symbols")
    async def api_market_del(request: Request):
        sym = _norm_symbol(await request.json())
        if sym is None:
            return JSONResponse({"error": "invalid symbol"}, status_code=400)
        cfg.market_symbols = [s for s in cfg.market_symbols if s != sym]
        save_runtime(cfg, cfg.runtime_store)
        state.market.clear()
        return {"ok": True}
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/python -m pytest tests/test_market_api.py -v`
Expected: PASS(7 passed)

- [ ] **Step 5: 提交**

```bash
git add inkpulse_hub/server.py tests/test_market_api.py
git commit -m "feat(api): /api/market 当前行情 + 标的增删(规范化/去重/校验)"
```

---

## Task 9: config.html —— 行情卡片

**Files:**
- Modify: `inkpulse_hub/web/config.html`
- 手动验证(纯前端,无单测)

- [ ] **Step 1: 加卡片**

在日程卡片之后、`#wrap` 收尾 `</div>`(`<script>` 之前)插入:

```html
  <div class="card">
    <h2>行情</h2>
    <div id="market"></div>
    <div class="row" style="margin-top:12px">
      <select id="mkType"><option value="cn">A股/指数</option><option value="crypto">加密</option></select>
      <input id="mkCode" placeholder="代码:sh000001 / sh600519 / BTC-USDT" style="flex:1">
      <button onclick="addMarket()">添加</button>
    </div>
  </div>
```

- [ ] **Step 2: load() 里挂载**

在 `load()` 函数体末尾(现有 `loadEvents();` 那行)下一行加:
```javascript
  loadMarket();
```

- [ ] **Step 3: 加 JS 函数**

在 `<script>` 块末尾(`</script>` 之前)加:

```javascript
const MKT_LABEL={cn:'A股/指数',crypto:'加密'};
async function loadMarket(){
  const list=await (await fetch('/api/market/symbols')).json();
  const box=document.getElementById('market');box.innerHTML='';
  if(!list.length){box.innerHTML='<div class="hint">还没有标的</div>';return;}
  list.forEach(s=>box.insertAdjacentHTML('beforeend',
    `<div class="row"><span style="flex:1">${MKT_LABEL[s.type]||s.type} · ${esc(s.code)}</span><button class="ghost" onclick="delMarket('${s.type}','${esc(s.code)}')">×</button></div>`));
}
async function addMarket(){
  const type=document.getElementById('mkType').value, ci=document.getElementById('mkCode');
  const code=ci.value.trim();if(!code){alert('请填代码');return;}
  const r=await fetch('/api/market/symbols',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({type,code})});
  if(!r.ok){alert('添加失败(检查类型/代码)');return;}
  ci.value='';loadMarket();setTimeout(refreshPreview,300);
}
async function delMarket(type,code){
  await fetch('/api/market/symbols',{method:'DELETE',headers:{'Content-Type':'application/json'},body:JSON.stringify({type,code})});
  loadMarket();setTimeout(refreshPreview,300);
}
```

- [ ] **Step 4: 手动验证**

```bash
# 用 venv python 起临时实例(参考 tests/test_market_api.py 的 create_app), 浏览器开 /config
```
检查:
1. 「行情」卡片出现,显示"还没有标的"。
2. 选类型 + 填代码(如 cn `sh000001`)→ 添加 → 列表出现该条,预览刷新。
3. `×` 删除。

- [ ] **Step 5: 提交**

```bash
git add inkpulse_hub/web/config.html
git commit -m "feat(web): /config 行情卡片(类型+代码 增删)"
```

---

## Task 10: 全量验证 + 预览 + spec 验收

**Files:** 无改动(纯验证)

- [ ] **Step 1: 跑全部测试**

Run: `.venv/bin/python -m pytest -q`
Expected: 全绿,唯一允许失败是预存的 `tests/test_discovery.py::test_register_mdns_is_discoverable_then_unregistered`。确认运行数秒内完成(无真连网络)。

- [ ] **Step 2: 渲染 market 预览**

```bash
.venv/bin/python -c "
from PIL import Image, ImageDraw
from inkpulse_hub.render.widgets import draw_market, Zone
q=[{'type':'cn','code':'sh000001','name':'上证指数','price':4031.51,'change_pct':1.12},
   {'type':'cn','code':'sh600519','name':'贵州茅台','price':1680.0,'change_pct':-0.45},
   {'type':'crypto','code':'BTC-USDT','name':'BTC','price':64544.6,'change_pct':1.04}]
img=Image.new('RGB',(360,200),(255,255,255)); d=ImageDraw.Draw(img); d.fontmode='1'
draw_market(d, Zone(0,0,360,200), q); img.save('/tmp/market_preview.png'); print('saved')
"
```
打开 `/tmp/market_preview.png` 目视:标题「行情」、各行 名称+现价+涨跌幅,涨(上证/BTC)红、跌(茅台)黑。

- [ ] **Step 3: 对照 spec 第 12 节验收逐条打勾**

1. 网页增删标的(A股+加密)+ 屏上显示名称/现价/涨跌幅(涨红跌黑)—— Task 3/5/6/7/8/9。
2. 后台抓取不阻塞渲染;单标的失败跳过、整源失败用旧缓存,不崩 —— Task 3/5。
3. 无标的/坏缓存不崩;非法标的被 API 拒 —— Task 3/6/8。
4. 全部测试通过且不真连 —— Step 1。

- [ ] **Step 4: 归档提示**

合并后可把本期 spec+plan 移入 `docs/superpowers/archive/`。仅提示。

---

## 自检(写计划后已核对)

- **Spec 覆盖**:§5.1 常量+归一 → T1;§5.2 parse(腾讯[1]/[3]/[32]、OKX last/open24h)→ T1,fetch → T2;§5.3 MarketService(current/clear/_sig/_needs_refresh/refresh_now 单标的跳过+整源失败留旧/maybe_refresh)→ T3;§4 config(market_cache + market_symbols RUNTIME)→ T4;§4 state 注入+非阻塞刷新 → T5;§6 widget(涨红跌黑/空/截断)→ T6;§4 registry → T7;§7 API(GET market、symbols GET/POST 规范化去重校验/DELETE)→ T8;§8 网页卡片 → T9;§9 错误处理(坏缓存当空、单标的跳过、整源失败留旧、非法 400、空提示)→ T3/T6/T8;§10 测试(全 mock)→ 各任务;§11 无新依赖 → 确认;§12 验收 → T10。无遗漏。
- **签名/命名一致**:`parse_tencent(line)`、`parse_okx(obj,code)`、`is_stale`、`fetch_cn(codes)`、`fetch_crypto(code)`、`_get_bytes`、`MarketService.current()/clear()/_sig/_needs_refresh/refresh_now(symbols,now,fetch_cn=,fetch_crypto=)/maybe_refresh`、`draw_market(d,z,quotes)`、state 键 `market`、registry `market`、config `market_cache`/`market_symbols` —— 全计划统一。缓存结构 `{fetched_at,sig,quotes}` 一致。
- **无占位符**:每个改码步骤均给出完整代码与确切路径/命令/预期输出。
- **网络隔离**:T1 纯解析;T2 mock `_get_bytes`;T3 注入假 fetch;T5 state 用新鲜同 sig 缓存避免起线程;T8 API 不触发刷新(仅 current 读空缓存);T10 显式核对运行时长。
```
