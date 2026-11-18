# Data dictionary

This file describes:

- `data/coding/runs.jsonl`, `data/coding/tasks.json`, `data/coding/costs.json`, `data/coding/denials_hard_set.json`
- `experiments/01-reasoning-ladder/results.jsonl`

Where a value is computed or inferred, the text says so. Field meanings for coding runs come from `bench.py`'s logic and the study's notes in `analysis/FACTS.md`.

## Conventions

- `.jsonl` files hold one JSON object per line. The other files are single JSON documents.
- Money is US dollars, API-equivalent. It is computed from transcript token counts at the prices in FACTS §5. It is not billing data.
- Times are seconds, unless the field name ends in `_ms`.
- Token fields are counts.
- Intervals and rates are fractions from 0 to 1.
- Coding files use `haiku` and `sonnet`. The reasoning file uses `claude-haiku-5-5` and `claude-sonnet-5-5`.

---

## data/coding/runs.jsonl

One record per coding run. 272 records on 272 lines.

| Set | Lines | Phase values | Records | Effective runs |
|---|---|---|---|---|
| easy | 1–24 | `easy-pilot` | 24 | 24 |
| easy | 25–120 | `easy-sweep` | 96 | 95 (one superseded) |
| easy | 121 | `easy-rerun` | 1 | 1 |
| hard | 122–271 | `hard` | 150 | 149 (one superseded) |
| hard | 272 | `hard-rerun` | 1 | 1 |

Effective runs: 120 easy (12 tasks × 10 configs, one trial) and 150 hard (10 tasks × 5 configs × 3 trials). Counts are from reading the file, not from a script.

### Fields on every row

| Field | Units or values | Meaning |
|---|---|---|
| `task` | task ID | Matches `id` in `tasks.json`. Example: `review-5-4dd880a`. |
| `type` | `locate`, `fix`, `feature`, `review` | Kind of task. |
| `level` | integer | Ordinal label within the task set. Labels repeat across types, so this is not a calibrated difficulty scale. |
| `set` | `easy`, `hard` | Task set. |
| `phase` | see table above | Which pass of the study wrote the row. |
| `model` | `haiku`, `sonnet` | Model family. The bench maps these to `claude-haiku-5-5` and `claude-sonnet-5-5`. |
| `effort` | `low`, `medium`, `high`, `xhigh`, `max` | Effort level. The easy pilot ran Sonnet at `high` and Haiku at `medium` only. |
| `trial` | integer | 1 for every easy row. 1–3 for the hard set. |
| `status` | `pass`, `fail` | Outcome. These are the only values in this file. The script can also write `timeout_or_err`, `launch_fail`, or `harness_error`; none appear here. |
| `tokens_in` | tokens | Input tokens the API reports (`input_tokens`). Small here because most input is cache reads. Summed over the run's assistant messages, counting each message ID once (`bench.py`). |
| `tokens_cache_write` | tokens | `cache_creation_input_tokens`, same summing rule. |
| `tokens_cache_read` | tokens | `cache_read_input_tokens`, same summing rule. |
| `tokens_out` | tokens | `output_tokens`, same summing rule. |
| `tool_calls` | count | `tool_use` blocks in the run's assistant messages. Includes denied calls. |
| `denied_tool_calls` | count | Tool results marked as errors whose text contains "denied" or "permission". This is a text match, so it is a heuristic. |
| `agent_seconds` | seconds | Agent running time. The code stores this as turn durations in milliseconds (`turn_ms`). The analysis script divides by 1000. I did not confirm the conversion against the data. |
| `wall_seconds` | seconds | Elapsed time from the start of worktree setup to the end of grading. Includes dependency sync. Greater than `agent_seconds` in every row I read. |
| `cost_usd` | dollars | API-equivalent cost of the run (FACTS §5). The script that computes it is not in this repo. |

### Pass rules (from FACTS §1 and `bench.py`)

- **locate:** the reply lists exactly the expected `file:line` locations.
- **fix and feature:** after the original tests are restored and hidden tests are added, the full suite has no failures and every required test passes.
- **review:** each planted bug is cited in its file within 3 lines. For a clean diff (no planted bugs), pass means the reply has no reports.

### Fields on locate rows

| Field | Units | Meaning |
|---|---|---|
| `found` | count | Expected locations the reply got right. |
| `wrong` | count | Reported locations that are not in the expected set. |
| `missed` | count | Expected locations the reply did not report. |

### Fields on fix and feature rows

