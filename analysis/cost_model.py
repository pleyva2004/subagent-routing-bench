"""How the study's API-equivalent dollar figures were computed.

Each run's cost is summed per request from its Claude Code session transcript
(~/.claude/projects/*/<session-id>.jsonl). The transcripts are not published, so the
figures in data/coding/ can't be re-derived from this repository alone; this file
documents the method and lets you apply it to your own runs.

Prices: first-party API, November 2026, per million tokens.
- Sonnet 5.5: $2.00 input, $10.00 output, $0.10 cache reads.
- Haiku 5.5: $0.10 input and $0.50 output for prompts up to 100K tokens; $0.50 and $2.50 beyond.
Assumed where the price list gave no rate: cache writes at 1.25x the input rate; Haiku cache
reads at 0.1x the input rate.

Usage: python3 analysis/cost_model.py <sonnet|haiku> <session-id>
"""
from __future__ import annotations

import glob
import json
import os
import sys

LONG_PROMPT = 100_000  # Haiku's long-prompt tier starts above this many prompt tokens


def rates(model: str, prompt_tokens: int) -> dict[str, float]:
    """Dollars per million tokens for one request."""
    if model == "sonnet":
        return {"in": 2.00, "out": 10.00, "cache_read": 0.10, "cache_write": 2.50}
    base_in, base_out = (0.10, 0.50) if prompt_tokens <= LONG_PROMPT else (0.50, 2.50)
    return {"in": base_in, "out": base_out, "cache_read": base_in * 0.1, "cache_write": base_in * 1.25}


def run_cost(model: str, session_id: str) -> float:
    """Sum the cost of every request in a session. Assistant messages are split across
    transcript entries that share a message id, so usage is taken once per id."""
    paths = glob.glob(os.path.expanduser(f"~/.claude/projects/*/{session_id}.jsonl"))
    if not paths:
        raise FileNotFoundError(f"no transcript for session {session_id}")
    usage: dict[str, dict[str, int]] = {}
    for line in open(paths[0], errors="replace"):
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if entry.get("type") != "assistant":
            continue
        message = entry.get("message") or {}
        u = message.get("usage") or {}
        cur = usage.setdefault(message.get("id", ""), {"in": 0, "cache_write": 0, "cache_read": 0, "out": 0})
        for key, field in (("in", "input_tokens"), ("cache_write", "cache_creation_input_tokens"),
                           ("cache_read", "cache_read_input_tokens"), ("out", "output_tokens")):
            cur[key] = max(cur[key], u.get(field) or 0)
    total = 0.0
    for u in usage.values():
        r = rates(model, u["in"] + u["cache_write"] + u["cache_read"])
        total += sum(u[k] * r[k] for k in u) / 1e6
    return total


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] not in ("sonnet", "haiku"):
        raise SystemExit("usage: cost_model.py <sonnet|haiku> <session-id>")
    print(f"${run_cost(sys.argv[1], sys.argv[2]):.5f}")
