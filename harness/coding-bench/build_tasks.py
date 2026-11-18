"""Assemble tasks.json from the build folders. Run after briefs, bugs, and review keys are final."""
from __future__ import annotations

import json
import os
import subprocess
from typing import Any

ROOT = os.path.expanduser("~/.cache/coding-bench")
REPO = os.environ.get("BENCH_REPO", f"{ROOT}/repos/target")  # the target repo clone
B = f"{ROOT}/build"
HEAD = "60913d6"


def git(*a: str, cwd: str = REPO) -> str:
    return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True, check=True).stdout


def junit_id(node: str) -> str:
    """tests/pkg/test_mod.py::test_x -> tests.pkg.test_mod::test_x (the ids run_suite reports)."""
    f, _, rest = node.partition("::")
    return f[:-3].replace("/", ".") + "::" + rest if f.endswith(".py") else node


tasks: list[dict[str, Any]] = []

# Locate: answers checked by hand against src/ at HEAD.
# Locate tasks: (question, expected "path:line" answers), checked by hand against the target repo.
# The study's three questions name private code, so they are not published. Shape:
#   ("Find where the function `<name>` is defined, and every place it is called.",
#    ["src/<package>/<module>.py:<line>", ...]),
loc: list[tuple[str, list[str]]] = [
]
for i, (q, exp) in enumerate(loc, 1):
    tasks.append({"id": f"locate-{i}", "type": "locate", "level": i, "base": HEAD, "question": q, "expected": exp})

# Fix: planted single-file bugs on HEAD.
for i, k in enumerate(["near", "far"], 1):
    d = f"{B}/inject-{k}"
    patch = f"{d}/setup.patch"
    open(patch, "w").write(git("diff", cwd=f"{d}/wt"))
    bug = json.load(open(f"{d}/bug.json"))
    tasks.append({"id": f"fix-{i}-{k}", "type": "fix", "level": i, "base": HEAD, "setup_patch": patch,
                  "report": open(f"{d}/report.md").read().strip(),
                  "must_pass": [junit_id(t) for t in bug["expected_failing_tests"]],
                  "expected_files": [bug["file"]]})

# Feature: real commits replayed from their parent, graded by the commit's own tests.
adm = {r["commit"]: r for r in json.load(open(f"{ROOT}/admission.json"))}
for i, c in enumerate(["bf88a3f", "ec8bef6", "d1d25cf", "43a549e"], 1):
    r = adm[c]
    tasks.append({"id": f"feature-{i}-{c}", "type": "feature", "level": i,
                  "base": git("rev-parse", f"{c}^").strip(), "brief": open(f"{B}/replay-{c}/brief.md").read().strip(),
                  "hidden_test_files": r["test_files"], "hidden_from": c, "must_pass": r["fail_to_pass"],
                  "expected_files": r["src_files"]})

# Review: a real commit's diff (src + tests) applied uncommitted on its parent, with 0, 1, or 2 planted bugs.
for i, (c, planted) in enumerate([("b0b1a97", False), ("e966b08", True), ("0c62b65", True)], 1):
    patch = f"{B}/review-{c}.patch"
    if planted:
        open(patch, "w").write(git("diff", f"{c}^", "--", "src", "tests", cwd=f"{B}/review-{c}/wt"))
        key = [{"file": k["file"], "line": k["line"], "description": k["description"]}
               for k in json.load(open(f"{B}/review-{c}/key.json"))]
    else:
        open(patch, "w").write(git("diff", f"{c}^", c, "--", "src", "tests"))
        key = []
    tasks.append({"id": f"review-{i}-{c}", "type": "review", "level": i, "base": git("rev-parse", f"{c}^").strip(),
                  "review_patch": patch, "commit_message": git("log", "-1", "--format=%B", c).strip(), "key": key})

json.dump(tasks, open(f"{ROOT}/tasks.json", "w"), indent=1)
for t in tasks:
    print(t["id"], t["type"], t.get("expected_files") or t.get("expected") or len(t.get("key", [])))
