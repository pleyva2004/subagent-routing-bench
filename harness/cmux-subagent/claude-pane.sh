#!/bin/bash
# cmux sub-agent helper.
# Usage:
#   claude-pane.sh <model> <prompt> [timeout] [--effort <level>] [run options]   open, wait, print reply, close
#   claude-pane.sh launch <model> <prompt> [--effort <level>] [run options] [--from <handle-or-surface>] [--dir left|right|up|down]
#                                                                    open only, print handle
# Run options (all optional):
#   --cwd <dir>                start Claude in <dir> instead of the calling pane's folder
#   --permission-mode <mode>   acceptEdits, auto, manual, dontAsk, or plan (bypassPermissions is refused)
#   --settings <file>          extra Claude settings file (for example, permission allow/deny rules)
#   claude-pane.sh collect <handle> [timeout]                        wait, print reply, close
# Layout is automatic: the first sub-agent opens one column to the right of the calling pane
# ($CMUX_SURFACE_ID), later ones stack below the newest live sub-agent pane in that column.
# --from and --dir override this (manual split). Those panes are not tracked, so later automatic
# launches never stack under them.
# Open panes are tracked in ${TMPDIR:-/tmp}/cmux-subagent/panes-<owner>, one line per pane:
# "<surface-uuid> <epoch-seconds-when-added>", where <owner> is $CMUX_SURFACE_ID (or "default").
# A pane added less than 20s ago counts as live even if cmux tree doesn't list it yet.
# collect removes a pane when it closes it.
# Surfaces are always addressed by UUID (short refs like surface:12 resolve inconsistently in cmux).
# Handle: <surface-uuid>@<session-id>, printed by launch and passed unchanged to collect and --from.
# --from also accepts a plain surface id (ref or UUID); only the part before "@" is used.
# Models: haiku, sonnet, claude-haiku-*, claude-sonnet-* only. The prompt must be non-empty.
# Effort levels: low, medium, high, xhigh, max. Omitted means Claude's default.
# Timeout: seconds, digits only, at most 6 digits. Default 120.
# The reply is read from the session transcript (read_transcript.py, same folder), not the screen.
# The prompt reaches the pane through a temp file, so its length and content don't matter.
# If no transcript appears within min(60, timeout) seconds, collect gives up and prints the pane's
# last lines (usually a trust-folder or permission prompt). A timeout with a transcript prints them too.
# Exit codes:
#   0    complete, non-empty reply
#   1    timeout (partial reply on stdout), empty reply, no transcript, transcript reader failed,
#        session id or split failed
#   2    bad arguments or missing read_transcript.py; no pane opened
#   130  interrupted; collect closes its pane. An interrupted launch releases the lock and deletes the
#        prompt file, but a pane it already opened stays open.
set -u

