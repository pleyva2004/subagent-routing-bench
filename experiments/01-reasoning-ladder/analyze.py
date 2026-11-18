"""Summarize results.jsonl: pass grid, threshold per config/family, token use."""
from __future__ import annotations

import json
import sys
from collections import defaultdict

rows = [json.loads(l) for l in open(sys.argv[1])]
fams = ["mult", "trace", "logic"]
grid: dict[tuple, dict[int, str]] = defaultdict(dict)
toks: dict[tuple, list[int]] = defaultdict(list)
for r in rows:
    k = (r["model"][7:].replace("-5-5", ""), r["effort"], r["family"])
    grid[k][r["level"]] = r["status"]
    toks[k[:2]].append(r.get("output_tokens") or 0)
sym = {"pass": "✓", "wrong": "✗", "timeout_or_err": "T", "tool_violation": "!", "launch_fail": "L", "no_answer": "∅", "skipped": "·"}
print(f"{'config':16}" + "".join(f"{f:>13}" for f in fams) + "   threshold(highest level with all ≤ passing)")
for m in ["haiku", "sonnet"]:
    for e in ["low", "medium", "high", "xhigh"]:
        cells, th = [], []
        for f in fams:
            g = grid[(m, e, f)]
            cells.append("".join(sym.get(g.get(i, "-"), "-") for i in range(1, 11)))
            t = 0
            while g.get(t + 1) == "pass":
                t += 1
            th.append(t)
        print(f"{m + ' ' + e:16}" + "".join(f"{c:>13}" for c in cells) + f"   {th}  avg_out_tok={sum(toks[(m, e)]) // max(1, len(toks[(m, e)]))}")
print("\nNon-pass detail:")
for r in rows:
    if r["status"] not in ("pass", "skipped"):
        print(r["model"][7:13], r["effort"], r["task"], r["status"], "got", r.get("got"), "want", r.get("want"), r.get("err", ""))
