#!/bin/bash
# Open one pane per untrusted slot folder so the user can accept Claude's folder-trust prompt there.
# After each pane, confirm in ~/.claude.json that the trust was saved for that exact path.
set -u
H=~/.claude/skills/cmux-subagent/claude-pane.sh
trusted() {
  python3 -I -c "import json,os,sys; d=json.load(open(os.path.expanduser('~/.claude.json'))); sys.exit(0 if d.get('projects',{}).get(sys.argv[1],{}).get('hasTrustDialogAccepted') else 1)" "$1"
}
for k in $(seq 1 8); do
  d="$HOME/.cache/coding-bench/slots/s$k"
  if trusted "$d"; then echo "s$k: already trusted"; continue; fi
  handle=$("$H" launch claude-haiku-5-5 "Reply with only the word: trusted" --effort low --cwd "$d") || { echo "s$k: launch failed"; exit 1; }
  sid=${handle#*@}
  started=0
  for _ in $(seq 1 1200); do  # up to 10 minutes for the user to accept
    if [ -n "$(find ~/.claude/projects -name "$sid.jsonl" 2>/dev/null)" ]; then started=1; break; fi
    sleep 0.5
  done
  if [ "$started" = 0 ]; then
    cmux close-surface --surface "${handle%%@*}" --force >/dev/null 2>&1
    echo "s$k: not accepted within 10 minutes; stopping"
    exit 1
  fi
  "$H" collect "$handle" 120 >/dev/null 2>&1
  if trusted "$d"; then echo "s$k: trusted and saved"; else echo "s$k: session started but trust NOT saved; stopping"; exit 1; fi
done
echo "all 8 slots trusted"
