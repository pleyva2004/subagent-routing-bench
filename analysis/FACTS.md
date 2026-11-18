# Facts pack

The single source of numbers for the technical report. Every number here was checked against the data in `data/` and `experiments/`. If the report needs a number that isn't here, compute it from those files and say how.

Study dates: November 16–17, 2026. Models: Claude Haiku 5.5 (`claude-haiku-5-5`) and Claude Sonnet 5.5 (`claude-sonnet-5-5`). Effort levels: `low`, `medium`, `high`, `xhigh`, `max`. "Config" means one model at one effort level. No Opus sub-agents were used.

## 1. Harness

### Sub-agents in cmux panes

- An orchestrating Claude Code session launches each sub-agent as a separate interactive Claude Code session in a cmux terminal pane, through `harness/cmux-subagent/claude-pane.sh`. `launch` prints a handle; `collect` waits for the reply and closes the pane. The first agent opens one column beside the orchestrator, and later agents stack inside it.
- Each session gets a fixed session ID. The reply is read from the session transcript (the last turn-end entry), not scraped from the screen, so long replies come back whole.
- The prompt goes to the pane through a temp file, because cmux drops typed input past about 1,024 characters.
- Options added for this study: `--cwd` (start folder), `--permission-mode` (refuses `bypassPermissions`), `--settings` (a settings file, used for allow and deny rules).

### Running coding agents

- Each run gets a fresh git worktree of the target repo at the task's base commit, with dependencies synced, in one of 8 reusable "slot" folders. Up to 8 runs at a time.
- Agents run in `dontAsk` permission mode with an allowlist: running tests, read-only git, search commands, and file edits inside the slot folders. Denied: commits, pushes, branch switches, resets, stashes, sub-agents, and web access. Anything not allowed is denied without stopping the run.
- Folder trust: Claude Code asks whether to trust any new folder, and trust isn't inherited from parent folders. It doesn't ask in an empty folder. Accepting trust inside a git worktree saves it on the main repository, which then covers every worktree of that repository. The orchestrator's auto-mode safety classifier blocked it from accepting the trust prompt on the user's behalf; the user accepted it once.
- Grading happens after the agent exits, from the worktree, not from the agent's reply:
  - Fix and feature tasks: restore the original tests, add the hidden tests, run the full suite (excluding two test files that need live network services). Pass means no failures and every hidden must-pass test passing.
  - Locate tasks: the reply must list exactly the expected set of `file:line` locations.
  - Review tasks: each planted bug counts as found if the reply cites its file within 3 lines. After the pilot, extra reports on a diff with planted bugs are recorded but don't fail the run; a clean diff must come back with no reports.
- Recorded per run: status, tokens by type, tool calls, denied tool calls, agent time, and whether the agent claimed the tests passed.

### Building and validating tasks

- The target repo is a private Python project of about 150 files (an agent runtime with a daemon, JSON-RPC, WebSocket and HTTP transports, model adapters, tools, a SQLite store and skill selection), with a suite of about 140 tests that runs in about 12 seconds. Its code is not published here.
- Feature tasks replay real commits: the agent starts at the commit's parent, gets a written ticket (brief), and is graded by the commit's own tests. Admission rule: the commit's new tests fail before the change and pass after it, and every other test passes both times.
- Briefs, planted bugs, bug reports and review answer keys were written by Sonnet `high` sub-agents. Each brief was then checked line by line against the hidden tests by a Sonnet `xhigh` verifier, which fixed what it found:
  - Easy set: 2 of 4 briefs passed unchanged; 2 leaked internal helper names, which were removed.
  - Hard set: 3 of 5 passed unchanged; one gained 2 missing interface details and one gained 4 (including a return type a test asserts).
- One hard task was rejected and rebuilt: its writer re-planted the easy set's bug and named the buggy function in the report.
- An oracle self-test ran on all 22 tasks: the known-correct answer must pass and doing nothing must fail. It caught one bad task (a feature whose commit also added a dependency); feature tasks now start with the commit's dependency changes applied. The fix was in place before any run of the two affected tasks.

## 2. Experiment 1: reasoning without tools

Design: three task families with exact answers, 10 difficulty levels each, 8 configs (both models at `low`, `medium`, `high`, `xhigh`), one trial per cell. Tools were forbidden, and every transcript was checked: only thinking and text blocks appeared. Levels 6–10 ran as per-family chains that stopped after two failures in a row, counting a failure at level 5; so Haiku `low`'s trace levels above 250 statements never ran.

