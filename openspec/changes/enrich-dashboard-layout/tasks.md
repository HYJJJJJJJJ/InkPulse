## 1. 依赖与农历(state 层)

- [x] 1.1 `software/hub/pyproject.toml` dependencies 加 `cnlunar`,在 hub 目录 `pip install -e .` 安装
- [x] 1.2 写一个临时 spike(脚本或 REPL)确认 cnlunar API:如何取农历日期、生肖年、节气、节日;记录字段/方法名(用完删除,不进库)
- [x] 1.3 `state.py:_clock` 改为完整格式 `f"{year}-{mon:02d}-{mday:02d} {h:02d}:{m:02d} {weekday}"` → `2026-06-12 11:23 周四`
- [x] 1.4 `state.py` 加 `_lunar(now)`:用 cnlunar 组装"农历日期 · 生肖年 · 节气[ · 节日]",缺失段省略不留空分隔;返回 `(text, is_festival)` 或文本+节日名,供渲染判断标红
- [x] 1.5 `build_render_state` 增加 `lunar` 字段(及节日标记)进 state dict
- [x] 1.6 测试:给定固定日期(普通日 / 含节气 / 节日各一例)断言 `_clock` 与 `_lunar` 输出字符串与节日标记

## 2. 头部渲染(header 两行 + 红日期 + 农历)

- [x] 2.1 `engine.py:ZONES` 把 `header_clock_env` 高度 60→约 76;`claude_status`/`usage`/`todos` 的 y 起点与高度顺移,保持总高 480、各区不重叠
- [x] 2.2 `widgets.py:draw_header` 改两行:第一行日期(红强调)+ 温湿度(黑,沿用有效区间逻辑);第二行农历(黑,节日名标红)
- [x] 2.3 测试:渲染头部,断言含完整日期串、农历串;节日用例断言出现红像素(节日名处)

## 3. 分区标题栏 + 状态区丰富化

- [x] 3.1 `widgets.py` 加内部 helper `_title_bar(d, z, text)`:画黑色填充矩形 + 白字,供各区复用(黑底白字,不用红)
- [x] 3.2 `draw_claude_status`:加"状态"标题栏;露出 `since` → "已 N 分钟/小时";保留 needs_attention 时状态块+标签转红
- [x] 3.3 测试:`working` 态断言状态区无红(除标题栏黑底);`waiting_for_input`/`error` 断言状态块红;`since` 给定值断言显示持续时长文案

## 4. 用量区丰富化(hero 数字 + 会话数 + 窗口%)

- [x] 4.1 `config.py` + `config.example.yaml` 加可选 `usage.budget_usd`(默认 None);`load_config` 解析
- [x] 4.2 `draw_usage`:加"今日用量"标题栏;花费做成放大 hero 数字,`budget_usd` 设了且 `cost_usd>budget_usd` 才红、否则黑;窗口条旁加百分比数字,`window_used_ratio>0.90` 时百分比红;露出 `session_count` → "今日 N 会话"
- [x] 4.3 测试:未配 budget→花费黑;配了且超→花费红;窗口 0.86→显示 86% 黑、0.95→红;session_count 显示

## 5. 待办区丰富化(真复选框 + 删除线)

- [x] 5.1 `draw_todos`:加"待办"标题栏;`[x]/[ ]` → ☑/☐ 字形;`done` 项文本加删除线弱化
- [x] 5.2 测试:done 项断言 ☑ 且有删除线像素特征,未 done 断言 ☐

## 6. 量化契约回归 + 预览核对

- [x] 6.1 测试:渲染整帧后断言像素集合 ⊆ {白,黑,红}、红字为纯(255,0,0)、`pack_frame` 仍 96000 字节(三色量化不变)
- [x] 6.2 跑全量 `pytest -q` 确保既有用例 + 新增用例全绿
- [x] 6.3 重启 Hub,浏览器开 `/preview.png` 逐项肉眼核对:完整日期、农历行、各分区标题栏、hero 数字、会话数、窗口%、真复选框;红仅出现在日期/告警处
- [ ] 6.4 (可选,有真机时)烧录无关、仅设备拉帧:复位设备或等刷新,真屏确认布局与残影可接受

## 7. 收尾

- [x] 7.1 更新 `software/hub/README.md` 渲染/widget 说明(新头部、农历、红色规则、budget_usd 配置)
- [x] 7.2 commit(分组提交;署名 zengqx <zengqx1996@gmail.com>;不加 Co-Authored-By/AI 署名)