| Field | Units | Meaning |
|---|---|---|
| `tests_run` | count | Tests in the grading run, after restoring tests and adding hidden ones. Varies by task, because each task starts from a different commit. |
| `failures` | count | Tests that failed or errored in the grading run. |
| `hidden_not_passing` | count | Required tests that did not pass. Inferred from `bench.py`'s `must_pass_missing` list. |
| `files_changed` | count | Files that differ from the base commit, including new files. |
| `src_files_outside_reference` | count | Changed source files not in the task's reference list. Inferred from `bench.py` and `build_tasks.py`. For feature tasks the reference is the real commit's source files. For fix tasks it is the planted bug's file. |
| `test_files_touched` | count | Changed files under the test folder, counted before the original tests are restored. Non-zero means the agent edited tests. |
| `claimed_passed` | count or null | The passing-test count the reply reports, taken from its last pytest-style summary. Null when the reply has no such summary. This is the agent's claim, not a measurement, and it often differs from `tests_run`. Example: a feature run with `tests_run` 140 and `claimed_passed` 176. |
| `claimed_all_pass` | boolean | True if the reply's last summary shows no failures, or says all tests pass. |
| `false_success_claim` | boolean | True if `claimed_all_pass` is true and grading failed. The only true value is on a superseded row (see below). |

### Fields on review rows

| Field | Units | Meaning |
|---|---|---|
| `planted` | count | Planted bugs in the diff. Zero for the clean diff. |
| `planted_found` | count | Planted bugs cited in their file within 3 lines. |
| `extra_reports` | count | Reports that match no planted bug. Recorded for review. They do not fail a run. |

### Flags

- **`superseded`** (true, or absent). The row stays in the file as a record. Totals in `costs.json` and in FACTS leave it out. Each superseded row has a `superseded_reason` and is followed by a rerun of the same task, model, effort, and trial.

  | Line | Task | Config, trial | Reason | Rerun |
  |---|---|---|---|---|
  | 35 | `locate-2` | haiku `high`, trial 1 | Harness: the allowlist denied a chained `echo`, and the agent gave up. | Line 121 (`easy-rerun`), pass |
  | 207 | `feature-7-e34653c` | sonnet `high`, trial 2 | Harness: a hidden test file produced no results during grading. | Line 272 (`hard-rerun`), pass |

  The line 207 row also has `false_success_claim` true. Because it is superseded, no false success claim is counted in the results.

- **`regraded`** (true or false). Present only on the 24 pilot rows (`easy-pilot`). It is false on the 6 locate rows and true on the other 18. True means the row was scored again from its saved reply after the review scoring rule changed (FACTS §3). FACTS does not say whether any fix or feature grade changed when the pilot was regraded.
- **`note`**. Free text. Present on line 272 only: "fresh sample replacing the superseded trial 2".

### Checks

- Easy `haiku` `high`: the 12 effective rows sum to 153,914 output tokens (added by hand). That matches `costs.json`, which confirms it leaves out the superseded row and includes the rerun.
- Easy `haiku` `high` has 11 passing rows. The one failure is `review-3-0c62b65`.

---

## data/coding/tasks.json

An array of 22 objects: 12 easy, 10 hard. This is a summary. It is not the file `bench.py` reads. The runnable task file also holds base commits, prompt text, expected answers, and grading fields, which are not published.

| Field | On types | Units | Meaning |
|---|---|---|---|
| `id` | all | string | Task ID, for example `fix-2-far` or `feature-terse-43a549e`. |
| `set` | all | `easy`, `hard` | Task set. |
| `type` | all | `locate`, `fix`, `feature`, `review` | Task kind. |
| `level` | all | integer | Ordinal label within the set. |
| `description` | all | text | Short generic summary of the task. |
| `locations` | locate | count | Expected `file:line` locations. |
| `bugs` | fix | count | Bugs the task requires fixing. |
| `tests_that_must_pass` | fix | count | Tests that must pass after the fix. |
| `hidden_test_files` | fix | count | Hidden test files. This is a count, not a list. |
| `report_words` | fix | words | Length of the bug report given to the agent. |
| `reference_src_files` | feature | count | Source files the real commit changed. |
| `reference_lines_added` | feature | lines | Lines the real commit added. |
| `hidden_tests` | feature | count | Tests from the commit that the agent does not see. |
| `brief_words` | feature | words | Length of the ticket given to the agent. |
| `planted_bugs` | review | count | Planted bugs. Zero for the clean diff. |

---

## data/coding/costs.json

One object with 15 keys: `easy|<model>:<effort>` for 10 configs and `hard|<model>:<effort>` for 5. Each value summarizes the effective runs for one config.

| Field | Units | Meaning |
|---|---|---|
| `set` | `easy`, `hard` | Task set. |
| `config` | `model:effort` | Config. |
| `runs` | count | Effective runs. Superseded rows are excluded. |
| `passes` | count | Runs with `status` `pass`. |
| `pass_rate_95ci` | [low, high], fractions | Wilson 95% interval for `passes / runs`. Checked by hand: easy `haiku:low` (11/12) gives 0.646 to 0.985, which matches. |
| `code_change_passes` | count | Passing fix and feature runs. |
| `code_change_runs` | count | Fix and feature runs. |
| `cost_usd_total` | dollars | Sum of `cost_usd` over effective runs, rounded to 3 decimals. |
| `cost_usd_per_run` | dollars | `cost_usd_total / runs`. |
| `cost_usd_per_pass` | dollars | `cost_usd_total / passes`. Cost of failed runs is included in the numerator. |
| `output_tokens_total` | tokens | Sum of `tokens_out` over effective runs. |
| `agent_seconds_per_run` | seconds | Mean `agent_seconds` over effective runs. Naming-based; I did not re-derive it. |

