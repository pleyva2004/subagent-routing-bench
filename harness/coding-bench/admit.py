"""Admission check for commit-replay tasks.

For commit C: run the suite at C^ with C's test files (base), and at C (reference).
FAIL_TO_PASS = tests failing at base and passing at reference. PASS_TO_PASS = passing at both.
Usage: python3 -I admit.py <repo> <out.json> <commit> [<commit> ...]
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET

IGNORE = ["--continue-on-collection-errors"] + [f"--ignore={p}" for p in os.environ.get("BENCH_IGNORE_TESTS", "").split(",") if p]
ROOT = os.path.expanduser("~/.cache/coding-bench/admit")


def sh(*args: str, cwd: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(list(args), cwd=cwd, capture_output=True, text=True)


def run_suite(wt: str, tag: str) -> dict[str, str]:
    """Return {test_id: outcome} with outcome in pass/fail/skip, plus collection errors as fail."""
    xml = os.path.join(ROOT, f"{tag}.xml")
    sh("uv", "sync", "--all-groups", "-q", cwd=wt)
    sh("uv", "run", "pytest", "-q", "-p", "no:cacheprovider", f"--junitxml={xml}", *IGNORE, cwd=wt)
    out: dict[str, str] = {}
    if not os.path.exists(xml):
        return out
    for tc in ET.parse(xml).iter("testcase"):
        tid = f"{tc.get('classname')}::{tc.get('name')}"
        kids = {k.tag for k in tc}
        out[tid] = "fail" if kids & {"failure", "error"} else ("skip" if "skipped" in kids else "pass")
    return out


def worktree(repo: str, path: str, rev: str) -> None:
    if os.path.exists(path):
        sh("git", "worktree", "remove", "--force", path, cwd=repo)
    r = sh("git", "worktree", "add", "--detach", "-f", path, rev, cwd=repo)
    if r.returncode:
        raise RuntimeError(r.stderr)


def admit(repo: str, c: str) -> dict[str, object]:
    files = sh("git", "show", "--name-status", "--format=", c, cwd=repo).stdout.split("\n")
    changed = [ln.split("\t") for ln in files if ln.strip()]
    tests = [p[-1] for p in changed if p[-1].startswith("tests/")]
    src = [p[-1] for p in changed if p[-1].startswith("src/")]
    base_wt, ref_wt = os.path.join(ROOT, f"{c}-base"), os.path.join(ROOT, f"{c}-ref")
    worktree(repo, base_wt, f"{c}^")
    sh("git", "checkout", c, "--", *tests, cwd=base_wt)  # the commit's tests on the old code
    worktree(repo, ref_wt, c)
    base, ref = run_suite(base_wt, f"{c}-base"), run_suite(ref_wt, f"{c}-ref")
    f2p = sorted(t for t, o in ref.items() if o == "pass" and base.get(t, "fail") == "fail")
    p2p = sorted(t for t, o in ref.items() if o == "pass" and base.get(t) == "pass")
    broken_ref = sorted(t for t, o in ref.items() if o == "fail")
    for wt in (base_wt, ref_wt):
        sh("git", "worktree", "remove", "--force", wt, cwd=repo)
    subj = sh("git", "log", "-1", "--format=%s", c, cwd=repo).stdout.strip()
    return {"commit": c, "subject": subj, "src_files": src, "test_files": tests,
            "fail_to_pass": f2p, "pass_to_pass_count": len(p2p), "ref_failures": broken_ref,
            "admitted": bool(f2p) and not broken_ref}


if __name__ == "__main__":
    repo, out_path, commits = sys.argv[1], sys.argv[2], sys.argv[3:]
    os.makedirs(ROOT, exist_ok=True)
    results = []
    for c in commits:
        r = admit(repo, c)
        results.append(r)
        print(f"{c} admitted={r['admitted']} src={len(r['src_files'])} f2p={len(r['fail_to_pass'])} "
              f"p2p={r['pass_to_pass_count']} ref_fail={len(r['ref_failures'])} | {r['subject'][:60]}", flush=True)
    json.dump(results, open(out_path, "w"), indent=1)
