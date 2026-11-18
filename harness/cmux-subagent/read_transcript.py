#!/usr/bin/env python3
"""Read the final reply from a Claude Code session transcript (JSON Lines).

Usage: python3 -I read_transcript.py <done|reply|partial> <path>

  done     exit 0 if the turn has finished (the last system/turn_duration entry
           has no pending*Count above 0), else 1
  reply    print the final assistant message's text; exit 0 if non-empty, else 1
  partial  print the latest assistant message that has text; always exit 0

Missing file or bad arguments: message on stderr, exit 2.
Any unexpected exception: "read_transcript.py: <error>" on stderr, exit 3.
"""
import json
import sys
from typing import Any, Dict, List, Optional, Tuple

USAGE = "usage: read_transcript.py <done|reply|partial> <path>"

# (message key, text blocks of this entry, is-api-error)
Entry = Tuple[Any, List[str], bool]


def load_entries(path: str) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except ValueError:
                continue  # the last line may be half-written
            if isinstance(obj, dict):
                entries.append(obj)
    return entries


def is_done(entries: List[Dict[str, Any]]) -> bool:
    last: Optional[Dict[str, Any]] = None
    for e in entries:
        if e.get("type") == "system" and e.get("subtype") == "turn_duration":
            last = e
    if last is None:
        return False
    # Background work still pending means the turn has not really finished.
    for key, val in last.items():
        if (
            isinstance(key, str)
            and key.startswith("pending")
            and key.endswith("Count")
            and isinstance(val, (int, float))
            and not isinstance(val, bool)
            and val > 0
        ):
            return False
    return True


def text_blocks(content: Any) -> List[str]:
    if isinstance(content, str):
        return [content]
    if not isinstance(content, list):
        return []
    out: List[str] = []
    for block in content:
        if (
            isinstance(block, dict)
            and block.get("type") == "text"
            and isinstance(block.get("text"), str)
        ):
            out.append(block["text"])
    return out


def assistant_messages(entries: List[Dict[str, Any]]) -> List[Tuple[Any, List[str], bool]]:
    """Group assistant entries by message.id, in order of first appearance.

    Returns a list of (key, text blocks in file order, is_api_error).
    """
    order: List[Any] = []
    groups: Dict[Any, Tuple[List[str], bool]] = {}
    for n, e in enumerate(entries):
        if e.get("type") != "assistant":
            continue
        msg = e.get("message")
        if not isinstance(msg, dict):
            msg = {}
        mid = msg.get("id")
        key: Any = mid if isinstance(mid, str) and mid else ("entry", n)
        err = e.get("isApiErrorMessage") is True or msg.get("isApiErrorMessage") is True
        texts = text_blocks(msg.get("content"))
        if key not in groups:
            order.append(key)
            groups[key] = ([], False)
        prev_texts, prev_err = groups[key]
        groups[key] = (prev_texts + texts, prev_err or err)
    # A message's position is that of its last entry, so "last" means the
    # message of the last assistant entry in the file.
    last_key: Optional[Any] = None
    for e_n in range(len(entries) - 1, -1, -1):
        e = entries[e_n]
        if e.get("type") == "assistant":
            msg = e.get("message") if isinstance(e.get("message"), dict) else {}
            mid = msg.get("id")
            last_key = mid if isinstance(mid, str) and mid else ("entry", e_n)
            break
    if last_key is not None and last_key in groups:
        order = [k for k in order if k != last_key] + [last_key]
    return [(k, groups[k][0], groups[k][1]) for k in order]


def join_text(texts: List[str]) -> str:
    return "\n\n".join(t for t in texts if t.strip()).rstrip()


def cmd_reply(entries: List[Dict[str, Any]]) -> int:
    msgs = assistant_messages(entries)
    if not msgs:
        return 1
    _, texts, err = msgs[-1]
    text = join_text(texts)
    if err:
        print(text, file=sys.stderr)
        return 1
    if not text:
        return 1
    print(text)
    return 0


def cmd_partial(entries: List[Dict[str, Any]]) -> int:
    for _, texts, _ in reversed(assistant_messages(entries)):
        text = join_text(texts)
        if text:
            print(text)
            break
    return 0


def main(argv: List[str]) -> int:
    if len(argv) != 3 or argv[1] not in ("done", "reply", "partial"):
        print(USAGE, file=sys.stderr)
        return 2
    cmd, path = argv[1], argv[2]
    try:
        entries = load_entries(path)
    except OSError as exc:
        print(f"cannot read {path}: {exc.strerror or exc}", file=sys.stderr)
        return 2
    if cmd == "done":
        return 0 if is_done(entries) else 1
    if cmd == "reply":
        return cmd_reply(entries)
    return cmd_partial(entries)


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        try:
            # "replace" keeps a lone surrogate in a reply from aborting the print.
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass
    # An uncaught exception would exit 1, which claude-pane.sh reads as "not done yet".
    try:
        code = main(sys.argv)
    except Exception as exc:
        print(f"read_transcript.py: {exc}", file=sys.stderr)
        code = 3
    sys.exit(code)
