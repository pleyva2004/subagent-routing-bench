"""Coding-task benchmark for cmux sub-agents.

Each run: fresh git worktree at the task's base -> sub-agent via claude-pane.sh (dontAsk + allowlist)
-> grade from the worktree state (tests, changed files) or the reply (locate, review).

Usage: python3 -I bench.py --tasks tasks.json --out results.jsonl --configs sonnet:high,haiku:medium
                           [--trials 1] [--workers 6] [--only id1,id2] [--mode slots|home]
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import queue
import re
import shutil
import subprocess
import threading
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from typing import Any

HOME = os.path.expanduser("~")
ROOT = f"{HOME}/.cache/coding-bench"
REPO = os.environ.get("BENCH_REPO", f"{ROOT}/repos/target")  # the target repo clone
H = f"{HOME}/.claude/skills/cmux-subagent/claude-pane.sh"
SETTINGS = f"{ROOT}/settings/bench.json"
MODELS = {"haiku": "claude-haiku-5-5", "sonnet": "claude-sonnet-5-5"}
# Test files to skip (for example ones needing live network services), comma-separated.
IGNORED_TESTS = [p for p in os.environ.get("BENCH_IGNORE_TESTS", "").split(",") if p]
LIVE = [f"--ignore={p}" for p in IGNORED_TESTS]
TIMEOUT = {"locate": 600, "fix": 1800, "feature": 2700, "review": 1500}
IDENT = ["-c", "user.name=coding-bench", "-c", "user.email=coding-bench@localhost"]
out_lock = threading.Lock()


def sh(args: list[str], cwd: str | None = None, timeout: int | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout)


# ---------- worktrees ----------

def remove_worktree(path: str) -> None:
    sh(["git", "worktree", "remove", "--force", path], cwd=REPO)
    shutil.rmtree(path, ignore_errors=True)
    sh(["git", "worktree", "prune"], cwd=REPO)


def prepare(task: dict[str, Any], path: str) -> str:
    """Create the worktree for a run and return the base revision the agent starts from."""
    remove_worktree(path)
    r = sh(["git", "worktree", "add", "-q", "--detach", path, task["base"]], cwd=REPO)
    if r.returncode:
        raise RuntimeError(f"worktree add failed: {r.stderr}")
    if task.get("setup_patch"):  # e.g. a planted bug: committed, so the agent's diff is measured from it
        r = sh(["git", "apply", task["setup_patch"]], cwd=path)
        if r.returncode:
            raise RuntimeError(f"setup patch failed: {r.stderr}")
        sh(["git", "add", "-A"], cwd=path)
        sh(["git", *IDENT, "commit", "-q", "-m", "benchmark base"], cwd=path)
    base_rev = sh(["git", "rev-parse", "HEAD"], cwd=path).stdout.strip()
    if task.get("review_patch"):  # left uncommitted: the reviewer reads it with git diff
        r = sh(["git", "apply", task["review_patch"]], cwd=path)
        if r.returncode:
            raise RuntimeError(f"review patch failed: {r.stderr}")
    sh(["uv", "sync", "--all-groups", "-q"], cwd=path, timeout=600)
    return base_rev


def changed_files(path: str, base_rev: str) -> list[str]:
    tracked = sh(["git", "diff", "--name-only", base_rev], cwd=path).stdout.split()
    new = sh(["git", "ls-files", "--others", "--exclude-standard"], cwd=path).stdout.split()
    return sorted(set(tracked) | set(new))


def run_suite(path: str, tag: str) -> dict[str, str]:
    xml = os.path.join(path, f".bench-{tag}.xml")
    sh(["uv", "run", "pytest", "-q", "-p", "no:cacheprovider", "--continue-on-collection-errors",
        f"--junitxml={xml}", *LIVE], cwd=path, timeout=900)
    out: dict[str, str] = {}
    if os.path.exists(xml):
        for tc in ET.parse(xml).iter("testcase"):
            kids = {k.tag for k in tc}
            tid = f"{tc.get('classname')}::{tc.get('name')}"
            out[tid] = "fail" if kids & {"failure", "error"} else ("skip" if "skipped" in kids else "pass")
        os.remove(xml)
    return out


# ---------- prompts ----------

def where(path: str, mode: str) -> str:
    if mode == "home":
        return (f"The repository is at {path}. Run every shell command from there, "
                f"for example `cd {path} && uv run pytest -q`.")
    return "You are in the root folder of the repository."


RULES = ("Rules: work only inside this repository. Don't commit, push, stash, or switch branches; "
         "leave your changes in the working tree. Do the work yourself; don't start sub-agents. "
         "Run tests with `uv run pytest` (add -q, -x, or a path as needed).")


def prompt_for(task: dict[str, Any], path: str, mode: str) -> str:
    loc, t = where(path, mode), task["type"]
    if t == "locate":
        return (f"{loc}\n\nTask: {task['question']}\n\nSearch the code under src/ only (not tests/). "
                "Don't change any files. When done, reply with one line per location, exactly in the form "
                "`LOC: <path from the repository root>:<line number>`, then a final line `DONE`. "
                "List each location once.")
    if t == "fix":
        return (f"{loc}\n\nA teammate filed this bug report:\n\n{task['report']}\n\nFind the cause and fix it. "
                "Keep the change minimal, and make sure the existing test suite passes.\n\n"
                f"{RULES}\n\nWhen done, reply with: the root cause in one sentence, the files you changed, and "
                "the test results you observed (exact passed and failed counts from your last run).")
    if t == "feature":
        return (f"{loc}\n\nImplement this ticket:\n\n{task['brief']}\n\n{RULES}\n\nWhen done, reply with: "
                "a short summary of the change, the files you changed, and the test results you observed "
                "(exact passed and failed counts from your last run).")
    if t == "review":
        return (f"{loc}\n\nReview the uncommitted changes in this repository (see `git diff`). The author's "
                f"commit message:\n\n{task['commit_message']}\n\nReport only real defects that would cause "
                "incorrect behavior at runtime: no style, naming, or performance comments. Don't change any "
                "files. Reply with one line per defect, exactly in the form "
                "`BUG: <path from the repository root>:<line number in the changed file> - <what is wrong>`. "
                "If you find no defects, reply with the single line `NO BUGS FOUND`.")
    raise ValueError(t)


# ---------- grading ----------

def norm_path(p: str, path: str) -> str:
    p = p.strip().strip("`")
    for prefix in (path + "/", "./"):
        if p.startswith(prefix):
            p = p[len(prefix):]
    return p


def claims(reply: str) -> dict[str, Any]:
    """What the agent says its last test run showed. Only the last pytest-style summary counts, so a
    'before the fix: 1 failed' mention earlier in the reply doesn't read as a failure claim."""
    runs = list(re.finditer(r"(?:(\d+)\s+failed[,;\s]+)?(\d+)\s+passed(?:[,;\s]+(?:\d+\s+skipped[,;\s]+)?(\d+)\s+(?:failed|errors?)\b)?", reply))
    if runs:
        # The final full-suite run has the most passing tests; earlier mentions are baselines or partial runs.
        last = max(runs, key=lambda m: int(m.group(2)))
        failed = int(last.group(1) or last.group(3) or 0)
        return {"claimed_passed": int(last.group(2)), "claimed_all_pass": failed == 0}
    if re.search(r"\ball\b[^.\n]{0,40}\btests?\b[^.\n]{0,20}\bpass", reply, re.I):
        return {"claimed_passed": None, "claimed_all_pass": True}
    return {"claimed_passed": None, "claimed_all_pass": False}


