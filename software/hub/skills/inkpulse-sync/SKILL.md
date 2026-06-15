---
name: inkpulse-sync
description: 用户想把当前会话的"工作焦点/关键行动项"推到 InkPulse 墨水屏时使用。提炼 2~5 条简短中文要点并上报 hub。
---

# inkpulse-sync

当用户调用本 skill 时:

1. 回顾当前会话与代码上下文,提炼出 **2~5 条**简短中文"工作焦点/持久行动项"(比如"给 parse 加边界测试""等 CI 通过后合并")。每条尽量短(≤20 字),只留真正值得在屏上长期提醒的。
2. 取当前项目名:`basename "$PWD"`。
3. 用 `curl` POST 到 hub 的 `/ingest/agent-tasks`,只带 `highlights`(不要带 `tasks`,以免覆盖 TodoWrite 的实时镜像):

   ```bash
   HUB="${INKPULSE_HUB:-http://127.0.0.1:8080}"
   curl -s -m 3 -X POST "$HUB/ingest/agent-tasks" \
     -H 'Content-Type: application/json' \
     -d "$(python3 -c 'import json,os,sys; print(json.dumps({"project":os.path.basename(os.getcwd()),"highlights":sys.argv[1:]}, ensure_ascii=False))' "焦点1" "焦点2")"
   ```
   把 `"焦点1" "焦点2"` 换成你提炼的要点(每条作为一个参数)。
4. 告诉用户已推送了哪几条焦点。

注意:hub 不可达时 curl 会失败,如实告知即可,不要重试纠缠。
