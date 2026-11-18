#!/bin/bash
# Commit ids of the private target repo are replaced with COMMIT_* placeholders.
# Build folders for the hard task writers. Usage: prep_hard.sh <feature commit>...
set -eu
R=${BENCH_REPO:-~/.cache/coding-bench/repos/target}  # the target repo clone
B=~/.cache/coding-bench/hard
mkdir -p "$B/prompts"
wt() {  # fresh detached worktree with its venv synced, so writers can run the suite
  git -C "$R" worktree remove --force "$1" >/dev/null 2>&1 || true
  rm -rf "$1"; git -C "$R" worktree prune
  git -C "$R" worktree add -q --detach "$1" "$2"
  (cd "$1" && uv sync --all-groups -q)
}
for c in "$@"; do
  d="$B/replay-$c"; mkdir -p "$d"
  git -C "$R" log -1 --format='%B' "$c" > "$d/commit_message.txt"
  git -C "$R" show --format= "$c" -- src > "$d/src.diff"
  git -C "$R" show --format= "$c" -- tests > "$d/tests.diff"
  python3 -I -c "
import json
r=[x for x in json.load(open('$HOME/.cache/coding-bench/admission_hard.json')) if x['commit']=='$c'][0]
open('$d/hidden_tests.txt','w').write('\n'.join(r['fail_to_pass'])+'\n')"
  [ -d "$d/base" ] || { git -C "$R" worktree add -q --detach "$d/base" "$c^"; }
done
for k in hidden-far two-bugs misleading; do mkdir -p "$B/fix-$k"; wt "$B/fix-$k/wt" COMMIT_HEAD; done
for c in COMMIT_R4 COMMIT_R5; do
  d="$B/review-$c"; mkdir -p "$d"
  git -C "$R" log -1 --format='%B' "$c" > "$d/commit_message.txt"
  git -C "$R" show --format= "$c" -- src > "$d/original.diff"
  wt "$d/wt" "$c"
done
ls "$B"
