# InkPulse 日程 widget(设计文档)

> 日期:2026-06-14 · 状态:已通过设计评审,待写实现计划
> 关联:待办 `todos`(本地录入范式)· 月历 `calendar` · 天气 `weather`(已归档)。第三期原计划联网,但日程无可靠外部来源(用户无可用 ICS),故落地为**本地录入打样**。

## 1. 背景与目标

第三期日程 widget。原设想订阅外部日历(ICS),但用户**当前没有可靠的 ICS 来源**,故本期不联网,做一个**本地录入的最小可用日程板**:用户在网页 `/config` 添加日程(标题 + 日期 + 可选时间),墨水屏按时间排出近期日程、过期自动隐去。定位是"打样",刻意精简。

与现有 `todos` 的区别:日程带**具体日期/时刻**,按时间排序、按相对日(今天/明天/日期)标注、过期自动消失;`todos` 是无时间的勾选清单。

## 2. 范围

### 本期做(In Scope)
- 事件存储 `EventStore`(`~/inkpulse/events.json`):增/删/列表 + `upcoming` 过滤排序。仿 `TodoStore`。
- 屏上 widget `draw_agenda`:近期日程列表(相对日标签 + 时间 + 标题),注册为 `agenda`。
- `state` 注入近期日程(纯函数化,便于测试)。
- 网页 `/config` 日程卡片:增/删 + 录入(标题 + 日期 + 可选时间)。
- 配套 API 与测试。

### 本期不做(Out of Scope / YAGNI)
- 订阅外部日历(ICS/CalDAV)—— 无可靠来源,留待以后。
- 重复事件、提醒/通知、条目编辑、起止时间段、地点/备注。
- 跨设备同步、农历/节假日联动(农历已在头部)。
- 屏上录入(墨水屏无输入)。

## 3. 决策记录(brainstorm 结论)

| 决策点 | 选择 | 理由 |
|---|---|---|
| 数据来源 | **本地手动录入** | 无可靠 ICS 来源;先打样 |
| 条目粒度 | **标题 + 日期 + 可选时间** | 填时间=定时事件,不填=全天;最贴合真实日程又不啰嗦 |
| 排序/范围 | **按 date+time 升序,只显 date≥今天,取前 N** | 议程式展示,过期自动隐去 |
| 过期判定 | **按日期**(date < 今天 隐去) | 简单;今天的事件当天整天都显示,不按时刻消失 |
| widget 名 | **`agenda`** | 区别于已有月历 `calendar` |

## 4. 架构总览

```
build_render_state(now)
  └─ EventStore(cfg.events_store).upcoming(now, AGENDA_LIMIT)
       → state["events"] = [{"id","title","date","time"}, ...]  # date≥今天, 升序

render: placement(widget="agenda")
  └─ _agenda 适配器 → draw_agenda(d, z, state["events"], state["now"])

网页 /config 日程卡片 ──(增/删)──> /api/events* ──> EventStore
```

设计要点:存储/过滤/排序在 `EventStore`;widget 为纯函数(注入事件 + `now`),`now` 仅用于算"今天/明天"相对标签,测试确定性。

### 模块划分(单一职责)
- `collectors/events.py`(新增):`EventStore` —— events.json 读写 + add/delete/list + upcoming。
- `config.py`(改):新增 `events_store` 路径字段 + sources 覆盖。
- `state.py`(改):`HubState` 持 `EventStore`;`build_render_state` 注入 `events`。
- `render/widgets.py`(改):新增 `draw_agenda`。
- `render/registry.py`(改):注册 `agenda` widget + 适配器。
- `server.py`(改):`/api/events` 系列端点。
- `web/config.html`(改):日程卡片。

## 5. 数据模型

### 5.1 存储(`~/inkpulse/events.json`)
裸 JSON 列表(仿 `todos.json`),每条:
```jsonc
[{"id": "a1b2c3d4", "title": "团队周会", "date": "2026-06-14", "time": "14:30"},
 {"id": "...",        "title": "交报告",   "date": "2026-06-14", "time": ""}]   // time="" = 全天
```
- `id`:`uuid4().hex[:8]`(同 `TodoStore`)。
- 文件不存在/损坏(非列表/JSON 错)→ 视为空 `[]`,不抛异常。

