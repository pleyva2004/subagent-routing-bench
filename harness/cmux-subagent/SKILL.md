---
name: cmux-subagent
description: Run a one-shot Claude sub-agent in a cmux split pane and read its reply. Use when the user asks to launch a sub-agent, run Claude in a pane, open a cmux panel with a prompt, or run parallel sub-agents in cmux.
---

# cmux sub-agent

Runs one prompt on one model in a visible cmux split, prints the reply, and closes the pane.

## Models

- Haiku 5.5 (`claude-haiku-5-5`) or Sonnet 5.5 (`claude-sonnet-5-5`) only.
- The script accepts any Haiku or Sonnet model id (`haiku`, `sonnet`, `claude-haiku-*`, `claude-sonnet-*`). Use the 5.5 versions.
- Never Opus for sub-agents.
- The script rejects any model other than Haiku or Sonnet (exit 2).

## Run one sub-agent

Call the helper by its full path:

```
/Users/<you>/.claude/skills/cmux-subagent/claude-pane.sh <model> "<prompt>" [timeout_seconds] --effort <level>
```

The reply comes from the session transcript, not the screen, so long replies come back whole. The pane is still shown while the agent runs. The timeout is whole seconds, at most 6 digits.

The script:
1. Opens a split below the newest open sub-agent pane if there is one, otherwise a new column to the right of the calling pane, running Claude with the model, effort, prompt, and a known `--session-id` as startup arguments. The prompt is written to a temp file, which the pane's shell reads into Claude's startup argument, so any length works. The pane starts in the directory of the pane it splits from.
2. Polls until the session transcript has its turn-end entry, up to the timeout (default 120s).
3. Prints the final message from the transcript.
4. Force-closes the pane.

## Working folder and permissions

Optional on both `launch` and the one-shot form:

- `--cwd <dir>`: start Claude in `<dir>` instead of the calling pane's folder. Claude must already trust that folder. Trust isn't inherited from parent folders. In an untrusted folder the pane stops at the trust prompt, and `collect` exits 1 after 60 seconds and shows the prompt.
- `--permission-mode <mode>`: `acceptEdits`, `auto`, `manual`, `dontAsk`, or `plan`. The script refuses `bypassPermissions`.
- `--settings <file>`: an extra Claude settings file, such as `{"permissions": {"allow": ["Bash(uv run pytest:*)"]}}`.

For unattended agents, use `dontAsk` with an allowlist in `--settings`: anything not allowed is denied instead of waiting at a prompt. Some read-only commands, such as `pwd`, run without an allow rule.

## Choosing model and effort

Choose both for each agent at launch. Always pass `--effort`. If you omit it, the agent inherits the user's default effort, which could be anything.

This table comes from measurements made in November 2026 on one Python repo (augustine, about 150 files): 222 coding runs across every model and effort level, covering lookups, bug fixes, features touching 1 to 15 files, and code reviews, plus a no-tools reasoning test. Costs are API-equivalent dollars per successful task. The harness and results are in `~/.cache/coding-bench/`.

| Slice | Model and effort | What was measured |
|---|---|---|
| Lookups: find definitions and call sites, extract a value, yes/no checks | Haiku `low` | Every config got them right; Haiku costs about 1/20 as much per token |
| Code changes: bug fixes, features up to ~15 files, test-backed refactors | Haiku `low` | 30/30 passed, at $0.04 per success on the hard tasks, about 1/5 of Sonnet `low` |
| Code changes when wall-clock time matters | Sonnet `medium` | 30/30 passed, about 2x faster than Haiku `low` (43 s vs 78 s per run), about 5x the cost |
| Code review | Haiku `low` and Sonnet `medium` in parallel on the same diff; merge their findings | Each model missed a different planted bug, at every effort level |
| Long exact reasoning with no tools, such as tracing code by hand | Sonnet `xhigh` | The only config that traced 1,300 statements correctly; Sonnet `low` to `high` failed at 600 |
| `max` | Only when the user explicitly asks for it | 8x to 20x the cost of `low`, with no accuracy gain in any test |

