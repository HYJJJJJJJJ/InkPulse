# InkPulse 天气 widget(设计文档)

> 日期:2026-06-14 · 状态:已通过设计评审,待写实现计划
> 关联:第二期数据 widget(已归档 `docs/superpowers/archive/`)。**第三期(联网 widget)的第一个**。

## 1. 背景与目标

第三期做需要**对外请求第三方 API** 的 widget(前两期全是本地数据、零联网)。本设计是第三期第一个:**天气**。

目标:在墨水屏上显示某地点的**当前天气 + 未来 3 天预报**;地点由用户在网页 `/config` 搜索城市设定。这是项目首个联网 widget,重点是把"联网"的复杂度(失败降级、缓存、不阻塞渲染)处理干净,为后续日程/行情 widget 立范式。

## 2. 范围

### 本期做(In Scope)
- 数据源 Open-Meteo(免费、**无需 API key**),标准库 `urllib.request` 抓取(零新依赖)。
- `collectors/weather.py`:抓取 + 解析 + 地理编码 + 带缓存的 `WeatherService`(stale-while-revalidate)。
- 网页 `/config` 天气地点卡片:城市搜索 → 选定 → 存坐标到 runtime。
- 屏上 widget `draw_weather`:当前天气(手绘图标 + 中文词 + 当前温度)+ 今日高低 + 未来 3 天预报 + 缓存新鲜度。注册为 `weather`。
- 配套 API 与测试。

### 本期不做(Out of Scope / YAGNI)
- 空气质量 / AQI(Open-Meteo 另一套接口,后续再说)。
- 逐小时预报、降水概率、风力风向、日出日落、生活指数。
- 多地点切换 / 收藏夹(只存一个地点)。
- IP 自动定位(本机常开代理 TUN,IP 会解析到代理出口节点的城市,必然错;故只用网页手动配)。
- 天气预警推送 / 阈值标红(纯黑显示)。
- 字体天气符号字形(思源黑缺失严重,改用 Pillow 手绘图标)。

## 3. 决策记录(brainstorm 结论)

| 决策点 | 选择 | 理由 |
|---|---|---|
| 数据源 | **Open-Meteo** | 完全免费、**无需 key**、全球、当前+逐日齐全;换源只影响一个模块 |
| HTTP | **标准库 `urllib.request`** | 零新依赖,延续项目最小依赖原则 |
| 定位 | **网页手动配地点(地理编码)** | IP 定位因代理 TUN 必然错;`/config` 搜城市最稳且契合现有模式 |
| 抓取时机 | **stale-while-revalidate,后台线程刷新** | 渲染**绝不阻塞网络**(否则一帧卡在超时上,叠加 e-ink 21s 很糟) |
| 刷新间隔 | **30 分钟** | 天气变化慢,避免每帧打 API |
| 展示 | **手绘图标 + 中文天气词 + 温度** | 图标比纯文字好看;字体符号字形缺失,故 Pillow 自绘(同打卡/曲线画法) |
| 图标 | **7 类**(晴/多云/阴/雾/雨/雪/雷) | WMO 码归并,绘制函数可控 |

## 4. 架构总览

```
/config 搜城市 → GET /api/weather/search?q=杭州 → geocode() → 候选[{name,lat,lon,admin}]
  用户选定 → POST /api/weather/location {lat,lon,name} → 存 runtime + 清 weather_cache

板子 GET /frame → build_render_state(now):
  有坐标? → svc.current(now) 取缓存(命中即用)
            svc.maybe_refresh(lat, lon, now)  # 过期/坐标变更则起后台线程抓取, 本次不等
          → state["weather"] = {...解析数据, "age_s", "status"}  (无缓存则 None)
            state["weather_place"] = "杭州"
  无坐标? → state["weather"] = None; state["weather_place"] = None
render: placement(widget="weather")
  └─ _weather 适配器 → draw_weather(d, z, state["weather"], state["weather_place"])
```

设计要点:**网络与渲染解耦**——渲染只读缓存,刷新在后台线程;`parse_weather` 为纯函数(注入 JSON + now),`is_stale` 为纯函数,均确定性可测;网络抓取(`fetch_weather`/`geocode`)隔离在薄薄一层,单测不真连(mock `urlopen` 或只测解析)。

### 模块划分(单一职责)
- `collectors/weather.py`(新增):见 §5。
- `config.py`(改):`weather_cache` 路径字段 + `sources` 覆盖;`weather_lat`/`weather_lon`/`weather_place` 进 `RUNTIME_FIELDS`。
- `state.py`(改):`HubState` 持 `WeatherService`;`build_render_state` 注入 `weather`/`weather_place` 并触发非阻塞刷新。
- `server.py`(改):`/api/weather*` 端点。
- `render/widgets.py`(改):`draw_weather` + 7 图标 helper。
- `render/registry.py`(改):注册 `weather`。
- `web/config.html`(改):天气地点卡片。

