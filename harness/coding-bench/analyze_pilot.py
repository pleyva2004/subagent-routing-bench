"""Summarize a coding-benchmark results file: per-run detail, then per-config totals."""
from __future__ import annotations

import json
import sys
from collections import defaultdict

rows = [json.loads(line) for line in open(sys.argv[1])]
order = {t: i for i, t in enumerate(["locate", "fix", "feature", "review"])}
rows.sort(key=lambda r: (order.get(r["type"], 9), r["task"], r["model"], r["effort"]))


def detail(r: dict) -> str:
    t = r["type"]
    if r["status"] in ("harness_error", "launch_fail"):
        return r.get("err", "")[:90]
    if t == "locate":
        return f"tp={r.get('tp')} fp={r.get('fp')} fn={r.get('fn')} extra={r.get('extra')} missed={r.get('missed')}"
    if t == "review":
        return f"found {r.get('found')}/{r.get('planted')} false_alarms={r.get('false_alarms')}"
    bits = [f"fails={r.get('failures')}"]
    if r.get("must_pass_missing"):
        bits.append(f"hidden_not_passing={len(r['must_pass_missing'])}")
    if r.get("outside_expected"):
        bits.append(f"extra_files={r['outside_expected']}")
    if r.get("test_files_touched"):
        bits.append(f"touched_tests={r['test_files_touched']}")
    if r.get("false_success_claim"):
        bits.append("FALSE_SUCCESS_CLAIM")
    return " ".join(bits)


def tok(r: dict) -> int:
    return sum(r.get(k) or 0 for k in ("in", "cache_write", "cache_read", "out"))


print(f"{'task':20} {'config':14} {'status':15} {'out_tok':>8} {'in_tok(all)':>11} {'tools':>5} {'deny':>4} {'turn_s':>6}  detail")
for r in rows:
    cfg = f"{r['model']}:{r['effort']}"
    turn = round((r.get("turn_ms") or 0) / 1000)
    print(f"{r['task']:20} {cfg:14} {r['status']:15} {r.get('out') or 0:>8} {tok(r) - (r.get('out') or 0):>11} "
          f"{r.get('tool_uses') or 0:>5} {r.get('denied') or 0:>4} {turn:>6}  {detail(r)}")

print("\nPer config:")
agg: dict[str, dict] = defaultdict(lambda: defaultdict(int))
for r in rows:
    a = agg[f"{r['model']}:{r['effort']}"]
    a["runs"] += 1
    a["pass"] += r["status"] == "pass"
    a["false_claims"] += bool(r.get("false_success_claim"))
    a["denied"] += r.get("denied") or 0
    a["out"] += r.get("out") or 0
    a["in_all"] += tok(r) - (r.get("out") or 0)
    a["turn_s"] += round((r.get("turn_ms") or 0) / 1000)
    a[f"pass_{r['type']}"] += r["status"] == "pass"
    a[f"n_{r['type']}"] += 1
for cfg, a in agg.items():
    by_type = " ".join(f"{t}={a[f'pass_{t}']}/{a[f'n_{t}']}" for t in order if a[f"n_{t}"])
    print(f"{cfg:14} pass {a['pass']}/{a['runs']} ({by_type})  false_claims={a['false_claims']} denied={a['denied']} "
          f"out_tok={a['out']:,} input_tok={a['in_all']:,} agent_time={a['turn_s']}s")