- Effort above `medium` bought nothing on coding tasks: Sonnet `xhigh` cost about 2.5x Sonnet `low` per success, with no gain.
- Don't run Haiku above `medium`. At `high` and `xhigh` it took wrong shortcuts on easy tasks and gained nothing.
- A second model beats more effort. Each model repeated its own mistakes at every effort level, so for a result that looks wrong, or a check that matters, re-run the slice on the other model instead of raising effort.
- If a Haiku code change fails its tests, retry it once on Sonnet `medium`.
- Outside what was measured (much larger or unfamiliar codebases, open-ended design work), start with Sonnet `medium`.
- If a Sonnet slice seems to need more than `xhigh`, do it inline instead of delegating.

## Exit codes

- `0`: complete, non-empty reply.
- `1`: timeout (partial reply on stdout), empty reply, no transcript, `transcript reader failed`, or a session id or split failure.
- `2`: bad arguments or a missing `read_transcript.py`; no pane opened.
- `130`: interrupted; pane closed.

Check the exit code before using the reply.

## Run several in parallel

The layout is automatic: the first agent opens one vertical column beside the calling pane, the rest stack inside it, and one-shot runs follow the same rule.

`launch` prints a handle, `<surface-uuid>@<session-id>`. Pass it unchanged to `--from` and `collect`.

First define the helper as a shell variable:

```
H=/Users/<you>/.claude/skills/cmux-subagent/claude-pane.sh
```

1. Open the first agent, and keep its handle:
   `A=$("$H" launch <model> "<prompt 1>" --effort <level>)`
2. Open each remaining agent the same way; it stacks in the column:
   `B=$("$H" launch <model> "<prompt 2>" --effort <level>)`
3. Collect each agent in turn. Each waits, prints its reply, and closes its panel:
   `"$H" collect "$A"`, `"$H" collect "$B"`, and so on.

Each agent gets its own model and effort, chosen per slice with the table above.

Don't pass `--from` or `--dir` unless you need a different layout; they are overrides only. Panes opened with `--from` or `--dir` are not tracked, so later automatic launches don't stack under them.

Check each `launch` exit code too. If a launch fails, collect the agents already launched, or close their panes.

Check each `collect` exit code before using its reply.

Interrupts:
- Interrupting `launch` exits 130 and leaves no lock behind. A pane opened by an interrupted one-shot run, before `collect` starts, can stay open; close it with `cmux close-surface --surface <surface-uuid> --force`.
- Interrupting `collect` (Ctrl-C, TERM, or HUP) closes that agent's pane and exits 130.
- Other launched panes stay open. Close each with `cmux close-surface --surface <surface-uuid> --force`, where `<surface-uuid>` is the part of its handle before `@`.
- `kill -9` can't be caught and leaves the pane open.

## Failure handling

- A non-zero exit means the run failed (an empty reply is exit 1). Report it; don't use the output as a complete reply.
- Don't chain `sleep` commands to wait on a pane. The script already polls.
- Interrupts: see the Interrupts list above. Interrupting `collect` closes that agent's pane, but not other launched panes, and `kill -9` closes nothing.
- No transcript: the script gives up after 60 seconds (or the timeout, if shorter) when no transcript appears. It prints what the pane showed, usually a trust-folder or permission prompt. Starting panes from a folder Claude already trusts avoids the trust prompt.
- A timeout also prints what the pane showed, which can reveal a permission prompt.
- Prompts of any length and content are fine as long as they aren't empty: the script passes the prompt through a temp file, not the command line.

## Files

- `claude-pane.sh`: the helper you call.
- `read_transcript.py`: reads the session transcript for `claude-pane.sh`.
- Both must stay in the same folder.

## Checks

- After a batch, run `cmux list-panes` and confirm only the main pane remains open.
