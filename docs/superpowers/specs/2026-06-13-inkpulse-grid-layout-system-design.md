# InkPulse 数据驱动网格布局系统(设计文档)

> 日期:2026-06-13 · 状态:已通过设计评审,待写实现计划
> 关联:[显示系统设计](2026-06-09-inkpulse-display-system-design.md) · [固件分层架构](2026-06-12-inkpulse-firmware-layered-arch-design.md)

## 1. 背景与目标

当前 Hub 的布局是 6 个写死的 Python 函数(`dash/photo/usage/todo/clock/split`),分区坐标硬编码在各函数里(仅 `dash` 读 `cfg.layout` 配合固定 `ZONES`)。"自定义布局"=网页里选 1 个预设;改布局必须改代码,加功能要同时碰布局逻辑。

**目标(提高自由度)**:把布局从代码变成**数据**,让用户在网页里把屏幕切成网格、往格子里放任意 widget、存成自己命名的布局;同时让"加新功能"退化成"加一个 widget 函数 + 注册一行"。

本设计是**第一期(地基)**,只做布局引擎本身 + 编辑器 + 2 个验证 widget。后续两期(见 §9)在此之上增量加 widget。

## 2. 范围

### 本期做(In Scope)
- 数据驱动**网格渲染引擎**(固定网格 + 矩形跨格,模型 B)。
- **Widget 注册表**:统一签名 + 元数据(默认跨度、参数 schema),把现有 8 个 widget 适配进来。
- 布局以 **JSON** 存储(`layouts.json`):命名布局 = placements 列表。
- **网页网格编辑器**("点格子选 widget"版):框选矩形 → 选 widget → 填参数 → 保存命名布局;布局切换/新建/删除;复用现有实时预览。
- 把现有 **6 个预设迁移**成 `builtin` 布局(像素位置尽量还原,从此可编辑、不可删)。
- **2 个验证 widget**:`countdown`(倒计时/纪念日)、`qrcode`(二维码)——纯本地、零新数据管线。
- 配套 **API** 与 **测试**。

### 本期不做(Out of Scope / YAGNI)
- 鼠标拖拽缩放编辑(本期只"点格子",拖拽留后续)。
- L4 像素级自由画布。
- 第二/三期的 7 个 widget(天气、日程、行情、用量趋势、项目分布、习惯打卡、温湿度曲线)。
- 布局导入/导出/分享。

## 3. 决策记录(brainstorm 结论)

| 决策点 | 选择 | 理由 |
|---|---|---|
| 自由度档位 | **L3 网格自定义** | 布局变数据,自由度大涨而复杂度可控 |
| 网格模型 | **B 固定网格 + 跨格** | 像 CSS Grid,墨水屏上随意摆又自动对齐,编辑器好做 |
| 第一期范围 | **地基 + 2 极简 widget** | 先把引擎跑通,不被数据采集拖住 |
| 编辑器程度 | **点格子选 widget** | 够用、好实现;拖拽留后续 |
| 默认网格 | **8 列 × 6 行**(格子 100×80px) | 800×480 整除,48 格易点选,跨格仍灵活;数值可配 |

## 4. 架构总览

```
render_frame(cfg, state)
  └─ load_layout(cfg.layout_name)         # 读 layouts.json → Layout(grid, placements)
       └─ for placement in placements:
            zone = cell_to_zone(grid, placement)   # 网格坐标 → 像素 Zone
            spec = REGISTRY[placement.widget]       # 注册表查 widget
            spec.draw(d, zone, state, cfg, placement.params)   # 单 widget 隔离容错
```

设计要点:现有 widget 函数已统一接收 `Zone`,因此本改造**复用全部现有 widget**,改动集中在引擎与新增的注册表/布局存储/编辑器。

### 模块划分(每个单元单一职责)
- `render/registry.py`(新增):`WidgetSpec` 数据类 + `REGISTRY` 字典 + 现有 widget 的薄适配器。依赖 `widgets.py`。
- `render/grid.py`(新增):`cell_to_zone()` 网格→像素换算;`Layout`/`Placement` 数据类。无副作用、纯函数,易测。
- `layouts.py`(新增):`layouts.json` 的加载/保存/迁移/校验。依赖 `grid.py`。
- `render/engine.py`(改):`render_frame` 改走数据驱动路径;退役 6 个 `draw_xxx`(逻辑转为 builtin 布局数据)。
- `render/widgets.py`(改):新增 `draw_countdown`、`draw_qrcode`。
- `server.py`(改):新增 `/api/layouts` 系列端点。
- `web/config.html`(改):新增网格编辑器区。

## 5. 数据模型

### 5.1 Widget 注册表(`render/registry.py`)
```python
@dataclass
class WidgetSpec:
    name: str                       # 唯一 key,如 "countdown"
    label: str                      # 中文显示名,如 "倒计时"
    draw: Callable                  # fn(d, zone, state, cfg, params) -> None
    default_span: dict              # {"cols": 3, "rows": 2} 拖入时默认大小
    params: list[dict]              # [{"key","label","type","default"}],编辑器据此生成表单

REGISTRY: dict[str, WidgetSpec]     # name -> spec
```
- 现有 widget 各写一个适配器把旧签名包成统一签名后登记:
  `header / claude_status / usage / usage_ring / todos / big_clock / month_calendar / photo`。
- `params` 的 `type` 第一期支持:`text`、`date`、`number`。

