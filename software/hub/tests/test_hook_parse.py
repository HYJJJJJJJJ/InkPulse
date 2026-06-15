import json
import subprocess
import sys
import textwrap

# 与 hooks/inkpulse_agent_tasks.sh 内嵌的 python 解析等价的独立脚本(单一真相: 见实现步骤,
# 二者必须一致)。本测试直接执行该解析脚本, 喂样例 stdin, 断言输出 JSON body。
# 注意: 下方 PARSE 的四行核心解析(todos/tasks/project/json.dumps)必须与
# hooks/inkpulse_agent_tasks.sh 内嵌的对应四行逐字节一致, 任一处修改务必同步另一处。
PARSE = textwrap.dedent(r'''
import sys, json, os
d = json.load(sys.stdin)
todos = (d.get("tool_input") or {}).get("todos") or []
tasks = [{"content": t.get("content",""), "status": t.get("status","pending")}
         for t in todos if t.get("content")]
project = os.path.basename((d.get("cwd") or "").rstrip("/")) or "?"
print(json.dumps({"project": project, "tasks": tasks}, ensure_ascii=False))
''')


def _run(stdin_obj):
    r = subprocess.run([sys.executable, "-c", PARSE],
                       input=json.dumps(stdin_obj), capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_parse_extracts_tasks_and_project():
    out = _run({"cwd": "/home/u/work/InkPulse",
                "tool_input": {"todos": [
                    {"content": "写端点", "status": "in_progress"},
                    {"content": "做 widget", "status": "pending"},
                    {"content": "", "status": "pending"}]}})
    assert out["project"] == "InkPulse"
    assert [t["content"] for t in out["tasks"]] == ["写端点", "做 widget"]


def test_parse_empty_todos():
    out = _run({"cwd": "/x/y", "tool_input": {"todos": []}})
    assert out == {"project": "y", "tasks": []}
