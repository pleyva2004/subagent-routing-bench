"""Grader self-test: the known-correct answer must pass and doing nothing must fail, for every task."""
from __future__ import annotations

import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bench  # noqa: E402

tasks = json.load(open(sys.argv[1] if len(sys.argv) > 1 else f"{bench.ROOT}/tasks.json"))
path = f"{bench.ROOT}/runs/oracle"
ok_all = True


def check(label: str, got: bool, want: bool) -> None:
    global ok_all
    ok_all &= got == want
    print(f"  {'ok ' if got == want else 'BAD'} {label}: pass={got} (want {want})", flush=True)


for t in tasks:
    print(t["id"], flush=True)
    if t["type"] == "locate":
        good = "\n".join(f"LOC: {x}" for x in t["expected"]) + "\nDONE"
        check("exact answer", bench.grade(t, path, "", good)["pass"], True)
        check("missing one", bench.grade(t, path, "", "\n".join(f"LOC: {x}" for x in t["expected"][1:]))["pass"], False)
        continue
    if t["type"] == "review":
        good = "\n".join(f"BUG: {k['file']}:{k['line']} - x" for k in t["key"]) or "NO BUGS FOUND"
        check("key answer", bench.grade(t, path, "", good)["pass"], True)
        bad = "NO BUGS FOUND" if t["key"] else "BUG: src/not_a_real_file.py:1 - x"
        check("wrong answer", bench.grade(t, path, "", bad)["pass"], False)
        continue
    for label, want in (("no change", False), ("reference solution", True)):
        base_rev = bench.prepare(t, path)
        if want:
            if t["type"] == "fix":
                r = subprocess.run(["git", "apply", "-R", t["setup_patch"]], cwd=path, capture_output=True, text=True)
            else:
                d = subprocess.run(["git", "diff", base_rev, t["hidden_from"], "--", "src"], cwd=path,
                                   capture_output=True, text=True).stdout
                r = subprocess.run(["git", "apply"], input=d, cwd=path, capture_output=True, text=True)
            if r.returncode:
                print("   apply failed:", r.stderr[:200])
        g = bench.grade(t, path, base_rev, "")
        check(label, g["pass"], want)
        if g["pass"] != want:
            print("   ", {k: g[k] for k in ("tests_run", "failures", "failing", "must_pass_missing")})
        bench.remove_worktree(path)
print("ALL GRADERS OK" if ok_all else "GRADER PROBLEMS FOUND")
