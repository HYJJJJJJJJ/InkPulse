# InkPulse 温度曲线 widget(设计文档)

> 日期:2026-06-14 · 状态:已通过设计评审,待写实现计划
> 关联:网格布局系统(第一期,已归档)· 第二期只读 widget `usage_trend`/`project_dist`(已归档)· 习惯打卡(第二期,已合并)

## 1. 背景与目标

第二期数据 widget 的收尾项。板子(ESP32-S3 + HTU21D)每次拉帧 `GET /frame?t=..&h=..&rssi=..` 顺带上报温湿度;hub 现状只用 `set_env` 保存**最新一条**,无历史。湿度通道硬件损坏(I2C NACK,恒回哨兵值),仅温度有效,故本 widget 是**温度曲线**(非温湿度)。

目标:在墨水屏上画**最近 24 小时**的温度折线,叠加**当前温度大数字**与**24h 峰谷**,让人一眼看出室温现状与一天波动。需要新增历史存储(持久化,hub 重启不丢)。

## 2. 范围

### 本期做(In Scope)
- 历史存储 `EnvHistoryStore`(`~/inkpulse/env_history.json`):按时间追加温度采样 + 24h 裁剪 + 取窗口。
- `/frame` 入口:温度有效时追加一条采样。
- `state` 注入近 24h 采样(纯函数化,便于测试)。
- 屏上 widget `draw_temp_trend`:24h 温度折线 + 当前值大数字 + 高/低标记,注册为 `temp_trend`。
- 配套测试。

### 本期不做(Out of Scope / YAGNI)
- 湿度曲线(通道坏,无有效数据)。
- 网页端展示/配置温度历史(只读 widget,无交互)。
- 可配置时间窗 / 多档窗口(固定 24h)。
- y 轴刻度线 / 网格(墨水屏小字易糊,brainstorm 决定不做)。
- 高频采样 / 下采样固定槽(读数本就 ~10 分钟一个,直接画即可)。
- 温度报警 / 阈值标红(纯黑显示)。

## 3. 决策记录(brainstorm 结论)

| 决策点 | 选择 | 理由 |
|---|---|---|
| 时间窗 | **最近 24 小时** | 看一天昼夜温差节律;~144 点数据量可控 |
| 叠加信息 | **当前温度大数字 + 24h 高/低标记** | 信息够又不挤;y 轴刻度小字易糊,不做 |
| 存储 | **持久化环形(裁剪)列表落盘** | hub/板子重启不丢;仿 `TodoStore`/`HabitStore` 落盘模式 |
| 采样 | **每帧上报即存一条(~10min/点)** | `refresh_periodic_s=600`,读数天然稀疏,无需高频/下采样 |
| 峰谷标记字形 | **「高/低」中文字**,不用 `↑↓` 箭头 | 规避思源黑符号字形缺失风险 |
| 折线 x 轴 | **固定窗口 `[now-24h, now]` 映射** | 数据有空档显示为稀疏,不假装连续 |

## 4. 架构总览

```
板子 GET /frame?t=23.4&h=..&rssi=..
  └─ state.set_env(t,h,rssi)                 # 现有: 存最新一条(头部右上角用)
  └─ state.env_history.append(now, t)        # 新增: t 有效才追加, 顺手裁掉 >24h

build_render_state(now)
  └─ state["env_history"] = EnvHistoryStore(cfg.env_history_store).window(now)
       → [[ts:float, temp:float], ...]  近24h, 按 ts 升序

render: placement(widget="temp_trend")
  └─ _temp_trend 适配器 → draw_temp_trend(d, z, state["env_history"], state["now"])
```

设计要点:有效性过滤 + 裁剪 + 取窗口都在 `EnvHistoryStore`;widget 为纯函数(注入采样 + now),无 I/O 无时间调用,测试确定性。只存 `t` 不存 `h`,坏湿度数据自然被排除在外。

### 模块划分(单一职责)
- `collectors/env_history.py`(新增):`EnvHistoryStore` —— env_history.json 读写 + append(裁剪) + window。
- `config.py`(改):新增 `env_history_store` 路径字段 + `sources.env_history_store` 覆盖。
- `server.py`(改):`/frame` 里温度有效时 `state.env_history.append(time.time(), t)`。
- `state.py`(改):`HubState` 持有 store;`build_render_state` 注入 `env_history`。
- `render/widgets.py`(改):新增 `draw_temp_trend`。
- `render/registry.py`(改):注册 `temp_trend` widget + 适配器。

## 5. 数据模型

### 5.1 存储(`~/inkpulse/env_history.json`)
裸 JSON 列表(仿 `todos.json`),每条 `[unix秒(float), 温度(float)]`,按 ts 升序:
```jsonc
[[1749800000.0, 23.4], [1749800600.0, 23.6], [1749801200.0, 23.1]]
```
- 文件不存在/损坏(非列表/JSON 错)→ 视为空 `[]`,不抛异常。

