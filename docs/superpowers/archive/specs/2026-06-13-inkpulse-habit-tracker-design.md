# InkPulse 习惯打卡 widget(设计文档)

> 日期:2026-06-13 · 状态:已通过设计评审,待写实现计划
> 关联:网格布局系统(第一期,已归档 `docs/superpowers/archive/`)· 第二期只读 widget(已归档)

## 1. 背景与目标

第二期规划的本地数据 widget 中,「用量趋势 / 项目分布」已完成(只读、零新存储)。本设计做第二期需要**新存储 + 交互**的第一个:**习惯打卡**。

目标:在墨水屏上以"本周打卡墙"展示若干习惯的坚持情况;用户在网页 `/config` 里管理习惯并逐日打卡(可补打本周已过的日子)。设备屏只读显示,不在屏上操作。

## 2. 范围

### 本期做(In Scope)
- 习惯存储 `HabitStore`(`~/inkpulse/habits.json`):习惯列表 + 按日完成记录。
- 屏上 widget `draw_habits`:本周(周一~周日)打卡墙,注册为 `habits`。
- `state` 注入本周打卡数据(纯函数化,便于测试)。
- 网页 `/config` 新增「习惯打卡」卡片:增/删习惯 + 点格子打卡(本周任意已到日期,未来禁用)。
- 配套 API 与测试。

### 本期不做(Out of Scope / YAGNI)
- 习惯改名、拖拽排序。
- 连续天数 / 完成率统计(brainstorm 时的备选 C 未采纳)。
- 提醒 / 通知。
- 跨周历史视图(只展示本自然周)。
- 屏上直接打卡(墨水屏无逐项输入)。

## 3. 决策记录(brainstorm 结论)

| 决策点 | 选择 | 理由 |
|---|---|---|
| 显示形式 | **7 天打卡墙**(习惯×本周7天) | 最能体现"打卡"、一眼看连续性 |
| 7 天语义 | **本周(周一~周日)** | 表头 `一..日` 固定;今天列描边;未来留空 |
| 周起始 | **周一**(Mon=0) | 与现有月历 `firstweekday=0` 一致 |
| 打卡操作 | **网页可点本周任意已到日** | 可补打/纠错;未来日禁用 |
| 参数 | **v1 无参数** | 显示全部习惯,放不下就截;先简单 |

## 4. 架构总览

```
build_render_state(now)
  └─ HabitStore(cfg.habits_store).week_view(now)
       → state["habits"]   = [{"name": str, "days": [bool×7 周一→周日]}, ...]
       → state["habit_today_idx"] = 0..6   # 今天是本周第几列(周一=0)

render: placement(widget="habits")
  └─ _habits 适配器 → draw_habits(d, z, state["habits"], state["habit_today_idx"])

网页 /config「习惯打卡」卡片  ──(增删/打卡)──>  /api/habits*  ──>  HabitStore
```

设计要点:存储与"本周视图计算"放在 `HabitStore` / `state`,widget 与网页只消费结构化数据;widget 为纯函数(注入数据),测试确定性。

### 模块划分(单一职责)
- `collectors/habits.py`(新增):`HabitStore` —— habits.json 读写 + 打卡切换 + 本周视图。
- `config.py`(改):新增 `habits_store` 路径字段 + `sources.habits_store` 覆盖。
- `state.py`(改):`build_render_state` 注入 `habits` / `habit_today_idx`。
- `render/widgets.py`(改):新增 `draw_habits`。
- `render/registry.py`(改):注册 `habits` widget + 适配器。
- `server.py`(改):新增 `/api/habits` 系列端点。
- `web/config.html`(改):新增「习惯打卡」卡片。

## 5. 数据模型

### 5.1 存储(`~/inkpulse/habits.json`)
```jsonc
{
  "habits": [ {"id": "a1b2c3d4", "name": "运动"}, {"id": "...", "name": "阅读"} ],
  "log": { "2026-06-13": ["a1b2c3d4", "..."],   // 该日完成的习惯 id 列表
           "2026-06-12": ["a1b2c3d4"] }
}
```
- `id`:`uuid4().hex[:8]`(同 TodoStore)。
- `log` 按日期(本地 `YYYY-MM-DD`)归集当天打卡的习惯 id。删除习惯时一并从各日 `log` 移除其 id。

