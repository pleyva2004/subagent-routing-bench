"""Assemble docs/index.md from the section files in docs/sections/, in order."""
from __future__ import annotations

import glob
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEADER = """---
layout: default
title: Routing Claude sub-agents by model and effort
---

# Routing Claude sub-agents by model and effort

A case study of Claude Haiku 5.5 and Claude Sonnet 5.5 at every effort level, run as Claude Code sub-agents in cmux panes.

Technical report, November 2026. Code and data: [github.com/pleyva2004/subagent-routing-bench](https://github.com/pleyva2004/subagent-routing-bench).

"""
FOOTER = """
## Appendix: data and code

- Per-run results, task descriptions, costs and denial counts: [`data/`](https://github.com/pleyva2004/subagent-routing-bench/tree/main/data), with a [data dictionary](https://github.com/pleyva2004/subagent-routing-bench/blob/main/data/README.md).
- The verified numbers this report draws on: [`analysis/FACTS.md`](https://github.com/pleyva2004/subagent-routing-bench/blob/main/analysis/FACTS.md).
- The reasoning experiment, fully reproducible: [`experiments/01-reasoning-ladder/`](https://github.com/pleyva2004/subagent-routing-bench/tree/main/experiments/01-reasoning-ladder).
- The sub-agent helper and the coding harness: [`harness/`](https://github.com/pleyva2004/subagent-routing-bench/tree/main/harness). The coding tasks' target repository is private, so its code, briefs, patches and agent diffs are not included.
"""


def main() -> None:
    parts = sorted(glob.glob(os.path.join(ROOT, "docs", "sections", "*.md")))
    body = "\n\n".join(open(p).read().strip() for p in parts)
    with open(os.path.join(ROOT, "docs", "index.md"), "w") as f:
        f.write(HEADER + body + "\n" + FOOTER)
    print(f"assembled {len(parts)} section files into docs/index.md")


if __name__ == "__main__":
    main()
