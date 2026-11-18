#!/bin/bash
# For each slot, start a tiny Haiku session and report whether Claude shows the trust prompt.
set -u
H=~/.claude/skills/cmux-subagent/claude-pane.sh
for k in $(seq 1 8); do
  d=~/.cache/coding-bench/slots/s$k
  handle=$("$H" launch claude-haiku-5-5 "Reply with only the word: ok" --effort low --cwd "$d") || { echo "s$k: launch failed"; continue; }
  sid=${handle#*@}
  surf=${handle%%@*}
  res=unknown
  for _ in $(seq 1 60); do
    if [ -n "$(find ~/.claude/projects -name "$sid.jsonl" 2>/dev/null)" ]; then res=trusted; break; fi
    if cmux read-screen --surface "$surf" --lines 30 2>/dev/null | grep -q "trust this folder"; then res=PROMPT; break; fi
    sleep 0.5
  done
  if [ "$res" = trusted ]; then
    "$H" collect "$handle" 90 >/dev/null 2>&1
  else
    cmux close-surface --surface "$surf" --force >/dev/null 2>&1
  fi
  echo "s$k: $res"
done
