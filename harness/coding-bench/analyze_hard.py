"""Hard-task results with trials: pass rate per task x config, then per-config totals."""
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
cfgs = [f"{m}:{e}" for m in ("haiku", "sonnet") for e in EFF
        if any(r["model"] == m and r["effort"] == e for r in rows)]
order = {"locate": 0, "fix": 1, "feature": 2, "review": 3}
tasks = sorted({r["task"] for r in rows}, key=lambda t: (order[t.split("-")[0]], t))

by_cell: dict[tuple, list] = defaultdict(list)
for r in rows:
    by_cell[(r["task"], f"{r['model']}:{r['effort']}")].append(r)
short = {c: c.replace("haiku:", "H-").replace("sonnet:", "S-").replace("medium", "med") for c in cfgs}
print("passes out of trials per cell")
print(f"{'task':26}" + "".join(f"{short[c]:>9}" for c in cfgs))
for t in tasks:
    cells = []
    for c in cfgs:
        rs = by_cell.get((t, c), [])
        cells.append(f"{sum(r['status'] == 'pass' for r in rs)}/{len(rs)}" if rs else ".")
    print(f"{t:26}" + "".join(f"{x:>9}" for x in cells))

print(f"\n{'config':14} {'pass rate':>10} {'out_tok':>10} {'in_tok':>12} {'agent_s':>8} {'false_claims':>13} {'denied':>7} {'errors':>7}")
for c in cfgs:
    rs = [r for r in rows if f"{r['model']}:{r['effort']}" == c]
    p = sum(r["status"] == "pass" for r in rs)
    out = sum(r.get("out") or 0 for r in rs)
    inp = sum(sum(r.get(k) or 0 for k in ("in", "cache_write", "cache_read")) for r in rs)
    secs = sum(round((r.get("turn_ms") or 0) / 1000) for r in rs)
    fc = sum(bool(r.get("false_success_claim")) for r in rs)
    den = sum(r.get("denied") or 0 for r in rs)
    err = sum(r["status"] in ("harness_error", "launch_fail", "timeout_or_err") for r in rs)
    print(f"{c:14} {p:>4}/{len(rs):<3} {out:>10,} {inp:>12,} {secs:>8} {fc:>13} {den:>7} {err:>7}")

print("\nNon-pass detail:")
for r in sorted(rows, key=lambda r: (r["task"], r["model"], EFF.index(r["effort"]), r["trial"])):
    if r["status"] == "pass":
        continue
    d = {k: r.get(k) for k in ("found", "planted", "failures", "must_pass_missing", "outside_expected",
                               "false_success_claim", "claimed_passed", "err") if r.get(k) not in (None, [], "", False)}
    print(f"  {r['task']:26} {r['model']}:{r['effort']:7} t{r['trial']} {r['status']:15} {json.dumps(d)[:200]}")