| Family | What it tests | Levels 1–5 | Levels 6–10 |
|---|---|---|---|
| Multiplication | Exact long arithmetic: two numbers of N digits each | 4, 6, 8, 10, 12 | 16, 20, 25, 32, 40 |
| Code trace | Mentally running generated Python over 4 variables (modular arithmetic, swaps, if/else) | 10, 20, 40, 80, 160 statements | 250, 400, 600, 900, 1,300 |
| Seating logic | A seating puzzle with a minimal set of clues and exactly one solution | 4–8 people | 9–13 people |

Results:

- Seating logic: every config solved every level, up to 13 people.
- Multiplication: every config solved up to 40 × 40 digits, except Haiku `low` (first failure at 25 digits) and Haiku `medium` (first failure at 32). Both wrong answers had the right length and were correct except for one span of 8 to 10 digits, which held the right digits in the wrong order, and both configs then solved the 40-digit problem.
- Code trace separated the configs clearly. (Multiplication affected only Haiku `low` and `medium`, and not consistently.)

| Config | Longest solved before first failure | Longest solved at all | Notes |
|---|---|---|---|
| Haiku `low` | 80 | 80 | Failed 160 and 250 |
| Haiku `medium` | 250 | 250 | Failed 400 and 600 |
| Haiku `high` | 20 | 250 | Failed 40 (shortcut), then 400 and 600 |
| Haiku `xhigh` | 20 | 400 | Failed 40 (same shortcut) and 600; at 900 declined to answer |
| Sonnet `low` | 400 | 400 | Failed 600 and 900 |
| Sonnet `medium` | 400 | 400 | Failed 600 and 900 |
| Sonnet `high` | 400 | 900 | Failed 600, solved 900, failed 1,300 |
| Sonnet `xhigh` | 1,300+ | 1,300 | Never failed; the 1,300-statement run used 95k output tokens and 439 s |

Failure analysis:

- At 40 statements, Haiku `high` and `xhigh` gave the same wrong answer. Both treated a run of three swaps of one pair of variables followed by one swap of a different pair as "four swaps that cancel out". Haiku `low` and `medium` traced each line and were right.
- At 600 statements, Sonnet `low` and `medium` gave the same wrong answer. No single skipped or misread statement explains it; the cause is unknown. Haiku `high`'s wrong answer at 600 is explained exactly by skipping one statement.
- At 900 statements, Haiku `xhigh` used 216k output tokens and 680 s, noticed it had re-traced a block it had already done, and declined to answer. Every other failure gave a definite answer.
- Cost of effort on the 400-statement trace: Sonnet `low`, `medium` and `high` used 8–9k output tokens in 43–46 s; Sonnet `xhigh` used 28k in 131 s; Haiku `xhigh` used 70k in 214 s.
- Both stages: 229 runs, 1.71 million output tokens.

## 3. Experiment 2: coding, easy set

Design: 12 tasks, all 10 configs (both models at all five effort levels), one trial each: 120 runs. Sonnet `high` and Haiku `medium` ran first as the pilot.

| Tasks | What they are |
|---|---|
| 3 locate | Find definitions and call sites. Easy; with same-named decoys; across Python and HTML |
| 2 fix | One planted bug each, with a visible failing test. One bug sits near its symptom; one is two layers below it |
| 4 feature | Replays of real commits: 1 file and 33 lines added (6 hidden tests); 2 files and 25 lines (4); 5 files and 41 lines (4); 8 files and 114 lines (3) |
| 3 review | Real diffs with 0, 1 and 2 planted bugs |

Results:

- Every config passed every locate, fix and feature task. One Haiku `high` locate failure was caused by the harness (the allowlist denied a chained `echo`, and the agent gave up); after widening the allowlist, a rerun passed. Both rows are in the data, the first marked superseded.
- Only the 2-bug review separated configs. Every Haiku level, `low` through `max`, and Sonnet `xhigh` missed a planted shutdown-loop bug. Each reported a real, pre-existing flaw nearby instead. Sonnet `low`, `medium`, `high` and `max` found both planted bugs.
- Totals: Sonnet `low`, `medium`, `high` and `max` 12/12; Sonnet `xhigh` 11/12; every Haiku level 11/12.
- During the pilot, most "false alarms" in reviews turned out to be real defects already in the original commits (two were confirmed by reading the code: a rendering gap and a shutdown-status bug). The review rule was changed and the pilot regraded from saved replies.
- No false "tests pass" claims, but no fix or feature failed, so this wasn't tested.

Cost per successful task (API-equivalent dollars) and agent time per run:

| Config | $ per success | Output tokens (12 tasks) | Agent s per run |
|---|---|---|---|
| Haiku `low` | 0.017 | 66k | 34 |
| Haiku `medium` | 0.025 | 95k | 48 |
| Haiku `high` | 0.040 | 154k | 68 |
| Haiku `xhigh` | 0.092 | 324k | 130 |
| Haiku `max` | 0.339 | 910k | 332 |
| Sonnet `low` | 0.118 | 27k | 35 |
| Sonnet `medium` | 0.116 | 30k | 24 |
| Sonnet `high` | 0.164 | 45k | 34 |
| Sonnet `xhigh` | 0.258 | 91k | 64 |
| Sonnet `max` | 0.895 | 549k | 327 |

## 4. Experiment 3: coding, hard set

Design: 10 harder tasks, 5 configs (Haiku `low`; Sonnet `low`, `medium`, `high`, `xhigh`), 3 trials each: 150 runs, finished in 27 minutes on 8 slots.

| Task | What makes it hard |
|---|---|
| Fix: hidden and far | A storage-layer serialization option drops each stored event's type. It shows only when replaying a session over WebSocket; the 5 tests that would catch it (in 4 files) are hidden |
| Fix: two bugs | A misspelled environment variable and a renamed query parameter cause one symptom. Only one has a visible failing test, so fixing it makes the suite pass while the reported problem remains |
| Fix: misleading report | A model-adapter bug breaks tool-call arguments for one provider; the report guesses the tool registry is at fault; the catching test is hidden |
| Feature: large | Commit replays: 4 files, 188 lines added, 4 hidden tests; 9 files, 196 lines, 7 tests; 15 files, 602 lines, 32 tests |
| Feature: terse | Two easy-set features (5 and 8 files) briefed in 70 and 115 words |
| Review: subtle | Real diffs with 2 and 3 planted bugs (missing awaits, error handling, edge cases) that the existing tests don't catch |

Results:

| Config | Passed as graded | Passed with the ambiguous review bug set aside | Code changes (fix and feature) | $ per success | Output tokens (30 runs) | Agent s per run |
|---|---|---|---|---|---|---|
| Haiku `low` | 29/30 | 30/30 | 24/24 | 0.041 | 427k | 78 |
| Sonnet `low` | 26/30 | 29/30 | 23/24 | 0.207 | 168k | 36 |
| Sonnet `medium` | 27/30 | 29/30 | 24/24 | 0.210 | 194k | 43 |
| Sonnet `high` | 27/30 | 30/30 | 24/24 | 0.259 | 244k | 58 |
| Sonnet `xhigh` | 27/30 | 30/30 | 24/24 | 0.532 | 606k | 145 |

- Every config solved all three fixes, both terse features and the 4- and 9-file features in all 3 trials.
- The 15-file, 602-line feature: Sonnet `low` failed once (7 failing tests).
- The 3-bug review: none of the 12 Sonnet runs, at any effort level, flagged the third planted bug, an error handler broadened to catch every exception, which turns parsing errors and code bugs into a quiet "model error" instead of a crash. That change is arguably a robustness choice rather than a defect, and the review prompt asked only for real runtime defects, so the report counts results both ways. Eleven Sonnet runs found the other two bugs; one Sonnet `medium` run found only one of them. Haiku `low` flagged the third bug in 2 of 3 runs.
- False success claims: none confirmed. The one flagged run was the harness anomaly below; the one real failure on a fix or feature didn't claim success.
- Denied tool calls in the hard set: 189, of which 154 were chained commands (`;`, `||`, pipes, loops) that an allowlist can't match, 15 other `uv` subcommands, 15 `sed -i`, 3 `mkdir`, 1 `python3`, 1 `mv`. An earlier count of 234 double-counted tool results that transcripts repeat in logging entries. Agents retried with simpler commands or the Edit tool; no failure was traced to a denial.

Harness problems found and fixed during this experiment:

- In one Sonnet `high` run of the 602-line feature, a hidden test file was never collected during grading. The run was graded a failure and flagged as a false success claim. The grader now verifies the restored hidden tests, treats a hidden test file with no results as a harness error, and retries. A fresh sample passed; the original row is kept and marked superseded.
- Saved diffs didn't include new files, so that run couldn't be replayed. Diffs now include new files.
- The claim parser read an earlier baseline count instead of the final run's. It now uses the largest pytest-style count in the reply.

## 5. Cost

- Prices used (first-party API, November 2026): Sonnet 5.5 $2.00 per million input tokens, $10.00 output, $0.10 cache reads. Haiku 5.5 $0.10 input and $0.50 output for prompts up to 100K tokens, $0.50 and $2.50 beyond. Assumed where not listed: cache writes at 1.25× the input rate; Haiku cache reads at 0.1× the input rate.
- Dollars are API-equivalent and computed per request from each transcript, applying Haiku's long-prompt tier per request. They are not subscription usage.
- Haiku costs about 1/20 as much per token as Sonnet. It used about 2.5× the output tokens and about 2× the agent time of Sonnet `low`, and still cost about 1/5 as much per successful coding task.
- Above `medium`, effort added cost with no accuracy gain we could detect (nearly every task passed at every config): Sonnet `xhigh` cost about 2.2× (easy set) and 2.6× (hard set) Sonnet `low` per success; `max` cost about 8× (Sonnet) and 19× (Haiku) its `low` level on the easy set.
- Whole study: the coding runs cost about $24 (easy set, 120 runs) and $34 (hard set, 150 runs) at API prices.