def grade(task: dict[str, Any], path: str, base_rev: str, reply: str) -> dict[str, Any]:
    t = task["type"]
    if t == "locate":
        got = {f"{norm_path(m.group(1), path)}:{m.group(2)}"
               for m in re.finditer(r"LOC:\s*`?([^\s`]+?):(\d+)", reply)}
        want = set(task["expected"])
        return {"pass": got == want, "tp": len(got & want), "fp": len(got - want), "fn": len(want - got),
                "extra": sorted(got - want)[:10], "missed": sorted(want - got)}
    if t == "review":
        reported = [(norm_path(m.group(1), path), int(m.group(2)))
                    for m in re.finditer(r"BUG:\s*`?([^\s`]+?):(\d+)", reply)]
        keys, matched, extra = task["key"], set(), []
        for f, ln in reported:
            hit = next((i for i, k in enumerate(keys)
                        if i not in matched and k["file"] == f and abs(k["line"] - ln) <= 3), None)
            if hit is None:
                extra.append(f"{f}:{ln}")
            else:
                matched.add(hit)
        # Real commits have real bugs, so extra reports on a planted diff are recorded for adjudication,
        # not failed. A clean diff must come back clean: that is its purpose.
        ok = (len(matched) == len(keys)) if keys else not reported
        return {"pass": ok, "found": len(matched), "planted": len(keys), "false_alarms": len(extra),
                "extra_reports": extra, "reported": len(reported)}
    # fix / feature: grade the code, with the original tests restored and hidden tests added
    changed = changed_files(path, base_rev)
    hidden = task.get("hidden_test_files", [])
    for _attempt in range(2):
        sh(["git", "checkout", base_rev, "--", "tests"], cwd=path)
        sh(["git", "clean", "-fdq", "tests"], cwd=path)
        for f in hidden:
            sh(["git", "checkout", task["hidden_from"], "--", f], cwd=path)
        restored = not hidden or sh(["git", "diff", "--quiet", task["hidden_from"], "--", *hidden], cwd=path).returncode == 0
        if restored:
            break
    if not restored:
        raise RuntimeError("hidden test files could not be restored for grading")
    res = run_suite(path, "grade")
    # A hidden test file that yields no test results at all (not even a collection error) means the
    # grading run itself went wrong; that is a harness problem, not the agent's failure.
    live = set(IGNORED_TESTS)
    for f in hidden:
        mod = f[:-3].replace("/", ".")
        if f not in live and not any(k.split("::")[0].startswith(mod) or k == f"::{mod}" for k in res):
            raise RuntimeError(f"hidden test file produced no results: {f}")
    fails = sorted(k for k, v in res.items() if v == "fail")
    must = task.get("must_pass", [])
    missing = [m for m in must if res.get(m) != "pass"]
    src_changed = [c for c in changed if c.startswith("src/")]
    expected = set(task.get("expected_files", []))
    c = claims(reply)
    ok = bool(res) and not fails and not missing
    return {"pass": ok, "tests_run": len(res), "failures": len(fails), "failing": fails[:8],
            "must_pass_missing": missing[:8], "changed": changed[:30],
            "test_files_touched": [x for x in changed if x.startswith("tests/")],
            "outside_expected": sorted(set(src_changed) - expected) if expected else [],
            "expected_untouched": sorted(expected - set(src_changed)) if expected else [],
            **c, "false_success_claim": c["claimed_all_pass"] and not ok}


