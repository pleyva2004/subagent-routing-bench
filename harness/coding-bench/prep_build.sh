#!/bin/bash
# Commit ids of the private target repo are replaced with COMMIT_* placeholders.
# Prepare build folders that the task-writing agents read from and write into.
set -eu
R=${BENCH_REPO:-~/.cache/coding-bench/repos/target}  # the target repo clone
B=~/.cache/coding-bench/build
mkdir -p "$B"

wt() {  # wt <path> <rev>: fresh detached worktree
  [ -e "$1" ] && git -C "$R" worktree remove --force "$1" 2>/dev/null || true
  rm -rf "$1"
  git -C "$R" worktree add -q --detach "$1" "$2"
}

# Replay tasks: briefs are written from the commit, its diff, and its hidden tests.
for c in COMMIT_F1 COMMIT_F2 COMMIT_F3 COMMIT_F4; do
  d="$B/replay-$c"; mkdir -p "$d"
  git -C "$R" log -1 --format='%B' "$c" > "$d/commit_message.txt"
  git -C "$R" show --format= "$c" -- src > "$d/src.diff"
  git -C "$R" show --format= "$c" -- tests > "$d/tests.diff"
  python3 -I -c "
import json,sys
r=[x for x in json.load(open('$HOME/.cache/coding-bench/admission.json')) if x['commit']=='$c'][0]
open('$d/hidden_tests.txt','w').write('\n'.join(r['fail_to_pass'])+'\n')"
  wt "$d/base" "$c^"
done

# Planted single-file bugs, on the current head.
for k in near far; do
  d="$B/inject-$k"; mkdir -p "$d"
  wt "$d/wt" HEAD
done

# Review diffs: plant bugs into the post-commit state of a real commit.
for c in COMMIT_R2 COMMIT_R3; do
  d="$B/review-$c"; mkdir -p "$d"
  git -C "$R" log -1 --format='%B' "$c" > "$d/commit_message.txt"
  git -C "$R" show --format= "$c" -- src > "$d/original.diff"
  wt "$d/wt" "$c"
done
ls "$B"
