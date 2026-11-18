"""Run (model, effort, family) chains through claude-pane.sh launch/collect; append results to results.jsonl.

Each chain climbs its family's levels in order and stops after two consecutive non-passes,
counting the streak already present in earlier results.
"""
from __future__ import annotations

import glob
import json
import os
import re
import subprocess
import sys
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from typing import Any

H = os.path.expanduser("~/.claude/skills/cmux-subagent/claude-pane.sh")
MODELS = ["claude-haiku-5-5", "claude-sonnet-5-5"]
EFFORTS = ["low", "medium", "high", "xhigh"]
PREAMBLE = (
    "This is a benchmark of unaided reasoning. Solve the problem below in your head. "
    "Do NOT use any tools: no Bash, no code execution, no file reads or writes, no sub-agents, no web. "
    "Do not ask questions. End your reply with one final line exactly in the form `ANSWER: <answer>`.\n\n"
)
lock = threading.Lock()


def norm(fam: str, s: str) -> str:
    if fam == "mult":
        return re.sub(r"[^0-9]", "", s)
    if fam == "trace":
        return ",".join(re.findall(r"-?\d+", s))
    return ",".join(w.capitalize() for w in re.findall(r"[A-Za-z]+", s))


def transcript_stats(sid: str) -> dict[str, Any]:
    paths = glob.glob(os.path.expanduser(f"~/.claude/projects/*/{sid}.jsonl"))
    out = {"tool_uses": 0, "output_tokens": 0, "duration_ms": None}
    if not paths:
        return out
    seen: dict[str, int] = {}
    for line in open(paths[0], errors="replace"):
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("type") == "assistant":
            m = e.get("message", {})
            for b in m.get("content", []) or []:
                if isinstance(b, dict) and b.get("type") == "tool_use":
                    out["tool_uses"] += 1
            u = (m.get("usage") or {}).get("output_tokens")
            if u is not None:
                seen[m.get("id", "")] = max(seen.get(m.get("id", ""), 0), u)
        if e.get("type") == "system" and e.get("subtype") == "turn_duration":
            out["duration_ms"] = e.get("durationMs")
    out["output_tokens"] = sum(seen.values())
    return out


def record(rec: dict[str, Any], res_path: str) -> None:
    with lock:
        with open(res_path, "a") as f:
            f.write(json.dumps(rec) + "\n")
        print(f"{rec['model'][7:13]:6} {rec['effort']:6} {rec['task']:9} {rec['status']}", flush=True)


def run_one(model: str, effort: str, t: dict[str, Any], res_path: str, timeout: int) -> str:
    t0 = time.time()
    p = subprocess.run([H, "launch", model, PREAMBLE + t["problem"], "--effort", effort], capture_output=True, text=True)
    rec: dict[str, Any] = {"model": model, "effort": effort, "task": t["id"], "family": t["family"], "level": t["level"]}
    if p.returncode != 0:
        rec.update(status="launch_fail", err=p.stderr[-300:])
    else:
        handle = p.stdout.strip()
        sid = handle.split("@", 1)[1]
        c = subprocess.run([H, "collect", handle, str(timeout)], capture_output=True, text=True)
        m = re.findall(r"ANSWER:\s*`?([^\n`]*)", c.stdout)
        got = norm(t["family"], m[-1]) if m else ""
        st = transcript_stats(sid)
        if c.returncode != 0:
            status = "timeout_or_err"
        elif st["tool_uses"]:
            status = "tool_violation"
        elif not m:
            status = "no_answer"
        elif got == t["answer"]:
            status = "pass"
        else:
            status = "wrong"
        rec.update(status=status, rc=c.returncode, got=got[:80], want=t["answer"][:80],
                   wall_s=round(time.time() - t0, 1), sid=sid, **st)
    record(rec, res_path)
    return rec["status"]


def chain(model: str, effort: str, ft: list[dict[str, Any]], streak: int,
          prior: dict[tuple, dict[str, Any]], res_path: str, timeout: int) -> None:
    for t in ft:
        r = prior.get((model, effort, t["id"]))
        if r:
            status = r["status"]
        elif streak >= 2:
            status = "skipped"
            record({"model": model, "effort": effort, "task": t["id"], "family": t["family"],
                    "level": t["level"], "status": status}, res_path)
        else:
            status = run_one(model, effort, t, res_path, timeout)
        streak = 0 if status == "pass" else streak + 1


def main() -> None:
    tasks = json.load(open(sys.argv[1]))
    res_path, workers, timeout = sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
    prior: dict[tuple, dict[str, Any]] = {}
    if os.path.exists(res_path):
        for line in open(res_path):
            r = json.loads(line)
            if r["status"] != "launch_fail":
                prior[(r["model"], r["effort"], r["task"])] = r
    chains = []
    for fam in ["trace", "mult", "logic"]:  # slowest family first, for load balance
        ft = sorted((t for t in tasks if t["family"] == fam), key=lambda t: t["level"])
        if not ft:
            continue
        for e in reversed(EFFORTS):
            for m in reversed(MODELS):
                lower = sorted((r for r in prior.values() if r["model"] == m and r["effort"] == e
                                and r["family"] == fam and r["level"] < ft[0]["level"]), key=lambda r: r["level"])
                streak = 0
                for r in lower:
                    streak = 0 if r["status"] == "pass" else streak + 1
                chains.append((m, e, ft, streak))
    print(f"{len(chains)} chains", flush=True)
    with ThreadPoolExecutor(workers) as ex:
        futs = []
        for i, (m, e, ft, streak) in enumerate(chains):
            futs.append(ex.submit(chain, m, e, ft, streak, prior, res_path, timeout))
            if i < workers:
                time.sleep(1.5)  # stagger the first launches so panes register before the next split
        for f in futs:
            try:
                f.result()
            except Exception:
                traceback.print_exc()


if __name__ == "__main__":
    main()