## 5. `collectors/weather.py`

### 5.1 WMO 天气码 → 中文 + 图标类别
```python
# 类别枚举: "sun" "partly" "cloud" "fog" "rain" "snow" "thunder"
# WMO_CN[code] = (中文词, 类别)
# 0 晴/sun; 1 晴/sun; 2 多云/partly; 3 阴/cloud;
# 45,48 雾/fog; 51..57 毛毛雨/rain; 61..67 雨(小/中/大)/rain;
# 71..77 雪/snow; 80..82 阵雨/rain; 85,86 阵雪/snow; 95..99 雷阵雨/thunder
```
未知码 → `("未知", "cloud")` 兜底。

### 5.2 抓取与解析
```python
OPEN_METEO = "https://api.open-meteo.com/v1/forecast"
GEOCODE = "https://geocoding-api.open-meteo.com/v1/search"
TIMEOUT_S = 8

def fetch_weather(lat, lon) -> dict:
    # urlopen(OPEN_METEO?latitude=&longitude=&current=temperature_2m,weather_code
    #         &daily=weather_code,temperature_2m_max,temperature_2m_min
    #         &timezone=auto&forecast_days=4, timeout=TIMEOUT_S) -> json.load
    # 抛 URLError/超时/JSON 错由调用方处理

def parse_weather(raw: dict, now: float) -> dict:
    # 纯函数。返回:
    # {"cur_temp": float, "cur_code": int, "cur_cn": str, "cur_cat": str,
    #  "today_hi": float, "today_lo": float,
    #  "days": [{"label": "明"/"周三", "cn", "cat", "hi", "lo"}, ...3条]}  # 未来3天
    # label: 明天="明", 其余用 _WEEKDAYS; 日期对齐用 daily.time

def geocode(name) -> list[dict]:
    # urlopen(GEOCODE?name=&count=5&language=zh) -> [{"name","lat","lon","admin"}]
    # 无结果/失败 -> []
```

### 5.3 缓存与 SWR(`WeatherService`)
```python
REFRESH_S = 1800   # 30 分钟

def is_stale(fetched_at, now) -> bool:   # 纯函数
    return (now - fetched_at) >= REFRESH_S

class WeatherService:
    def __init__(self, cache_path): ...
    def current(self, now) -> dict | None:
        # 读缓存文件 {fetched_at, lat, lon, raw}; 无 -> None
        # 返回 {**parse_weather(raw, now), "age_s": now-fetched_at,
        #       "status": "ok"|"stale"}  (stale = is_stale)
    def maybe_refresh(self, lat, lon, now) -> None:
        # 若无缓存 或 缓存坐标≠当前坐标 或 is_stale: 且当前无刷新在跑 ->
        #   起 daemon 线程: fetch_weather -> 写缓存 {fetched_at:now,lat,lon,raw}
        #   线程内异常 try/except 吞掉(记 print), 不抛
        # 用 threading.Lock + _refreshing 标志防并发
    def clear(self) -> None:   # 删缓存文件(改地点时调)
```
- 缓存文件 `~/inkpulse/weather_cache.json`:`{"fetched_at": float, "lat": float, "lon": float, "raw": {...}}`。坏/缺 → 视为无缓存。
- `current` 不触发网络;`maybe_refresh` 才可能起线程。渲染路径只调 `current` + `maybe_refresh`(后者立即返回)。

## 6. 屏上 widget(`draw_weather`)

```
┌ 天气 · 杭州 ─────────────┐
│  (大图标) 多云   23°C     │
│           今日 26° / 18°   │
│ ───────────────────────  │
│ 明  (小)  27° / 19°       │
│ 周三(小)  24° / 17°       │
│ 周四(小)  22° / 16°       │
│              更新于 12 分钟前 │
└─────────────────────────┘
```
- 顶部 `_title_bar(f"天气 · {place}")`(无 place 时 `"天气"`)。
- 签名 `draw_weather(d, z, weather, place)`,**三态由 (place, weather) 区分**(无需额外标志):
  - `place is None` → 「未设置地点 · 去网页添加」(无坐标)。
  - `place` 有值 且 `weather is None` → 「加载中…」(有坐标但首次无缓存)。
  - `weather` 有值 → 正常态(下述)。
- 正常态:当前块大图标(§5.1 类别 → §6.1 绘制)+ 中文词 + 当前温度大字;今日高/低;分隔线;未来 3 天每行 小图标 + 高/低。
- 右下角:`age_s` → 「更新于 X 分钟前」(`status=="stale"` 也照常显示,数据即便旧也展示)。
- 纯黑无红。