# ---------- transcripts ----------

def transcript_stats(sid: str) -> dict[str, Any]:
    paths = glob.glob(f"{HOME}/.claude/projects/*/{sid}.jsonl")
    st: dict[str, Any] = {"tool_uses": 0, "denied": 0, "turn_ms": None,
                          "in": 0, "cache_write": 0, "cache_read": 0, "out": 0}
    if not paths:
        return st
    usage: dict[str, dict[str, int]] = {}
    for line in open(paths[0], errors="replace"):
        try:
            e = json.loads(line)
        except ValueError:
            continue
        msg = e.get("message") or {}
        if e.get("type") == "assistant":
            for b in msg.get("content") or []:
                if isinstance(b, dict) and b.get("type") == "tool_use":
                    st["tool_uses"] += 1
            u = msg.get("usage") or {}
            cur = usage.setdefault(msg.get("id", ""), {})
            for k, src in (("in", "input_tokens"), ("cache_write", "cache_creation_input_tokens"),
                           ("cache_read", "cache_read_input_tokens"), ("out", "output_tokens")):
                cur[k] = max(cur.get(k, 0), u.get(src) or 0)
        elif e.get("type") == "user":
            for b in msg.get("content") or [] if isinstance(msg.get("content"), list) else []:
                if isinstance(b, dict) and b.get("type") == "tool_result" and b.get("is_error"):
                    if re.search(r"denied|permission", json.dumps(b.get("content")), re.I):
                        st["denied"] += 1
        elif e.get("type") == "system" and e.get("subtype") == "turn_duration":
            st["turn_ms"] = (st["turn_ms"] or 0) + (e.get("durationMs") or 0)
    for cur in usage.values():
        for k, v in cur.items():
            st[k] += v
    return st


