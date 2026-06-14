# InkPulse 行情 widget(设计文档)

> 日期:2026-06-14 · 状态:已通过设计评审,待写实现计划
> 关联:天气 `weather`(联网范式:fetch+缓存+stale-while-revalidate,已归档)。第三期最后一块。

## 1. 背景与目标

第三期联网 widget 的收尾项:**行情**。在墨水屏上显示一组自选标的(**A股/指数 + 加密货币**)的现价与涨跌幅;标的在网页 `/config` 管理。复用天气立的联网范式(后台抓取 + 缓存 + 失败降级,渲染不阻塞网络)。

## 2. 范围

### 本期做(In Scope)
- `collectors/market.py`:两源抓取(腾讯 A股 / OKX 加密)+ 解析归一 + 带缓存的 `MarketService`(SWR)。
- 自选标的配置(runtime,网页增删):`market_symbols`。
- 屏上 widget `draw_market`:名称 + 现价 + 涨跌幅(涨红跌黑),注册为 `market`。
- `state` 注入当前行情(纯函数化,便于测试)。
- 网页 `/config` 行情卡片:增/删标的(类型 + 代码)。
- 配套 API 与测试。

### 本期不做(Out of Scope / YAGNI)
- K线 / 分时图 / 历史走势 / 盘口五档。
- 美股 / 港股 / 场外基金(本期只 A股+指数+加密;美股港股境内源不稳)。
- 涨跌停 / 阈值提醒、自选排序拖拽。
- 货币换算(加密以 OKX 计价币种原样显示,如 USDT)。

## 3. 决策记录(brainstorm 结论 + 实测)

| 决策点 | 选择 | 理由 / 实测 |
|---|---|---|
| 标的类型 | **A股/指数 + 加密** | 用户需求 A+C |
| A股源 | **腾讯 `qt.gtimg.cn`** | 实测可用、无 key、无需 Referer、支持逗号批量;**返回 GBK** 需解码;自带名称 |
| 加密源 | **OKX `www.okx.com/api/v5/market/ticker`** | 实测干净 JSON、无 key、代理可达;**Binance 实测被地域封锁**(restricted location)故弃用 |
| 抓取/缓存 | **复用天气 SWR** | 后台线程刷新,`current()` 只读缓存不阻塞渲染,失败降级旧缓存 |
| 刷新间隔 | **300 秒(5 分钟)** | 行情变化快于天气;每 /frame 本就 ~10min,5min TTL 触发后台刷新 |
| 涨跌配色 | **涨=RED,跌/平=BLACK** | 中国"红涨绿跌";e-ink 三色有红无绿,故涨用红、跌用黑 |
| 标的存储 | **`market_symbols` 进 RUNTIME_FIELDS** | 网页可调;runtime.json 存列表 |

## 4. 架构总览

```
/config 行情卡片 ──(增/删标的)──> /api/market/symbols ──> cfg.market_symbols + save_runtime + svc.clear()

板子 GET /frame → build_render_state(now):
  market_symbols 非空? → svc.current() 取缓存(命中即用)
                         svc.maybe_refresh(symbols, now)  # 过期/标的变更则后台线程抓取, 本次不等
                       → state["market"] = [{type,code,name,price,change_pct}, ...]
  为空? → state["market"] = []
render: placement(widget="market")
  └─ _market 适配器 → draw_market(d, z, state["market"])
```

要点:网络与渲染解耦(`current()` 只读缓存);解析为纯函数(注入字节/JSON),`MarketService` 的刷新决策(`_needs_refresh`)与同步抓取(`refresh_now`)分离、线程仅包装 —— 全部可单测,网络不真连。

### 模块划分(单一职责)
- `collectors/market.py`(新增):见 §5。
- `config.py`(改):`market_cache` 路径字段 + sources 覆盖;`market_symbols` 进 `RUNTIME_FIELDS`。
- `state.py`(改):`HubState` 持 `MarketService`;注入 `market` + 触发非阻塞刷新。
- `render/widgets.py`(改):新增 `draw_market`。
- `render/registry.py`(改):注册 `market`。
- `server.py`(改):`/api/market*` 端点。
- `web/config.html`(改):行情卡片。

