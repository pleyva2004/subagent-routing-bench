"""Which single slip explains a wrong code-trace answer?

Replays a trace program with one statement changed at a time (skipped, its if/else branch flipped,
or its tuple swap applied sequentially) and reports any change that reproduces a wrong answer
recorded in results.jsonl. Used for the 600-statement trace (trace-L8) in the paper.

Usage: python3 slip_search.py [task-id]   (default trace-L8)
"""
from __future__ import annotations

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def statements(code: str) -> list[str]:
    """Top-level statements; an if/else block counts as one."""
    out: list[str] = []
    cur: list[str] = []
    for line in code.split("\n"):
        if not line.startswith((" ", "else:")) and cur:
            out.append("\n".join(cur))
            cur = []
        cur.append(line)
    out.append("\n".join(cur))
    return out


def flip(s: str) -> str | None:
    m = re.match(r"if (.*):\n    (.*)\nelse:\n    (.*)", s)
    return f"if not ({m.group(1)}):\n    {m.group(2)}\nelse:\n    {m.group(3)}" if m else None


def sequential_swap(s: str) -> str | None:
    m = re.match(r"^(\w), (\w) = (\w), (\w)$", s)
    return f"{m.group(1)} = {m.group(3)}\n{m.group(2)} = {m.group(4)}" if m else None


def final_state(compiled: list, changed_index: int = -1, replacement: str | None = None) -> str:
    env: dict[str, int] = {}
    for i, code in enumerate(compiled):
        if i == changed_index:
            if replacement:
                exec(replacement, {}, env)
        else:
            exec(code, {}, env)
    return ",".join(str(env[v]) for v in "abcd")


def main() -> None:
    task_id = sys.argv[1] if len(sys.argv) > 1 else "trace-L8"
    tasks = {t["id"]: t for f in ("tasks.json", "tasks2.json") for t in json.load(open(os.path.join(HERE, f)))}
    code = re.search(r"```python\n(.*?)\n```", tasks[task_id]["problem"], re.S).group(1)
    stmts = statements(code)
    compiled = [compile(s, "<stmt>", "exec") for s in stmts]
    print(f"{task_id}: {len(stmts) - 1} statements after the initial assignment; correct answer {final_state(compiled)}")
    wrong: dict[str, list[str]] = {}
    for line in open(os.path.join(HERE, "results.jsonl")):
        r = json.loads(line)
        if r["task"] == task_id and r["status"] == "wrong" and r.get("got"):
            wrong.setdefault(r["got"], []).append(f"{r['model'].split('-')[1]} {r['effort']}")
    for answer, configs in wrong.items():
        print(f"wrong answer {answer} from {', '.join(configs)}")
    hits = 0
    for i, s in enumerate(stmts[1:], start=1):
        for kind, alt in (("skipped", ""), ("branch flipped", flip(s)), ("swap applied sequentially", sequential_swap(s))):
            if alt is None:
                continue
            result = final_state(compiled, i, alt)
            if result in wrong:
                hits += 1
                print(f"  reproduces {result} ({', '.join(wrong[result])}): statement {i} {kind}: {s.replace(chr(10), ' | ')}")
    print(f"single slips that reproduce a wrong answer: {hits}")


if __name__ == "__main__":
    main()