### 6.1 七类图标(Pillow 手绘,字体无关)
`_wx_icon(d, cx, cy, r, cat)`:按 `cat` 画——
- `sun`:实心圆 + 8 条放射短线。
- `partly`:小太阳(圆+短线)左上 + 一朵云右下盖住部分。
- `cloud`:2~3 个叠圆 + 平底(空心或浅填)。
- `fog`:云 + 下方 3 条横线。
- `rain`:云 + 4~5 条斜短线。
- `snow`:云 + 3 个雪点(小圆/米字)。
- `thunder`:云 + 一条闪电折线(多段 `line`)。
大图标 `r` 大、预报行小图标 `r` 小,同一函数按 `r` 缩放。

## 7. API(`server.py`)

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/weather/search?q=` | 代理 `geocode(q)`,返回候选 `[{name,lat,lon,admin}]`;空 `q` → `[]` |
| POST | `/api/weather/location` | body `{lat,lon,name}`,存进 runtime(`weather_lat/lon/place`)并 `save_runtime` + `svc.clear()`;缺字段 → 400 |
| DELETE | `/api/weather/location` | 清除地点(三字段置空)+ `save_runtime` + `svc.clear()` |
| GET | `/api/weather` | `{place, lat, lon, weather: current(now)或null}`,供 `/config` 显示当前 |

## 8. 网页 `/config` 天气地点卡片

- 搜索框 + 「搜索」:输入城市 → `GET /api/weather/search?q=` → 候选列表(每条 `名字 · 省/行政区`,点击即 `POST /api/weather/location`)。
- 顶部显示当前地点(`GET /api/weather` 的 `place`)+「清除」(`DELETE`)。
- 设置/清除后刷新本卡片 + `refreshPreview()`(沿用现有模式)。

## 9. 错误处理

- 无坐标 → widget「未设置地点 · 去网页添加」;API `/api/weather` 的 `weather` 为 null。
- 首次无缓存 → widget「加载中…」(后台已起刷新,下帧即有)。
- 抓取失败(网络/超时/解析)→ 后台线程吞异常记日志、不写缓存;`current` 仍返回上次缓存(`status` 可能 `stale`),widget 照常显示 + 「更新于 X 分钟前」;彻底无缓存才「加载中…」直至成功。
- `geocode` 无结果/失败 → 返回 `[]`,前端提示「没找到」。
- 并发刷新由 `_refreshing` 标志 + Lock 防抖;线程 daemon,进程退出不挂起。
- 缓存文件坏/缺 → 当无缓存,不崩。
- 单 widget 异常仍由引擎 per-widget 隔离画 `n/a`。

## 10. 测试计划(pytest,**不真连网络**)

- `parse_weather`:用样例 Open-Meteo JSON → 当前温度/天气码/中文词/类别正确;今日高低;未来 3 天 label(明/周X)与高低;各 WMO 段(0/2/3/45/61/71/80/95)映射到正确中文+类别;未知码兜底。
- `is_stale`:边界(刚好 30 分钟、之内、之外)。
- `WeatherService`:注入假 `fetch`(monkeypatch)+ 控 `now` —— 新鲜不刷;过期触发刷新写缓存;坐标变更触发刷新;`fetch` 抛异常时保留旧缓存不崩;无缓存 `current` 返回 None;`clear` 删缓存。
- `geocode`:mock `urlopen` 返回样例 JSON → 候选解析;空结果 → `[]`。
- `state`:无坐标 → `weather` None、`weather_place` None;有坐标(注入假缓存)→ `weather` 为 dict。
- `draw_weather`:正常数据画黑像素;7 类图标各画不崩;`place=None`→未设置提示;`place` 有值+`weather=None`→加载中;有黑像素、不崩。
- API:`search`(mock geocode)、`location` POST 存 runtime + 缺字段 400、`DELETE` 清除、`GET /api/weather` 结构。
- `registry`:`weather` 已注册,注入 state 下绘制不抛错。

## 11. 新增依赖

无。`urllib.request` / `json` / `threading` 均标准库。

## 12. 验收标准

1. 网页搜城市并选定后,屏上 `weather` widget 显示该地当前天气(图标+中文+温度)+ 今日高低 + 未来 3 天。
2. 网络抓取在后台进行,**不阻塞渲染**;抓取失败时显示上次缓存 + 新鲜度,不崩。
3. 未设地点显示提示;首次加载显示「加载中…」;坏缓存/无结果不崩。
4. 全部测试通过(网络部分以 mock/纯解析覆盖,不真连)。
