# A subagent's second report is dropped

**Status:** open

**Component:** Claude Code harness (SubagentHandback, SendMessage, task notifications). Not this repo's code.

**Reproduces on:** Claude Code 2.1.284. Reported upstream with `/feedback`, receipt
`260e8f59-b601-4b81-b896-e7cf15d01045`.

## Observed behavior

A background subagent sends its report with SubagentHandback while background work of its own (a Monitor, or a
`run_in_background` command) is still running. The harness still counts the subagent as running. A SendMessage from
the coordinator then joins that same run instead of starting a new one. When the subagent finishes the follow-up and
calls SubagentHandback again, the call is refused:

```text
Nothing was sent: your report was already delivered (SubagentHandback delivers one report). Use SendMessage for
anything further, then stop.
```

The subagent writes its report as plain text instead, which never reaches the coordinator. The coordinator then gets a
"finished" notification that points at the first report:

```text
This agent's report was delivered to you as a message from "<agent>" (its SubagentHandback call). Read it there; it is
not repeated here.
```

A coordinator waiting for the second report has nothing left to wake it. In `/work-queue` this stalls the run until the
user nudges it.

## First seen

On 2026-10-05, in the `/work-queue` session `92641421-6819-4084-a923-5c16e036397f`,
worktree `gowork`. The Phase 76.4 implementer's review fixes were done at
14:23Z, but its report was refused. The coordinator waited until the user
nudged it at 16:56Z, 2.5 hours later. The full analysis is in the session
report `20261005-subagent-second-report-dropped.md`.

## Repro

Run this from any Claude Code session, with auto mode allowing SendMessage:

1. Spawn a background subagent with this prompt: "Run `sleep 300` with `run_in_background: true` and do not wait for
   it. Deliver your report with the text `REPORT-1`, then end your turn. If you later receive a message from the
   coordinator, follow it and deliver a second report with the exact text it asks for. If the delivery tool returns an
   error, copy the exact error text into your final plain-text reply."
2. When `REPORT-1` arrives, and before the five minutes are up, SendMessage the subagent: "Deliver a second report with
   the exact text `REPORT-2`."
3. Wait for the subagent's "finished" notifications.

**Still broken:** `REPORT-2` never arrives, the notification points at the earlier report, and the subagent transcript
(the notification's `<output-file>`) shows the refusal above.

**Fixed:** `REPORT-2` arrives as a message from the subagent.

## Workarounds in this repo

These landed with this bug note.

| File | Workaround | When the bug is fixed |
|---|---|---|
| `claude/agents/implementer.md` | Finish or stop background work before reporting | Keep. A report sent while background work can still change files races with the coordinator's commit |
| `claude/agents/implementer.md` | If SubagentHandback refuses the report as already delivered, send it with SendMessage to `main` | Remove |
| `claude/commands/work-queue.md` | Arm a fallback timer while waiting on an agent | Keep. Any lost notification stalls a run that has nothing else to wake it |
| `claude/commands/work-queue.md` | Use `git diff --stat`, not `git status`, to tell whether an agent's edits landed | Keep. `git status` cannot show new edits to files that were already modified |
| `claude/commands/work-queue.md` | When a "finished" notification points at an earlier report while a follow-up is unanswered, read the end of the agent's transcript | Remove |

Each line to remove is marked with an HTML comment that names this file.