### 5.2 `EventStore`(`collectors/events.py`)
```python
AGENDA_LIMIT = 8   # state 注入上限(widget 再按高度截断)

class EventStore:
    def __init__(self, path): ...
    def list(self) -> list[dict]:          # 全部, 按 (date, time) 升序; time="" 视为最早("00:00"前)
    def add(self, title, date, time="") -> dict:   # 追加, 返回新条目; 调用方已校验
    def delete(self, eid) -> None
    def upcoming(self, now, limit) -> list[dict]:  # date >= 今天(由 now 求) 的, 升序, 取前 limit
```
- 排序键:`(date, time or "00:00")` —— 全天事件(`time=""`)排在当天定时事件之前。
- `今天` 由 `now`(unix 秒)经 `date.fromtimestamp(now).isoformat()` 求;`upcoming` 保留 `date >= 今天` 的条目。

## 6. 屏上 widget(`draw_agenda`)

```
┌ 日程 ──────────────────┐
│ 今天 14:30  团队周会         │
│ 今天 全天   交报告           │
│ 明天 09:00  体检             │
│ 6/18 周三 19:00 看演出       │
└───────────────────────┘
```
- 顶部 `_title_bar("日程")`。
- `events` 为空 → 居中提示「无日程 · 去网页添加」,return。
- 每行:**相对日标签** + 时间 + 标题:
  - 相对日:`date==今天`→「今天」;`==明天`→「明天」;否则「`M/D 周X`」(周X 用 `_WEEKDAYS`)。
  - 时间:`time` 非空→`time`(如 `14:30`);空→「全天」。
  - 标题:超长按宽度截断(同 `draw_todos`)。
- 按 `zone.h` 估算可容纳行数,`events[:N]` 截断。
- 纯黑,无红。
- 签名:`draw_agenda(d, z, events, now)`,`events=[{"title","date","time"}, ...]` 已升序。

## 7. API(`server.py`)

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/events` | 返回全部日程(`list()`,升序),供网页渲染 |
| POST | `/api/events` | body `{title,date,time}`;`title` 空白 → 400;`date` 非 `YYYY-MM-DD` → 400;`time` 非空且非 `HH:MM` → 400 |
| DELETE | `/api/events/{id}` | 删除该日程 |

- 校验:`date` 用 `datetime.date.fromisoformat` 解析失败 → 400;`time` 非空时用 `datetime.time.fromisoformat`(或正则 `HH:MM`)校验失败 → 400。
- 增删后网页刷新本卡片 + 调 `refreshPreview()`(沿用现有模式)。

## 8. 网页 `/config` 日程卡片

- 列出每条日程:`日期 时间  标题  ×`(`×` 删除)。按 `GET /api/events` 顺序。
- 录入行:标题输入框 + `<input type=date>` + `<input type=time>`(可留空)+「添加」。
- 添加/删除后刷新本卡片 + `refreshPreview()`。

## 9. 错误处理

- events.json 不存在/损坏 → 当空 `[]`,不崩。
- POST 空标题 / 坏日期 / 坏时间 → 400。
- `events` 为空 → widget「无日程 · 去网页添加」。
- 单 widget 异常仍由引擎 per-widget 隔离画 `n/a`。

## 10. 测试计划(pytest)

- `EventStore`:add/list/delete;`list` 按 (date,time) 升序、全天排当天之前;`upcoming` 过滤过期(date<今天)并取前 limit;损坏文件当空;持久化跨实例。
- `state`:`build_render_state` 含 `events`(list)。
- `draw_agenda`:有数据画黑像素;空 → 提示不崩;今天/明天/日期标签与"全天"分支均不崩;长标题截断不崩。
- API:GET 结构;POST 加 / 空标题拒 / 坏日期拒 / 坏时间拒;DELETE。
- `registry`:`agenda` 已注册,注入 state 下绘制不抛错。

## 11. 新增依赖

无。复用现有 Pillow / 标准库(`datetime`/`uuid`/`json`)。

## 12. 验收标准

1. 网页能新增/删除日程(标题+日期+可选时间);屏上 `agenda` widget 按时间排出近期日程,相对日标签 + 时间/全天 + 标题,过期自动隐去。
2. 无日程/坏文件不崩;坏日期/坏时间/空标题被 API 拒。
3. 全部测试通过。