# Follow symlinks (readlink without -f, which may be missing) so a symlinked script still finds its folder.
resolve_script_dir() {
  local src="$0" link dir n=0
  while [ -L "$src" ] && [ "$n" -lt 40 ]; do
    dir=$(cd "$(dirname "$src")" && pwd)
    link=$(readlink "$src")
    case "$link" in
      /*) src="$link" ;;
      *) src="$dir/$link" ;;
    esac
    n=$((n + 1))
  done
  (cd "$(dirname "$src")" && pwd)
}

script_dir=$(resolve_script_dir)
reader="$script_dir/read_transcript.py"

require_reader() {
  if [ ! -f "$reader" ]; then
    echo "missing read_transcript.py next to claude-pane.sh" >&2
    return 2
  fi
}

# Pane tracking. Owner is the calling pane; $CMUX_WORKSPACE_ID is not used because it can be stale.
owner="${CMUX_SURFACE_ID:-default}"
owner="${owner//\//_}"
state_dir="${TMPDIR:-/tmp}/cmux-subagent"
state_file="$state_dir/panes-$owner"
lock_dir="$state_file.lock"
lock_held=0

# mkdir lock (no flock on macOS). Retries every 0.1s for up to 10s; a lock older than 30s is stale.
lock_acquire() {
  local start=$SECONDS mtime now
  mkdir -p "$state_dir" 2>/dev/null || return 1
  while ! mkdir "$lock_dir" 2>/dev/null; do
    [ $((SECONDS - start)) -ge 10 ] && return 1
    mtime=$(stat -f %m "$lock_dir" 2>/dev/null || stat -c %Y "$lock_dir" 2>/dev/null)
    case "$mtime" in
      ""|*[!0-9]*) mtime="" ;;
    esac
    if [ -n "$mtime" ]; then
      now=$(date +%s)
      if [ $((now - mtime)) -gt 30 ]; then
        rmdir "$lock_dir" 2>/dev/null
        continue
      fi
    fi
    sleep 0.1
  done
  lock_held=1
}

lock_release() {
  rmdir "$lock_dir" 2>/dev/null
  lock_held=0
}

# Caller holds the lock. A surface is live if its UUID appears as a whole word in `cmux tree --all --id-format both`,
# or if it was added less than 20s ago (cmux lists a new surface in the tree only after a moment).
# Lines without a timestamp count as old.
state_prune() {
  [ -f "$state_file" ] || return 0
  local tree id ts rest now tmp
  # If the tree can't be read, keep every entry: an empty tree would otherwise prune live panes.
  tree=$(cmux tree --all --id-format both 2>/dev/null) || return 0
  [ -n "$tree" ] || return 0
  now=$(date +%s)
  tmp=$(mktemp "$state_file.XXXXXX") || return 1
  while read -r id ts rest; do
    [ -n "$id" ] || continue
    case "$ts" in
      ""|*[!0-9]*) ts=0 ;;
    esac
    if printf '%s\n' "$tree" | grep -qwF -e "$id" || [ $((now - ts)) -lt 20 ]; then
      printf '%s %s\n' "$id" "$ts" >> "$tmp"
    fi
  done < "$state_file"
  mv "$tmp" "$state_file" || rm -f "$tmp"
}

state_add() {
  printf '%s %s\n' "$1" "$(date +%s)" >> "$state_file"
}

# Caller holds the lock.
state_drop() {
  local tmp
  [ -f "$state_file" ] || return 0
  tmp=$(mktemp "$state_file.XXXXXX") || return 1
  awk -v u="$1" '$1 != u' "$state_file" > "$tmp"
  mv "$tmp" "$state_file" || rm -f "$tmp"
}

# Takes the lock itself. If the lock can't be had, the entry stays and is pruned as dead on the next launch.
state_remove() {
  local tmp
  lock_acquire || return 0
  if [ -f "$state_file" ]; then
    tmp=$(mktemp "$state_file.XXXXXX") && {
      awk -v u="$1" '$1 != u' "$state_file" > "$tmp"
      mv "$tmp" "$state_file" || rm -f "$tmp"
    }
  fi
  lock_release
}

# Digits only, at most 6: longer values overflow [ -ge ] and the loop would never time out.
valid_timeout() {
  case "$1" in
    ""|*[!0-9]*) return 1 ;;
  esac
  [ "${#1}" -le 6 ]
}

# Runs cmux with the caller's $args and $errf (launch's locals) and sets out, rc, surface and not_found.
# cmux registers a new surface asynchronously, so a split from a just-created surface can fail with
# "not_found". Retry only that error, up to 10 times, 0.3s apart.
split_with_retry() {
  local tries=0
  not_found=0
  while :; do
    out=$(cmux "${args[@]}" 2>"$errf")
    rc=$?
    if [ "$rc" -eq 0 ]; then
      not_found=0
      split_ok=1
      break
    fi
    if grep -q 'not_found' "$errf" || printf '%s\n' "$out" | grep -q 'not_found'; then
      not_found=1
    else
      not_found=0
      break
    fi
    [ "$tries" -ge 10 ] && break
    tries=$((tries + 1))
    sleep 0.3
  done
  # Output: "OK surface:<n> (<surface-uuid>) workspace:<n> (<uuid>)"; take the first UUID on the OK line.
  surface=$(printf '%s\n' "$out" | grep -m1 '^OK ' | grep -oE '[0-9A-Fa-f]{8}(-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}' | head -n 1)
}

# Diagnostic only, never used for the reply: last 15 non-empty lines of the pane, to stderr.
pane_tail() {
  cmux read-screen --surface "$1" --lines 40 2>/dev/null | grep -v '^[[:space:]]*$' | tail -n 15 >&2
}

launch() {
  if [ $# -lt 2 ]; then
    echo "usage: claude-pane.sh launch <model> <prompt> [--effort <level>] [--cwd <dir>] [--permission-mode <mode>] [--settings <file>] [--from <handle-or-surface>] [--dir left|right|up|down]" >&2
    return 2
  fi
  local model="$1" prompt="$2" from="" dir="right" effort="" from_set=0 dir_set=0
  local cwd="" pmode="" settings=""
  shift 2

  case "$model" in
    haiku|sonnet|claude-haiku-*|claude-sonnet-*) ;;
    *) echo "model not allowed: $model (Haiku or Sonnet only)" >&2; return 2 ;;
  esac
  # Keeps the pane command well under the ~1,024 characters cmux can type.
  if [ "${#model}" -gt 100 ]; then
    echo "model name too long" >&2
    return 2
  fi

  if [ -z "$prompt" ]; then
    echo "empty prompt" >&2
    return 2
  fi

  while [ $# -gt 0 ]; do
    case "$1" in
      --from|--dir|--effort|--cwd|--permission-mode|--settings)
        # Guard: "shift 2" on a lone flag fails without shifting and would loop forever.
        if [ $# -lt 2 ]; then
          echo "missing value for $1" >&2
          return 2
        fi
        case "$1" in
          --from) from="$2"; from_set=1 ;;
          --dir) dir="$2"; dir_set=1 ;;
          --effort) effort="$2" ;;
          --cwd) cwd="$2" ;;
          --permission-mode) pmode="$2" ;;
          --settings) settings="$2" ;;
        esac
        shift 2
        ;;
      *) echo "unknown argument: $1" >&2; return 2 ;;
    esac
  done

  case "$effort" in
    ""|low|medium|high|xhigh|max) ;;
    *) echo "invalid effort: $effort (use low, medium, high, xhigh, or max)" >&2; return 2 ;;
  esac

  case "$dir" in
    left|right|up|down) ;;
    *) echo "invalid dir: $dir (use left, right, up, or down)" >&2; return 2 ;;
  esac

  # Sub-agents never get permission checks switched off.
  case "$pmode" in
    ""|acceptEdits|auto|manual|dontAsk|plan) ;;
    *) echo "invalid permission mode: $pmode (use acceptEdits, auto, manual, dontAsk, or plan)" >&2; return 2 ;;
  esac

  # Absolute paths, because the pane's shell starts in the calling pane's folder, not this one.
  if [ -n "$cwd" ]; then
    cwd=$(cd "$cwd" 2>/dev/null && pwd) || { echo "invalid --cwd: not a directory" >&2; return 2; }
  fi
  if [ -n "$settings" ]; then
    if [ ! -f "$settings" ]; then
      echo "invalid --settings: not a file: $settings" >&2
      return 2
    fi
    settings="$(cd "$(dirname "$settings")" && pwd)/$(basename "$settings")"
  fi

  # --from takes a handle or a plain surface ref; only the part before the first "@" is used.
  if [ -n "$from" ]; then
    from="${from%%@*}"
    if [ -z "$from" ]; then
      echo "invalid --from: empty surface" >&2
      return 2
    fi
  fi

  require_reader || return 2

  local sid
  sid=$(uuidgen | tr 'A-Z' 'a-z')
  if [ -z "$sid" ]; then
    echo "failed to create session id" >&2
    return 1
  fi

  # cmux types the pane command and drops input past ~1,024 characters, so the prompt goes through a
  # temp file that the pane's shell reads and deletes.
  local pf qpf
  pf=$(mktemp "${TMPDIR:-/tmp}/cmux-subagent.XXXXXX") || { echo "failed to create prompt file" >&2; return 1; }
  if ! printf '%s' "$prompt" > "$pf"; then
    rm -f "$pf"
    echo "failed to write prompt file" >&2
    return 1
  fi
  qpf=$(printf '%q' "$pf")

  # The "--" keeps a prompt that starts with "-" from being parsed as an option.
  local cmd="claude --model $(printf '%q' "$model")"
  [ -n "$cwd" ] && cmd="cd $(printf '%q' "$cwd") && $cmd"
  [ -n "$effort" ] && cmd="$cmd --effort $effort"
  [ -n "$pmode" ] && cmd="$cmd --permission-mode $pmode"
  [ -n "$settings" ] && cmd="$cmd --settings $(printf '%q' "$settings")"
  cmd="$cmd --session-id $sid -- \"\$(cat $qpf; rm -f $qpf)\""
  # cmux drops typed input past ~1,024 characters; long --cwd or --settings paths could get there.
  if [ "${#cmd}" -gt 1000 ]; then
    rm -f "$pf"
    echo "pane command too long (${#cmd} chars); use shorter --cwd or --settings paths" >&2
    return 2
  fi

  # Auto mode (no --from/--dir): stack below the newest live sub-agent pane, else open a column
  # to the right of the calling pane. The lock covers only the state work. With no anchor, the new
  # column is opened and recorded under the lock so two launches can't both open one; a split down
  # from an anchor, with its retries, runs outside the lock.
  local auto=0 last="" args out rc surface not_found=0 split_ok=0
  [ "$from_set" -eq 0 ] && [ "$dir_set" -eq 0 ] && auto=1

  local errf=""
  errf=$(mktemp)
  # Interrupted launch: release our lock if we hold it, drop the prompt file. collect's trap takes over later.
  # Once a split succeeded the pane's shell reads and deletes the prompt file itself, so keep it.
  trap '[ "$lock_held" -eq 1 ] && lock_release; [ "$split_ok" -eq 1 ] || rm -f "$pf"; rm -f ${errf:+"$errf"}; exit 130' INT TERM HUP

  if [ "$auto" -eq 1 ]; then
    while :; do
      if ! lock_acquire; then
        rm -f "$errf" "$pf"
        trap - INT TERM HUP
        echo "failed to lock pane state ($lock_dir)" >&2
        return 1
      fi
      state_prune
      last=$(grep -v '^$' "$state_file" 2>/dev/null | tail -n 1)
      last="${last%% *}"
      if [ -z "$last" ]; then
        args=(new-split right --id-format both --command "$cmd" --focus false)
        [ -n "${CMUX_SURFACE_ID:-}" ] && args+=(--surface "$CMUX_SURFACE_ID")
        split_with_retry
        [ "$rc" -eq 0 ] && [ -n "$surface" ] && state_add "$surface"
        lock_release
        break
      fi
      lock_release

      args=(new-split down --id-format both --command "$cmd" --focus false --surface "$last")
      split_with_retry
      if [ "$rc" -eq 0 ] && [ -n "$surface" ]; then
        if lock_acquire; then
          state_add "$surface"
          lock_release
        fi
        break
      fi
      # Anchor gone (still not_found after the retries): forget it and pick again.
      [ "$not_found" -eq 1 ] || break
      lock_acquire || break
      state_drop "$last"
      lock_release
    done
  else
    args=(new-split "$dir" --id-format both --command "$cmd" --focus false)
    [ -n "$from" ] && args+=(--surface "$from")
    split_with_retry
  fi
  if [ "$rc" -ne 0 ] || [ -z "$surface" ]; then
    cat "$errf" >&2
    [ -n "$out" ] && printf '%s\n' "$out" >&2
    rm -f "$errf" "$pf"
    trap - INT TERM HUP
    echo "failed to open split" >&2
    return 1
  fi
  rm -f "$errf"
  trap - INT TERM HUP
  echo "$surface@$sid"
}

collect() {
  if [ $# -lt 1 ]; then
    echo "usage: claude-pane.sh collect <handle> [timeout]" >&2
    return 2
  fi
  require_reader || return 2
  local handle="$1" timeout="${2:-120}"

  case "$handle" in
    ?*@?*) ;;
    *) echo "invalid handle: $handle (expected <surface-uuid>@<session-id>)" >&2; return 2 ;;
  esac
  local surface="${handle%%@*}" sid="${handle#*@}"

  if ! valid_timeout "$timeout"; then
    echo "invalid timeout: $timeout (seconds, digits only, at most 6 digits)" >&2
    return 2
  fi

  # If interrupted inside the locked section, drop our own lock first; state_remove waits at most 10s.
  trap 'cmux close-surface --surface "$surface" --force >/dev/null 2>&1; [ "$lock_held" -eq 1 ] && lock_release; state_remove "$surface"; exit 130' INT TERM HUP

  # Give up early if the agent never starts (e.g. stuck at a trust-folder prompt).
  local start_wait="$timeout"
  [ "$start_wait" -gt 60 ] && start_wait=60

  local path="" f start=$SECONDS finished=0 elapsed drc
  while :; do
    if [ -z "$path" ]; then
      for f in "${CLAUDE_CONFIG_DIR:-$HOME/.claude}"/projects/*/"$sid".jsonl; do
        if [ -f "$f" ]; then
          path="$f"
          break
        fi
      done
    fi
    if [ -n "$path" ]; then
      python3 -I "$reader" done "$path"
      drc=$?
      if [ "$drc" -eq 0 ]; then
        finished=1
        break
      elif [ "$drc" -ge 2 ]; then
        cmux close-surface --surface "$surface" --force >/dev/null
        state_remove "$surface"
        echo "transcript reader failed" >&2
        return 1
      fi
    fi
    elapsed=$((SECONDS - start))
    [ "$elapsed" -ge "$timeout" ] && break
    if [ -z "$path" ] && [ "$elapsed" -ge "$start_wait" ]; then
      break
    fi
    # Background sleep + wait lets a signal trap fire immediately instead of after the sleep.
    sleep 2 &
    wait $!
  done

  local reply rc
  if [ "$finished" -eq 1 ]; then
    reply=$(python3 -I "$reader" reply "$path")
    rc=$?
    cmux close-surface --surface "$surface" --force >/dev/null
    state_remove "$surface"
    if [ "$rc" -ge 2 ]; then
      echo "transcript reader failed" >&2
      return 1
    elif [ "$rc" -ne 0 ]; then
      echo "empty reply" >&2
      return 1
    fi
    printf '%s\n' "$reply"
    return 0
  fi

  if [ -n "$path" ]; then
    reply=$(python3 -I "$reader" partial "$path")
    [ -n "$reply" ] && printf '%s\n' "$reply"
    echo "timed out after ${timeout}s; reply below is partial" >&2
    echo "the pane showed:" >&2
    pane_tail "$surface"
    cmux close-surface --surface "$surface" --force >/dev/null
    state_remove "$surface"
    return 1
  fi

  echo "no transcript for session $sid after $((SECONDS - start))s; the pane showed:" >&2
  pane_tail "$surface"
  cmux close-surface --surface "$surface" --force >/dev/null
  state_remove "$surface"
  return 1
}

case "${1:-}" in
  launch)  shift; launch "$@" ;;
  collect) shift; collect "$@" ;;
  *)
    if [ $# -lt 2 ]; then
      echo "usage: claude-pane.sh <model> <prompt> [timeout] [--effort <level>] [--cwd <dir>] [--permission-mode <mode>] [--settings <file>]" >&2
      exit 2
    fi
    model="$1" prompt="$2"
    shift 2
    timeout=120
    if [ $# -gt 0 ] && [ "${1#--}" = "$1" ]; then
      timeout="$1"
      shift
    fi
    # A non-numeric timeout (e.g. "high" passed without --effort) would never trip the timeout.
    if ! valid_timeout "$timeout"; then
      echo "invalid timeout: $timeout (seconds, digits only, at most 6 digits; pass effort as --effort <level>)" >&2
      exit 2
    fi
    require_reader || exit 2
    handle=$(launch "$model" "$prompt" "$@") || exit $?
    collect "$handle" "$timeout"
    ;;
esac
