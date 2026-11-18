"""Assemble hard_tasks.json from the hard build folders. Run after writers and verifiers finish."""
# Commit ids of the private target repo are replaced with COMMIT_* placeholders.
from __future__ import annotations

import json
import os
import subprocess
from typing import Any

ROOT = os.path.expanduser("~/.cache/coding-bench")
REPO = os.environ.get("BENCH_REPO", f"{ROOT}/repos/target")  # the target repo clone
B = f"{ROOT}/hard"
HEAD = "COMMIT_HEAD"


def git(*a: str, cwd: str = REPO) -> str:
    return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True, check=True).stdout


def junit_id(node: str) -> str:
    """Pytest node id -> the classname::name id that run_suite reports.
    tests/pkg/test_mod.py::test_z -> tests.pkg.test_mod::test_z; tests/pkg/test_mod.py::TestC::test_z -> tests.pkg.test_mod.TestC::test_z"""
    parts = node.split("::")
    if not parts[0].endswith(".py"):
        return node
    mod = parts[0][:-3].replace("/", ".")
    return f"{'.'.join([mod, *parts[1:-1]])}::{parts[-1]}"


tasks: list[dict[str, Any]] = []
adm = {r["commit"]: r for f in ("admission.json", "admission_hard.json") for r in json.load(open(f"{ROOT}/{f}"))}


def feature(tid: str, c: str, brief_path: str, level: int) -> dict[str, Any]:
    r = adm[c]
    t = {"id": tid, "type": "feature", "level": level, "base": git("rev-parse", f"{c}^").strip(),
         "brief": open(brief_path).read().strip(), "hidden_test_files": r["test_files"], "hidden_from": c,
         "must_pass": r["fail_to_pass"], "expected_files": r["src_files"]}
    # The task is the code, not dependency management: start from the commit's dependency changes.
    dep = git("diff", f"{c}^", c, "--", "pyproject.toml", "uv.lock")
    if dep:
        t["setup_patch"] = f"{B}/deps-{c}.patch"
        open(t["setup_patch"], "w").write(dep)
    return t


for lvl, c in ((5, "COMMIT_F5"), (6, "COMMIT_F6"), (7, "COMMIT_F7")):
    tasks.append(feature(f"feature-{lvl}-{c}", c, f"{B}/replay-{c}/brief.md", lvl))
for c in ("COMMIT_F3", "COMMIT_F4"):
    tasks.append(feature(f"feature-terse-{c}", c, f"{B}/terse-{c}.md", 8))

for lvl, k in ((3, "hidden-far"), (4, "two-bugs"), (5, "misleading")):
    d = f"{B}/fix-{k}"
    patch = f"{d}/setup.patch"
    open(patch, "w").write(git("diff", cwd=f"{d}/wt"))
    bug = json.load(open(f"{d}/bug.json"))
    must = bug.get("hidden_tests", []) + bug.get("visible_failing_tests", [])
    tasks.append({"id": f"fix-{lvl}-{k}", "type": "fix", "level": lvl, "base": HEAD, "setup_patch": patch,
                  "report": open(f"{d}/report.md").read().strip(), "hidden_test_files": bug["hidden_test_files"],
                  "hidden_from": HEAD, "must_pass": [junit_id(t) for t in must], "expected_files": bug["files"]})

for lvl, c in ((4, "COMMIT_R4"), (5, "COMMIT_R5")):
    d = f"{B}/review-{c}"
    patch = f"{B}/review-{c}.patch"
    open(patch, "w").write(git("diff", f"{c}^", "--", "src", "tests", cwd=f"{d}/wt"))
    key = [{"file": k["file"], "line": k["line"], "description": k["description"]} for k in json.load(open(f"{d}/key.json"))]
    tasks.append({"id": f"review-{lvl}-{c}", "type": "review", "level": lvl, "base": git("rev-parse", f"{c}^").strip(),
                  "review_patch": patch, "commit_message": git("log", "-1", "--format=%B", c).strip(), "key": key})

json.dump(tasks, open(f"{ROOT}/hard_tasks.json", "w"), indent=1)
for t in tasks:
    extra = t.get("expected_files") or [k["file"] for k in t.get("key", [])]
    print(f"{t['id']:26} {t['type']:8} must_pass={len(t.get('must_pass', []))} files={extra}")
