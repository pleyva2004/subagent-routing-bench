# subagent-routing-bench

A study of which model and effort level to use for each kind of work a Claude Code sub-agent does.

Each sub-agent runs as its own interactive Claude Code session in a cmux terminal pane. The orchestrating session reads the reply from the session transcript. The study compares Claude Haiku 5.5 (`claude-haiku-5-5`) and Claude Sonnet 5.5 (`claude-sonnet-5-5`) at effort levels `low`, `medium`, `high`, `xhigh`, and `max`. No Opus sub-agents were used. Runs were made November 16–17, 2026.

**Report:** https://pleyva2004.github.io/subagent-routing-bench/ (methods, uncertainty, figures). This README is the short version.

## Key findings

- **Code trace was the only reasoning task that separated configs.** Longest program solved without tools: Haiku `low` 80 statements; Haiku `medium` and `high` 250; Haiku `xhigh` and Sonnet `low` and `medium` 400; Sonnet `high` 900; Sonnet `xhigh` 1,300, with no failure.
- **Easy coding set (12 tasks, 120 runs): almost everything passed.** Every config passed all locate, fix, and feature tasks. Only the two-bug review task separated configs: Sonnet `low`, `medium`, `high`, and `max` passed 12/12. Sonnet `xhigh` and every Haiku level passed 11/12.
- **Hard coding set (10 tasks, 150 runs, three trials per config):** Haiku `low` passed 29/30, including 24/24 code changes, at $0.041 per successful task. Sonnet `medium` passed 27/30 at $0.210 per success. Sonnet `xhigh` passed 27/30 at $0.532. Of the 14 hard-set misses, 13 came from one review task with three planted bugs.
- **Haiku is cheaper per success; effort above `medium` added cost without adding passes.** On the hard set, Haiku `low` cost about a fifth of Sonnet `low` per success ($0.041 vs $0.207). Sonnet `xhigh` cost $0.532 per success against $0.210 for Sonnet `medium`, with the same 27/30 pass count.
- **Routing rule adopted from these results:** Haiku `low` for lookups and code changes up to about 15 files; Sonnet `medium` when wall-clock time matters; Haiku `low` and Sonnet `medium` in parallel for review; Sonnet `xhigh` for long exact reasoning without tools; `max` only on explicit request.

Coding runs cost about $24 (easy set) and $34 (hard set) at API-equivalent prices. These are estimates from transcripts, not billing data.

## Limits

- One private Python repository, 22 coding tasks. The easy set has one trial per config; the hard set has three.
- Most coding tasks passed at every config, so the study did not find failure rates for them. "Effort did not help" may partly be a ceiling effect.
- Task briefs and answer keys were written by Sonnet and checked by another Sonnet pass and an automated oracle. People did not check them.
- Dollar figures depend on assumed cache-write and cache-read multipliers.

## Folder layout

```
analysis/FACTS.md                   Single source of numbers for the report
data/README.md                      Data dictionary for the files below
data/coding/runs.jsonl              One record per coding run (272 rows)
data/coding/tasks.json              Summary of the 22 coding tasks (not the runnable task file)
data/coding/costs.json              Per-config totals and Wilson 95% intervals
data/coding/denials_hard_set.json   Denied tool calls in the hard set, by category
docs/                               Report source; figures go in docs/assets/figures/
experiments/01-reasoning-ladder/    Reasoning without tools: gen.py, run.py, analyze.py,
                                    variants.py, task files, results.jsonl, console logs
harness/cmux-subagent/              claude-pane.sh (launch and collect a sub-agent in a pane),
                                    read_transcript.py, SKILL.md
harness/coding-bench/               bench.py (run and grade coding tasks), task builders,
                                    oracle and admission checks, analysis scripts,
                                    settings/ (permission allow and deny files)
```

## Reproduce

Requirements: Claude Code CLI with access to the two models, `cmux`, `uuidgen`, Python 3, and, for the coding bench, `git` and `uv`. Every run calls the API and costs money. Results will differ from the published ones on re-runs.

The pane helper must sit where the scripts expect it. Both `run.py` and `bench.py` call `~/.claude/skills/cmux-subagent/claude-pane.sh`.

```bash
mkdir -p ~/.claude/skills/cmux-subagent
cp harness/cmux-subagent/* ~/.claude/skills/cmux-subagent/
```

### Reasoning ladder (fully reproducible)

Ten levels for each of three families: multiplication, code trace, and seating logic. Tools are forbidden in every prompt, and any run that uses a tool is flagged.

```bash
cd experiments/01-reasoning-ladder
python3 gen.py tasks.json            # stage 1: levels 1-5
python3 gen.py tasks2.json 2         # stage 2: levels 6-10 (fixed seeds)
python3 run.py tasks.json results.jsonl <workers> <timeout-seconds>
python3 run.py tasks2.json results.jsonl <workers> <timeout-seconds>
python3 analyze.py results.jsonl
```

`run.py` resumes from existing rows in `results.jsonl` and skips a chain after two failures in a row. The study's worker count and timeout are not recorded in the repo. Regenerating the task files has not been checked against the committed ones.

### Coding bench (needs your own target repo)

The original target is private and is not included. To run the bench, you need a Python repository with a test suite that runs under `uv run pytest`.

1. Clone your target repo and set `BENCH_REPO` to its path. Without it, `bench.py` uses `~/.cache/coding-bench/repos/target`.
2. Copy the settings: `mkdir -p ~/.cache/coding-bench/settings && cp harness/coding-bench/settings/bench.json ~/.cache/coding-bench/settings/`. Replace the `/Users/<you>` paths in that file with your home folder.
3. Accept folder trust once for each slot folder: `harness/coding-bench/open_trust_panes.sh`. Without this, the agents stop at the trust prompt.
4. Write a task file. `data/coding/tasks.json` is a summary, not the input. `bench.py` needs each task's base commit, prompt text, expected answers, and grading fields. The task builders (`prep_build.sh`, `prep_hard.sh`, `build_tasks.py`, `build_hard_tasks.py`, `admit.py`, `oracle.py`) were written for the private repo and need to be rewritten for yours.
5. Run:

```bash
python3 -I harness/coding-bench/bench.py --tasks <task-file> --out <results.jsonl> \
  --configs sonnet:high,haiku:medium --trials 1 --workers 8 --mode slots
```

Set `BENCH_IGNORE_TESTS` to skip test files that need live services.

The analysis scripts do not read the published `runs.jsonl` correctly. They use field names from a different version of `bench.py`. See `data/README.md`, "Known issues."

## Privacy and paths

- The target repo is private. This repo contains no code, file or folder paths, function, class, or test names, or commit messages from it. Tasks are named by ID, for example `feature-7-e34653c`.
- Some settings and scripts contain paths written as `/Users/<you>`. Replace them with your own home folder before running anything.
- Data files describe tasks in generic terms only.