### 5.2 `HabitStore`(`collectors/habits.py`)
```python
class HabitStore:
    def __init__(self, path): ...
    def list(self) -> list[dict]:                  # [{"id","name"}]
    def add(self, name) -> dict:                    # 追加, 返回新习惯
    def delete(self, hid) -> None:                  # 删习惯 + 清各日 log 里的该 id
    def toggle(self, hid, date_iso) -> None:        # 在 date_iso 切换该习惯打卡(增/删)
    def is_done(self, hid, date_iso) -> bool
    def week_view(self, now) -> tuple[list[dict], int]:
        # 返回 ([{"name","days":[bool×7 周一→周日]}, ...], today_idx)
```
- `date_iso` 形如 `"2026-06-13"`;空习惯列表时 `week_view` 返回 `([], today_idx)`。
- 文件不存在/损坏 → 视为空(`{"habits":[],"log":{}}`),不抛异常。

### 5.3 本周日期计算
- 周一为起点:`monday = today - timedelta(days=today.weekday())`;7 列为 `monday + i`(i=0..6)。
- `today_idx = today.weekday()`(周一=0 … 周日=6)。

## 6. 屏上 widget(`draw_habits`)

```
┌ 习惯打卡 ──────────┐
│        一 二 三 四 五 六 日 │
│ 运动   ■ ■ ■ [■] · · ·   │   [■]=今天列描边, ·=未来留空
│ 阅读   ■ □ ■ [□] · · ·   │   ■=打卡, □=已过未打
│ 喝水   ■ ■ ■ [■] · · ·   │
└──────────────────┘
```
- 顶部 `_title_bar("习惯打卡")`;其下一行星期表头 `一..日`(列与下方格对齐)。
- 每行:习惯名(左,超长截断)+ 7 个格子:
  - 列 `< today_idx` 或 `== today_idx`:`■`(已打卡,实心方块)/ `□`(未打,空心方块);
  - 列 `> today_idx`(未来):`·`(小点/留空,不可达)。
  - 今天列(`== today_idx`)在格子外描一圈细框强调。
- 字形使用确认存在的 `■`(U+25A0)/`□`(U+25A1)(思源黑已含);纯黑,无红。
- 习惯数超出可显示行数时按可容纳行数截断(同 `draw_todos` 的 `items[:N]` 思路,N 由 `zone.h` 估算)。
- 无习惯 → 居中提示「无习惯 · 去网页添加」。

签名:`draw_habits(d, z, habits, today_idx)`,`habits=[{"name","days":[bool×7]}]`。

## 7. API(`server.py`)

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/habits` | `{habits:[{id,name}], week:[7个 "YYYY-MM-DD"], done:{hid:[bool×7]}, today_idx}`:供网页渲染本周格 |
| POST | `/api/habits` | body `{name}`,新增习惯;空名返回 400 |
| DELETE | `/api/habits/{id}` | 删除该习惯(含清 log) |
| POST | `/api/habits/{id}/toggle` | body `{date}`,切换该习惯在 date 的打卡;**date 晚于今天 → 400**;未知 id → 404 |

打卡后网页可调用现有 `/api/refresh` 让真机刷新(同待办/照片)。

## 8. 网页 `/config`「习惯打卡」卡片

- 列出每个习惯:`名字  [一][二][三][四][五][六][日]  ×`
  - 7 个格子按 `done` 矩阵着色;**今天及之前可点**(toggle),**未来禁用置灰**;
  - `×` 删除习惯。
- 底部:输入框 + 「添加」按钮新增习惯。
- 打卡/增删后刷新本卡片 + 调 `refreshPreview()`(沿用现有模式)。

## 9. 错误处理

- habits.json 不存在/损坏 → 当空处理,不崩。
- toggle 未知习惯 id → 404;未来日期 → 400。
- 新增空白名 → 400。
- widget:`habits` 为空 → "无习惯 · 去网页添加";单 widget 异常仍由引擎 per-widget 隔离画 `n/a`。

## 10. 测试计划(pytest)

- `HabitStore`:add/list/delete(含从 log 清 id)、toggle 增删往返、is_done、损坏文件当空、`week_view` 结构与 today_idx、空习惯返回 `([], idx)`。
- `state`:`build_render_state` 含 `habits`(list)与 `habit_today_idx`(0..6)。
- `draw_habits`:有数据画黑格;空习惯画提示不崩;未来列不画实心格;今天列有描边。
- API 契约:GET 结构;POST 加/空名拒;DELETE;toggle 正常 / 拒未来 / 未知 id 404。
- registry:`habits` 已注册,注入 state 下绘制不抛错。

## 11. 新增依赖

无。复用现有 Pillow / 标准库。

## 12. 验收标准

1. 网页能新增/删除习惯,并点本周任意已到日期格子打卡(未来禁用)。
2. 屏上 `habits` widget 显示本周打卡墙,今天列描边、未来留空,数据与网页一致。
3. 无习惯/坏文件不崩;toggle 未来日期被拒。
4. 全部测试通过。