## 5. `collectors/market.py`

### 5.1 常量与归一结构
```python
REFRESH_S = 300                       # 5 分钟
TIMEOUT_S = 8
TENCENT = "https://qt.gtimg.cn/q="    # 批量: 逗号拼接 cn 代码
OKX = "https://www.okx.com/api/v5/market/ticker?instId="
# 归一 quote: {"type": "cn"|"crypto", "code": str, "name": str,
#             "price": float, "change_pct": float}
```

### 5.2 抓取与解析(纯解析可单测)
```python
def _get_bytes(url) -> bytes: ...        # urlopen().read(); 网络seam, 测试 monkeypatch

def parse_tencent(text: str) -> dict:
    # 入参: 已 GBK 解码的一行 v_sh000001="1~名称~代码~现价~昨收~..~涨跌幅~..";
    # 取 名称=字段[1], 现价=float(字段[3]), change_pct=float(字段[32])
    # 返回 {type:"cn", code, name, price, change_pct}; 字段不足/非数值 -> 抛/None 由调用方跳过

def fetch_cn(codes: list) -> list:
    # 批量: _get_bytes(TENCENT + ",".join(codes)).decode("gbk"); 按行解析 parse_tencent
    # 每行失败跳过; 整体网络失败抛(由 refresh 吞)

def parse_okx(obj: dict, code: str) -> dict:
    # obj = OKX 响应; d=obj["data"][0]; last=float(d["last"]); open24h=float(d["open24h"])
    # change_pct = (last-open24h)/open24h*100; name = code 去 "-USDT" 等取基础符号(如 BTC)
    # 返回 {type:"crypto", code, name, price:last, change_pct}

def fetch_crypto(code) -> dict:
    # json.loads(_get_bytes(OKX + code)); parse_okx
```

### 5.3 `MarketService`(缓存 + SWR,结构同 `WeatherService`)
```python
def is_stale(fetched_at, now) -> bool: return (now - fetched_at) >= REFRESH_S

class MarketService:
    def __init__(self, cache_path): ...           # makedirs; Lock + _refreshing
    def _read_cache(self): ...                     # {fetched_at, sig, quotes}; 坏/缺 -> None
    def current(self) -> list:                     # 读缓存返回 quotes(无缓存 -> [])
    def clear(self): ...
    def _sig(self, symbols): ...                   # 标的签名(用于检测变更), 如 tuple(sorted(...))
    def _needs_refresh(self, symbols, now): ...     # 无缓存 / 标的变更 / is_stale
    def refresh_now(self, symbols, now, fetch_cn=fetch_cn, fetch_crypto=fetch_crypto):
        # 分流: cn 批量 fetch_cn, crypto 逐个 fetch_crypto; 单标的失败跳过
        # 成功项汇成 quotes(保持 symbols 顺序), 写缓存 {fetched_at:now, sig, quotes}
        # 整体异常吞掉记日志, 保留旧缓存
    def maybe_refresh(self, symbols, now, ...):     # _needs_refresh 才起 daemon 线程
```
- 缓存文件 `~/inkpulse/market_cache.json`:`{"fetched_at": float, "sig": [...], "quotes": [...]}`。坏/缺当无缓存。
- `current()` 不触网(渲染路径只调它 + `maybe_refresh`)。

## 6. 屏上 widget(`draw_market`)

```
┌ 行情 ─────────────────┐
│ 上证指数   4031.51  +1.12% │   ← 涨=红
│ 贵州茅台   1680.00  -0.45% │   ← 跌=黑
│ BTC       64544.6  +1.04% │
└──────────────────────┘
```
- 顶部 `_title_bar("行情")`。
- `quotes` 为空 → 居中提示「无标的 · 去网页添加」,return。
- 每行:名称(左,超长截断)+ 现价(中)+ 带符号涨跌幅(右,`+1.12%`/`-0.45%`)。
  - **涨跌幅 > 0 → RED;≤ 0 → BLACK**(名称与现价恒黑)。
  - 价格格式:`f"{price:.2f}"`(加密大数也用 2 位小数,够用)。