## 6. Routing table adopted

The cmux-subagent skill's routing table was rewritten from these results:

| Slice | Model and effort |
|---|---|
| Lookups | Haiku `low` |
| Code changes (fixes, features up to ~15 files) | Haiku `low`; Sonnet `medium` when wall-clock time matters |
| Code review | Haiku `low` and Sonnet `medium` in parallel; merge findings |
| Long exact reasoning without tools | Sonnet `xhigh` |
| `max` | Only on explicit request |

Rules, with what each rests on:

- Effort above `medium` bought nothing on coding tasks. Measured.
- Haiku above `medium` is not recommended. One trial each: `high` and `xhigh` took a wrong shortcut at 40 statements in the no-tools test, though `xhigh` solved 400 where `medium` stopped at 250; on coding they matched `low` at higher cost.
- A second model looks more useful than more effort. A handful of cases, with exceptions (section 7).
- Retry a failed Haiku change once on Sonnet `medium`. Untested.
- Outside what was measured, start with Sonnet `medium`. Judgment.

## 7. Uncertainty and models

Wilson 95% intervals for pass rates:

- One cell with 3 of 3 passes: 44–100%. 2 of 3: 21–94%.
- Code changes, pooled across both sets: Haiku `low` 30/30 (89–100%); Sonnet `medium` 30/30 (89–100%); Sonnet `low` 29/30 (83–99%).
- Hard set, all tasks as graded: Haiku `low` 29/30 (83–99%); Sonnet `low` 26/30 (70–95%); Sonnet `medium`, `high` and `xhigh` 27/30 (74–97%).

Modeling framework (proposed; the data are too saturated to fit most of it yet):

- Item response model: `P(pass | config c, task t) = σ(θ_c − b_t)`, with `θ_c = α_model + δ_effort + u_(model,task)`. The `u` term captures model-specific blind spots that persist across effort levels. The hardest task a config passes 80% of the time is `b = θ_c − ln 4`.
- Difficulty horizon for size-graded tasks: `P(pass) = σ(α_c − β_c · ln x)`, so the 50% horizon is `x₅₀ = e^(α_c / β_c)`.
- Cost per completed task: `c / p` when failures are detected and retried. A fallback chain (Haiku first, Sonnet on failure) costs `c_H + (1 − p_H) · c_S`: about $0.046 per task, with the chain completing 99.7% of tasks (Haiku `low` alone passed 29 of 30), against $0.21 per completed task for Sonnet `medium` alone ($0.189 per attempt at 90% success). With undetected failures, minimize `c + (1 − p) · L`, where L is the cost of a missed defect.
- Two reviewers miss a bug together with probability `q_A · q_B` only if their misses are independent. What was seen: some misses repeated across every effort level of one model (every Haiku level missed the same review bug; no Sonnet run at any of four levels flagged the catch-all handler), and the other model usually caught them (Sonnet `low`, `medium`, `high` and `max` found Haiku's miss; Haiku `low` flagged the catch-all in 2 of 3 runs). There were exceptions both ways: Sonnet `xhigh` shared Haiku's miss, and one Haiku `low` run shared Sonnet's. In the reasoning test, pairs of effort levels within a model gave identical wrong answers. This is a handful of cases, not an estimate.

## 8. Limitations

- One private repo, one language; 22 coding tasks; one trial per cell in the 10-config sweep, three in the hard set.
- Almost every task passed at every config, so failure thresholds for coding were not found, and "effort didn't help" may be a ceiling effect.
- The error-correlation pattern rests on a handful of cases and has exceptions in both directions.
- Dollar figures were computed from session transcripts, which aren't published, so they can't be re-derived from this repository alone.
- Tasks, briefs and answer keys were written by Sonnet. One planted review bug was arguably not a bug; answer-key validity was checked by the oracle and by spot reads from the orchestrating model, not by people.
- Conditions changed during the study: the allowlist was widened partway through the 10-config sweep, and one grading anomaly was replaced by a fresh sample.
- Agents loaded the user's global Claude Code instructions, as they would in real use.
- Dollar figures depend on assumed cache multipliers, not billing data.
- Model versions are specific to November 2026.