# ---------- runs ----------

def run_one(task: dict[str, Any], model: str, effort: str, trial: int, slots: queue.Queue[str],
            mode: str, out: str) -> None:
    path = slots.get()
    run_id = f"{task['id']}--{model}-{effort}--t{trial}"
    art = f"{ROOT}/artifacts/{run_id}"
    os.makedirs(art, exist_ok=True)
    rec: dict[str, Any] = {"task": task["id"], "type": task["type"], "level": task.get("level"),
                           "model": model, "effort": effort, "trial": trial}
    t0 = time.time()
    try:
        base_rev = prepare(task, path)
        cwd = path if mode == "slots" else HOME
        p = sh([H, "launch", MODELS[model], prompt_for(task, path, mode), "--effort", effort,
                "--cwd", cwd, "--permission-mode", "dontAsk", "--settings", SETTINGS])
        if p.returncode:
            rec.update(status="launch_fail", err=p.stderr[-400:])
            return
        handle = p.stdout.strip()
        sid = handle.split("@", 1)[1]
        c = sh([H, "collect", handle, str(TIMEOUT[task["type"]])])
        reply = c.stdout
        open(f"{art}/reply.txt", "w").write(reply + ("\n--- stderr ---\n" + c.stderr if c.stderr else ""))
        sh(["git", "add", "-A", "-N"], cwd=path)  # intent-to-add, so new files appear in the saved diff
        open(f"{art}/agent.diff", "w").write(sh(["git", "diff", base_rev], cwd=path).stdout)
        sh(["git", "reset", "-q"], cwd=path)
        g = grade(task, path, base_rev, reply)
        status = "pass" if g["pass"] else ("timeout_or_err" if c.returncode else "fail")
        rec.update(status=status, rc=c.returncode, sid=sid, **g, **transcript_stats(sid))
    except Exception as ex:  # keep the batch going; the record says what broke
        rec.update(status="harness_error", err=repr(ex)[:400])
    finally:
        rec["wall_s"] = round(time.time() - t0, 1)
        remove_worktree(path)
        slots.put(path)
        with out_lock:
            with open(out, "a") as f:
                f.write(json.dumps(rec) + "\n")
            print(f"{run_id:48} {rec.get('status')}", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--configs", required=True, help="e.g. sonnet:high,haiku:medium")
    ap.add_argument("--trials", type=int, default=1)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--only", default="")
    ap.add_argument("--mode", choices=["slots", "home"], default="slots")
    a = ap.parse_args()
    tasks = json.load(open(a.tasks))
    if a.only:
        keep = set(a.only.split(","))
        tasks = [t for t in tasks if t["id"] in keep]
    configs = [tuple(c.split(":")) for c in a.configs.split(",")]
    done = set()
    if os.path.exists(a.out):
        for line in open(a.out):
            r = json.loads(line)
            if r["status"] not in ("launch_fail", "harness_error"):
                done.add((r["task"], r["model"], r["effort"], r["trial"]))
    slots: queue.Queue[str] = queue.Queue()
    base = f"{ROOT}/slots/s" if a.mode == "slots" else f"{ROOT}/runs/w"
    for k in range(1, a.workers + 1):
        slots.put(f"{base}{k}")
    jobs = [(t, m, e, i) for i in range(1, a.trials + 1) for t in tasks for m, e in configs
            if (t["id"], m, e, i) not in done]
    print(f"{len(jobs)} runs, {a.workers} workers, mode={a.mode}", flush=True)
    with ThreadPoolExecutor(a.workers) as ex:
        for j, (t, m, e, i) in enumerate(jobs):
            ex.submit(run_one, t, m, e, i, slots, a.mode, a.out)
            if j < a.workers:
                time.sleep(3)  # stagger first launches


if __name__ == "__main__":
    main()