### 5.2 布局存储(`~/inkpulse/layouts.json`)
```jsonc
{
  "version": 1,
  "grid": {"cols": 8, "rows": 6},
  "layouts": {
    "dash": {
      "builtin": true,
      "placements": [
        {"widget": "header",        "col": 0, "row": 0, "colspan": 8, "rowspan": 1, "params": {}},
        {"widget": "claude_status", "col": 0, "row": 1, "colspan": 4, "rowspan": 3, "params": {}},
        {"widget": "usage",         "col": 4, "row": 1, "colspan": 4, "rowspan": 3, "params": {}},
        {"widget": "todos",         "col": 0, "row": 4, "colspan": 8, "rowspan": 2, "params": {}}
      ]
    },
    "我的桌面": { "placements": [ /* 用户自建,无 builtin 标记 */ ] }
  }
}
```
- `runtime.json` 的 `layout_name` 指向 `layouts` 的某个 key(沿用现有机制;`config.py` 的 `RUNTIME_FIELDS` 不变)。
- `grid` 全局一份(本期不做"每布局不同网格")。
- 文件不存在时由迁移逻辑生成(含 6 个 builtin)。

### 5.3 网格→像素换算(`render/grid.py`)
- `cell_w = WIDTH / cols`,`cell_h = HEIGHT / rows`(WIDTH=800, HEIGHT=480)。
- `cell_to_zone(grid, p)` → `Zone(round(p.col*cell_w), round(p.row*cell_h), round(p.colspan*cell_w), round(p.rowspan*cell_h))`。
- 边界用 round 累计,保证铺满不留缝;**gutter=0**(墨水屏避免多余分隔线,由 widget 自身决定是否画边框)。

## 6. 网页编辑器(`config.html` 新增区)

交互(点格子版):
1. 选/新建布局 → 画布(8×6)渲染其 placements。
2. 点一个格子=矩形起点,再点另一格=终点 → 黄色高亮选中区。
3. 右侧:widget 下拉(来自 `/api/layouts` 的 widget 目录)+ 按 `params` schema 自动生成的参数输入框 → "放入选中区域"。
4. 删除:点已有 widget → 删;移动/改尺寸:重新框选覆盖。
5. "保存布局" → `PUT /api/layouts/{name}`;切到该布局后点现有「刷新屏幕」即下发设备。
6. 下方复用现有 `/preview.png` 实时预览。

builtin 布局:可选中、可"另存为"副本编辑,不可直接删除/覆盖(UI 禁用删除按钮)。

## 7. API(`server.py`)

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/layouts` | `{grid, layouts, widgets}`:全部布局 + 网格 + widget 目录(label/default_span/params schema) |
| PUT | `/api/layouts/{name}` | 新建/更新布局的 placements;body 校验 widget 存在、坐标在网格内 |
| DELETE | `/api/layouts/{name}` | 删除;`builtin` 返回 400 |

现有 `POST /api/config {layout_name}`、`POST /api/refresh`、`/preview.png` 不变。

## 8. 错误处理(沿用现有 per-widget 隔离原则)

- **未知 widget / 参数缺失**:该格画 `n/a` 占位框,不崩整帧。
- **布局文件损坏 / 空 / layout_name 不存在**:回退 `dash`,日志告警。
- **placements 越界**(超出 grid):加载时 clamp 到网格内 + 日志。
- **重叠区域**:编辑器阻止重叠落子;引擎按 placements 顺序渲染,后者覆盖前者(不报错)。
- **PUT 校验失败**:返回 400 + 原因,不写文件。

## 9. 后续分期(非本期,记录方向)

- **第二期(Claude 增强 + 本地批)**:用量趋势(近7天柱状)、项目分布(今日各项目占比)、习惯打卡、温湿度曲线(sparkline,注:本机湿度通道损坏,仅温度有效)。数据本地已有/好采,无外部 API 风险。
- **第三期(联网批)**:天气预报、今日日程(Google Calendar/ICS)、行情/自定义数值。共用"外部采集器 + 缓存 + 失败回退 n/a"一套模式。
- 每个 widget 落地 = 写 `draw_xxx` + 注册一行(+ 需要时加采集器),不动布局引擎——这正是本期地基的价值。

## 10. 测试计划(pytest,沿用现有风格)

- `grid.cell_to_zone`:各种 col/row/span 的像素换算,边界铺满不留缝。
- `layouts.json` 读写往返;迁移逻辑产出 6 个 builtin 且能渲染。
- 注册表查找;未知 widget 返回 None。
- 数据驱动 `render_frame`:用一个自定义布局渲染出非空帧。
- 单 widget draw 抛错 → 画 n/a、其余 widget 正常(隔离容错)。
- `draw_countdown`(日期差计算 + 文案)、`draw_qrcode`(纯黑白、可解码)输出正确。
- API 契约:GET 返回结构、PUT 校验(越界/未知 widget 拒绝)、DELETE 拒删 builtin。

## 11. 新增依赖

- `qrcode`(纯 Python,生成二维码 PIL 图像)。其余复用现有 Pillow/FastAPI 栈。

## 12. 验收标准

1. 网页里能新建一个布局、框选区域放入 widget(含 countdown/qrcode 并填参数)、保存、切换、在设备/预览上看到效果。
2. 原 6 个预设作为 builtin 仍可用、外观与现状基本一致、且可"另存为"后编辑。
3. 任一 widget 出错只影响该格,整帧仍出图。
4. 全部测试通过。