- 按 `zone.h` 估算可容纳行数,`quotes[:N]` 截断。
- 签名 `draw_market(d, z, quotes)`,`quotes=[{name,price,change_pct,...}]`。

## 7. API(`server.py`)

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/market` | `{symbols: cfg.market_symbols, quotes: svc.current()}`,供网页显示当前 |
| GET | `/api/market/symbols` | 返回 `cfg.market_symbols` |
| POST | `/api/market/symbols` | body `{type,code}`;`type∈{cn,crypto}` 且 `code` 非空 → 追加并 `save_runtime`+`svc.clear()`;否则 400;重复(同 type+code)忽略 |
| DELETE | `/api/market/symbols` | body `{type,code}`(或 query),移除该标的 + `save_runtime`+`svc.clear()` |

- `code` 规范化:cn 去空格小写(如 `sh000001`);crypto 大写(如 `BTC-USDT`)。具体规范化在 server 入口做。

## 8. 网页 `/config` 行情卡片

- 列出 `market_symbols`:`类型 代码  ×`(× 删除)。
- 录入行:类型下拉(A股/指数=cn、加密=crypto)+ 代码输入(占位提示:cn 填 `sh000001`/`sh600519`,crypto 填 `BTC-USDT`)+「添加」。
- 增删后刷新本卡片 + `refreshPreview()`。

## 9. 错误处理

- `market_symbols` 为空 → widget「无标的 · 去网页添加」;`/api/market` 的 `quotes` 为 `[]`。
- 首次无缓存 → widget 同空提示(后台已起刷新,下帧即有);为简化不单设"加载中"态(行情非首屏关键)。
- 单标的抓取/解析失败 → 跳过该标的,其余正常;整源网络失败 → 后台线程吞异常、保留旧缓存。
- 缓存文件坏/缺 → 当无缓存,不崩。
- GBK 解码失败 → 该批 cn 解析跳过(不崩)。
- POST 非法 type / 空 code → 400。
- 并发刷新 `_refreshing` 标志防抖;daemon 线程不挂起进程。
- 单 widget 异常仍由引擎 per-widget 隔离画 `n/a`。

## 10. 测试计划(pytest,**不真连网络**)

- `parse_tencent`:样例(GBK 解码后的)行 → 名称/现价/涨跌幅;字段不足/非数值不崩(跳过)。
- `parse_okx`:样例 OKX JSON → last/change_pct 计算;name 取基础符号。
- `fetch_cn`/`fetch_crypto`:monkeypatch `_get_bytes` 返回样例字节(cn 给 GBK 编码字节)→ 归一结构;批量多行;单行坏跳过。
- `is_stale`:边界。
- `MarketService`:注入假 `fetch_cn`/`fetch_crypto` + 控 `now` —— 无缓存刷新、新鲜不刷、标的变更刷新(`_sig`)、`refresh_now` 写缓存、单标的失败仍写其余、整体失败保留旧缓存、`current` 无缓存返回 `[]`、`clear`。
- `state`:无标的 → `market` `[]`;有标的 + 注入新鲜缓存 → `market` 为 list。
- `draw_market`:有数据画黑+红像素(涨红);空 → 提示不崩;全跌(无红)只黑;长名截断不崩。
- API:GET 结构;POST 加 / 非法 type 拒 / 空 code 拒 / 重复忽略;DELETE。
- `registry`:`market` 已注册,注入 state 下绘制不抛错。

## 11. 新增依赖

无。`urllib`/`json`/`threading`/`bytes.decode("gbk")`(GBK 编解码是 Python 标准库内置 codec)均标准库。

## 12. 验收标准

1. 网页能增删自选标的(A股/指数 + 加密);屏上 `market` widget 显示各标的名称+现价+涨跌幅,涨红跌黑。
2. 网络后台抓取不阻塞渲染;单标的失败跳过、整源失败用旧缓存,不崩。
3. 无标的/坏缓存不崩;非法标的被 API 拒。
4. 全部测试通过(网络部分 mock,不真连)。
