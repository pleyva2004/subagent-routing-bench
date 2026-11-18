"""Merge pilot + sweep results: task x config grid, then per-config totals (all 10 model/effort configs)."""
from __future__ import annotations

import json
import sys
from collections import defaultdict

latest: dict[tuple, dict] = {}
for path in sys.argv[1:]:  # later files override earlier ones (reruns)
    for line in open(path):
        r = json.loads(line)
        latest[(r["task"], r["model"], r["effort"], r["trial"])] = r
rows = list(latest.values())
EFF = ["low", "medium", "high", "xhigh", "max"]
cfgs = [f"{m}:{e}" for m in ("haiku", "sonnet") for e in EFF]
cfgs = [c for c in cfgs if any(f"{r['model']}:{r['effort']}" == c for r in rows)]
order = {"locate": 0, "fix": 1, "feature": 2, "review": 3}
tasks = sorted({r["task"] for r in rows}, key=lambda t: (order[t.split("-")[0]], t))
cell = {(r["task"], f"{r['model']}:{r['effort']}"): r for r in rows}

short = {c: c.replace("haiku:", "H-").replace("sonnet:", "S-").replace("medium", "med") for c in cfgs}
print(f"{'task':20}" + "".join(f"{short[c]:>9}" for c in cfgs))
for t in tasks:
    marks = []
    for c in cfgs:
        r = cell.get((t, c))
        marks.append("." if r is None else {"pass": "✓", "fail": "✗"}.get(r["status"], r["status"][:4]))
    print(f"{t:20}" + "".join(f"{m:>9}" for m in marks))

print(f"\n{'config':14} {'pass':>6} {'locate':>7} {'fix':>4} {'feature':>8} {'review':>7} {'out_tok':>9} {'in_tok':>11} {'agent_s':>8} {'false_claims':>13}")
for c in cfgs:
    rs = [r for r in rows if f"{r['model']}:{r['effort']}" == c]
    by = defaultdict(lambda: [0, 0])
    for r in rs:
        by[r["type"]][0] += r["status"] == "pass"
        by[r["type"]][1] += 1
    out = sum(r.get("out") or 0 for r in rs)
    inp = sum(sum(r.get(k) or 0 for k in ("in", "cache_write", "cache_read")) for r in rs)
    secs = sum(round((r.get("turn_ms") or 0) / 1000) for r in rs)
    fc = sum(bool(r.get("false_success_claim")) for r in rs)
    p = sum(r["status"] == "pass" for r in rs)
    f = lambda t: f"{by[t][0]}/{by[t][1]}"
    print(f"{c:14} {p:>3}/{len(rs):<2} {f('locate'):>7} {f('fix'):>4} {f('feature'):>8} {f('review'):>7} "
          f"{out:>9,} {inp:>11,} {secs:>8} {fc:>13}")

print("\nNon-pass detail:")
for r in sorted(rows, key=lambda r: (r["task"], r["model"], EFF.index(r["effort"]))):
    if r["status"] == "pass":
        continue
    d = {k: r.get(k) for k in ("found", "planted", "extra_reports", "failures", "failing", "must_pass_missing",
                               "missed", "extra", "err") if r.get(k) not in (None, [], "")}
    print(f"  {r['task']:20} {r['model']}:{r['effort']:7} {r['status']:15} {json.dumps(d)[:220]}")