### 5.2 `EnvHistoryStore`(`collectors/env_history.py`)
```python
RETENTION_S = 86400          # 24h
TEMP_MIN, TEMP_MAX = -40.0, 85.0   # 合理温度范围(挡 None/哨兵/越界)

class EnvHistoryStore:
    def __init__(self, path): ...
    def append(self, ts: float, temp) -> None:
        # temp 为 None 或不在 [TEMP_MIN, TEMP_MAX] → 直接 return(不存)
        # 否则: 读 → 追加 [ts, float(temp)] → 裁掉 ts < (this_ts - RETENTION_S) → 写
    def window(self, now: float) -> list[list]:
        # 返回 ts >= now - RETENTION_S 的采样, 按 ts 升序
```
- 裁剪以"本次 append 的 ts"为基准(`ts - RETENTION_S`),避免依赖墙钟。
- `window` 再按传入的 `now` 过滤一次(渲染时刻可能晚于最后采样)。

## 6. 屏上 widget(`draw_temp_trend`)

```
┌ 温度曲线 24h ─────────┐
│                      23°C │   ← 当前温度大数字(右上, 末点温度)
│        ╭╮      ╭─╮         │
│   ╭───╯ ╰─╮  ╭╯  ╰──╮      │   ← 24h 折线(纯黑)
│ ──╯       ╰──╯      ╰───   │
│ 高 26°  低 18°             │   ← 24h 峰谷(左下, 中文字)
└──────────────────────────┘
```
- 顶部 `_title_bar("温度曲线 24h")`。
- 采样数 `< 2` → 居中提示「暂无温度数据」,return(不崩)。
- **当前值**:末点温度,右上角大字号 `f"{temp:.0f}°C"`。
- **折线**:
  - x:`ts` 在 `[now-86400, now]` 线性映射到 [zone 左, zone 右];数据有空档则点稀疏(只连相邻采样点)。
  - y:`temp` 在 `[tmin, tmax]` 映射到 [zone 下, zone 上](温度高→偏上);`tmin==tmax`(全等)时画水平中线避免除零。
  - 相邻采样点 `d.line` 连段;单段宽度由像素决定,不分桶。
- **峰谷**:窗口内 `max`/`min` 温度,左下角 `f"高 {tmax:.0f}°  低 {tmin:.0f}°"`(中文字,避开箭头字形)。
- 纯黑,无红。
- 签名:`draw_temp_trend(d, z, samples, now)`,`samples=[[ts,temp], ...]` 升序。

## 7. 集成点

- `config.py`:`Config` 加 `env_history_store: str = os.path.expanduser("~/inkpulse/env_history.json")`;`load_config` 加 `sources.env_history_store` 覆盖。
- `state.py`:`HubState.__init__` 加 `self.env_history = EnvHistoryStore(cfg.env_history_store)`;`build_render_state` 加 `"env_history": self.env_history.window(now)`。
- `server.py`:`/frame` 内 `set_env` 之后,`if t is not None: state.env_history.append(time.time(), t)`(有效性由 append 内部把关)。
- `registry.py`:适配器 `_temp_trend(d,img,z,state,cfg,p) → W.draw_temp_trend(d, z, state.get("env_history", []), state.get("now"))`;`REGISTRY` 加 `"temp_trend": WidgetSpec("temp_trend","温度曲线",_temp_trend,{"cols":4,"rows":3})`(无参数)。

## 8. 错误处理

- env_history.json 不存在/损坏 → 当空 `[]`,不崩。
- 温度 `None`/越界(挡哨兵/坏值)→ append 静默丢弃,不入库。
- 采样 `< 2` → widget 画「暂无温度数据」提示,不崩。
- 全等温度(`tmin==tmax`)→ 画水平中线,不除零。
- 单 widget 异常仍由引擎 per-widget 隔离画 `n/a`。

## 9. 测试计划(pytest)

- `EnvHistoryStore`:append 后 window 含该点;append 越界/None 不入库;超 24h 旧点被裁;损坏文件当空;持久化跨实例;window 按 now 过滤并升序。
- `state`:`build_render_state` 含 `env_history`(list)。
- `server`:`GET /frame?t=23.4` 后 `state.env_history.window(now)` 多一条;`t` 缺省不追加。
- `draw_temp_trend`:有数据画黑线;空/单点画提示不崩;全等温度不崩;当前值与峰谷文字出现(有黑像素)。
- `registry`:`temp_trend` 已注册,注入 state 下绘制不抛错。

## 10. 新增依赖

无。复用现有 Pillow / 标准库。

## 11. 验收标准

1. 板子上报温度后,屏上 `temp_trend` 显示近 24h 折线,右上当前值、左下高/低标记。
2. hub 重启后历史仍在(持久化生效)。
3. 无数据/坏文件/坏温度值不崩;湿度坏通道数据不入库。
4. 全部测试通过。