---

## data/coding/denials_hard_set.json

One object. Each key is a category of denied tool call. Each value is a count of denied calls across the hard-set runs.

| Category | Count |
|---|---|
| chained command (`;`, `||`, pipe, or loop) | 188 |
| `uv` | 24 |
| `sed` | 15 |
| `mkdir` | 5 |
| `python3` | 1 |
| `mv` | 1 |

The categories sum to 234, which is the figure FACTS §4 uses. The file has no run IDs, so it cannot be traced to rows. See "Known issues" for a mismatch with `runs.jsonl`.

---

## experiments/01-reasoning-ladder/results.jsonl

One record per attempt, on 240 lines. 229 are runs. 11 are `skipped` rows, which have only the identity fields. The 229 matches FACTS §2.

### Fields

| Field | Units or values | Meaning |
|---|---|---|
| `model` | `claude-haiku-5-5`, `claude-sonnet-5-5` | Model ID. |
| `effort` | `low`, `medium`, `high`, `xhigh` | Effort level. No `max` in this experiment. |
| `task` | `<family>-L<level>` | Example: `trace-L6`. |
| `family` | `mult`, `trace`, `logic` | Task family. |
| `level` | 1–10 | Difficulty level. `gen.py` writes levels 1–5 to `tasks.json` and 6–10 to `tasks2.json`. |
| `status` | `pass`, `wrong`, `skipped` | Outcome. `skipped` means the chain stopped after two failures in a row, so the run was not made. `run.py` can also write `tool_violation`, `no_answer`, `timeout_or_err`, or `launch_fail`; none appear here. |
| `got` | text | The answer after normalization, cut to 80 characters. For `mult`, digits only. For `trace`, comma-separated integers. For `logic`, comma-separated capitalized names. Empty when the `ANSWER:` line was blank. One example is Haiku `xhigh` `trace-L9`, which declined to answer. |
| `want` | text | Expected answer, cut to 80 characters. |
| `rc` | integer | Exit status of `claude-pane.sh collect`. 0 on every run row here. |
| `wall_s` | seconds | Time from before launch to after collect returns. Includes pane setup. |
| `tool_uses` | count | `tool_use` blocks in the session. 0 on every run row here, so no run used a tool. |
| `output_tokens` | tokens | Output tokens summed over the session's assistant messages, counting each message ID once. |
| `duration_ms` | milliseconds | The last `turn_duration` value in the session transcript. This is in milliseconds. `wall_s` is in seconds. |
| `sid` | UUID | Claude Code session ID. The transcript is in `~/.claude/projects/*/<sid>.jsonl`, which is not in the repo. Present from line 121 on. Lines 1–120 do not have it. |

Skipped rows have only `model`, `effort`, `task`, `family`, `level`, and `status`.

### Level-to-parameter mapping (from `gen.py`)

The parameter is not stored in `results.jsonl`.

| Family | Levels 1–5 | Levels 6–10 | Parameter |
|---|---|---|---|
| `mult` | 4, 6, 8, 10, 12 | 16, 20, 25, 32, 40 | Digits in each factor |
| `trace` | 10, 20, 40, 80, 160 | 250, 400, 600, 900, 1,300 | Statements |
| `logic` | 4, 5, 6, 7, 8 | 9, 10, 11, 12, 13 | People in the seating puzzle |

Seeds are fixed: 20261116 for stage 1 and 20261117 for stage 2.

---

## Known issues

1. **Field names do not match the current harness.** The current `bench.py` writes `in`, `out`, `cache_write`, `cache_read`, `turn_ms`, `tool_uses`, `denied`, `must_pass_missing`, and `outside_expected`. The published file uses `tokens_in`, `tokens_out`, `tokens_cache_write`, `tokens_cache_read`, `agent_seconds`, `tool_calls`, `denied_tool_calls`, `hidden_not_passing`, and `src_files_outside_reference`. Some values also differ in shape: `test_files_touched` is a list in `bench.py` and a count here. `analyze_sweep.py` reads the `bench.py` names, so it will not read this file correctly. The published file came from a different version of the harness.
2. **The cost script is not in the repo.** `cost_usd` and the totals in `costs.json` cannot be re-derived from the code here. The prices and multipliers are in FACTS §5.
3. **The denial totals do not match.** The category file sums to 234. Summing `denied_tool_calls` over the 150 effective hard-set rows gives about 189 by hand. I did not confirm that sum with a script, and the two counts may use different rules. Check both with a script before quoting either.
4. **Unknown effect of the regrade.** It is not stated whether any fix or feature grade changed when the pilot was regraded.
5. **No `sid` in early reasoning rows.** Lines 1–120 of `results.jsonl` have no `sid`.
