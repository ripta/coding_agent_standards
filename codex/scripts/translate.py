"""Checked Codex adaptations of shared Claude workflows and role instructions.

Every platform-specific replacement must match exactly once. Source changes
require reviewing the adaptation rather than silently shipping stale behavior.
"""

REPLACEMENTS = {
    'work-queue': (
        ("""Start by calling the EnterPlanMode tool, before any other action. Skip this
step if the session is already in plan mode.
""",
         """Plan first using read-only exploration. Do not edit project files, reports,
stage, commit, or stash until the user explicitly approves the complete plan.
Do not try to switch collaboration modes. Present the plan in chat and ask
for explicit approval; wait for the user's reply. A checklist update, question
default, empty answer, timeout, or tool permission grant is not run approval.
Use an available question tool only within its supported mode and limits;
otherwise ask in chat. For multiple selections, accept IDs in text.
Workflow approval never bypasses sandbox, command approval, or higher-priority
instructions. Request command permissions through the session's actual
approval mechanism when needed.
"""),
        ("""This session is the coordinator. It plans, delegates, triages, commits, and
keeps the session reports. It does not write code. Each milestone goes to a
fresh `implementer` agent, and each review to a fresh `reviewer` and
`adr-impact` agent. Under a plugin they are named
`coding-standards:implementer`, `coding-standards:reviewer`, and
`coding-standards:adr-impact`. Keeping the code out of this session's context is
what lets it hold the whole run without drifting.

""",
         """This session is the coordinator. It plans, delegates, triages, commits, and
keeps the session reports. It does not write code. Read the bundled role
instructions at `${CLAUDE_PLUGIN_ROOT}/references/agents/implementer.md`,
`${CLAUDE_PLUGIN_ROOT}/references/agents/reviewer.md`, and
`${CLAUDE_PLUGIN_ROOT}/references/agents/adr-impact.md` before delegating.
Each milestone gets a fresh ordinary Codex subagent with the implementer
instructions; each review gets fresh subagents with the reviewer and ADR
instructions. These are reference files, not registered custom agent types.

Use the session's exposed spawn, message, follow-up, wait, and status tools.
Tool names and schemas vary between Codex surfaces. Give each child its role
instructions or their absolute path, the checkout and bundle paths, its brief,
and the approved plan and authorization boundaries. Inherit model settings.
Explore with read-only subagents. Run reviews in parallel when slots permit;
otherwise run the reviewer and ADR check sequentially. Release finished child
slots when the exposed tools support it, retaining the implementer for fixes.
Before implementation, confirm there is capacity for the implementer plus
one reviewer child. If only one child slot is available and the session cannot
suspend and resume the implementer with its context intact, stop and explain
that two child slots are required. Do not close the implementer to make room
and silently replace it with a fresh context for milestone fix rounds.
If delegation or follow-up is unavailable, stop before implementation and
explain the missing capability. Do not silently replace independent review
with coordinator self-review.

"""),
        ("""${CLAUDE_PLUGIN_ROOT}/commands/work-on.md""",
         """${CLAUDE_PLUGIN_ROOT}/skills/work-on/SKILL.md"""),
        ("""Its
plan mode and plan approval happen once for the whole run, not per milestone,""",
         """Its
planning and explicit approval happen once for the whole run, not per milestone,"""),
        ("""those with the sandbox disabled, through the permission prompt. The plan
  names each one, so approving it covers them.""",
         """those through the session's command approval mechanism when required. The
  plan names each one, but run approval does not grant command permissions."""),
        ("""## 1. Plan mode: build the run""",
         """## 1. Build the run for approval"""),
        ("""project's `CLAUDE.md`. Every milestone runs them before it commits.""",
         """project's `AGENTS.md` and any applicable `CLAUDE.md`. Every milestone runs
   them before it commits."""),
        ("""7. Front-load every question. Ask them together, in one batch, before calling
   ExitPlanMode.""",
         """7. Front-load every question. Collect them together before requesting
   approval, using chat or supported question tools within their limits."""),
        ("""Call ExitPlanMode. That approval is the only gate in the run.""",
         """Present this complete plan and the run's authorization scope in chat. Ask the
user to approve it explicitly and wait for their reply. Do not start the run
while approval is pending. This is the run's single workflow approval gate;
command permission prompts remain separate. Record the approved plan and its
scope in the first run report after approval so a resumed run can recover it."""),
        ("""proposals instead, and hand off. Do not schedule in plan mode. Plan mode
cannot write, and scheduling has its own approval in `/schedule-proposal`.""",
         """proposals instead, and hand off. Keep discovery read-only. Scheduling has
its own approval in the bundled `schedule-proposal` skill."""),
        ("""does. That includes its one multi-select AskUserQuestion call.""",
         """does. Ask for the selected IDs in text when multi-select is unavailable."""),
        ("""When the user picks nothing, or there is nothing to offer, stop. Otherwise
call ExitPlanMode with a plan that implements nothing. It names the picks, in
the order `candidates` gave. It says the run will schedule them and then plan
again. Approving it only leaves plan mode, so `/schedule-proposal` can write.
It authorizes nothing in "What the user authorizes by approving the plan".

Once approved, run the handoff yourself. Do not print it as commands for the
user to type.

1. Invoke `/schedule-proposal` with the Skill tool, passing the picks, as in
   `/schedule-proposal PROJ-012 PROJ-015`. Under a plugin it is named
   `coding-standards:schedule-proposal`. Follow it through its own approval.
2. When it added no queue row, stop. Nothing in sections 2 to 6 runs.
3. Otherwise call EnterPlanMode and start section 1 again with this run's
   arguments. Run "When there is nothing to run" at most once per run. If
   `next` still finds no row, report that and stop.

""",
         """When the user picks nothing, or there is nothing to offer, stop. Otherwise
read `${CLAUDE_PLUGIN_ROOT}/skills/schedule-proposal/SKILL.md` and follow it
with the picked IDs, in the order `candidates` gave. This is scheduling only;
it authorizes nothing in "What the user authorizes by approving the plan".
Scheduling keeps its own layout approval. Do not invoke a Claude command or
assume a skill invocation tool exists: read and follow the bundled skill.

When it added no queue row, stop. Otherwise start section 1 again with this
run's arguments and obtain approval of the implementation plan. Run this
scheduling handoff at most once per run. If `next` still finds no row,
report that and stop.

"""),
        ("""When a tool whose name ends in `work_queue_status` is available, it shows the
run's progress to the user. Call it with the whole run right after
ExitPlanMode. Call it again whenever a milestone's run status or the current
step changes, and with step `finished` when the run is done. Skip it when the
tool is absent.

Pass each row in its `rows` array, with the row's range as `id`. Pass each
milestone with its `PROJ-NNN MN` ID, and a `DROPPED` milestone with run status
`DROPPED`. Use step `row-review` for a row review.

""",
         """If `update_plan` is available, show one checklist step per milestone after
approval and update it when progress changes. Map QUEUED to pending,
IN PROGRESS to in_progress, and DONE to completed. Keep HELD and BLOCKED
pending with their status and reason in the step text. Label DROPPED as
DROPPED and completed; it means no work remains, not that code was built.
During row and final reviews, explain which review is running. Never mark
unfinished work completed just to close the checklist. When `update_plan`
is unavailable, report these transitions in commentary. The full statuses
and reasons live in the run report, which remains the recovery source.

"""),
        ("""path, and the run's notes. Do not re-enter plan mode, and do not present a
   plan for approval.""",
         """path, and the run's notes. Include the implementer reference and approved
   run scope. Do not request another milestone plan approval."""),
        ("""(`coding-standards:adr-impact`) on the working-tree diff.""",
         """with the bundled ADR instructions on the working-tree diff."""),
        ("""   Send the fix and trace findings to the same implementer with SendMessage,
   so it keeps its context. It re-runs the local checks and reports again.

   While waiting on any agent, keep a fallback timer armed, such as a
   background `sleep 600`. A lost report or notification otherwise stalls the
   run with nothing to wake it. An agent that hangs or dies does the same.
   When the timer fires and the agent has not reported, check its liveness
   before re-sending anything. Never kill a command the agent started. A
   restarted test suite costs more than waiting for it.

   The agent's transcript is the notification's `<output-file>`. It is JSONL,
   and too large to read whole. Query it instead with
   `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/agent_liveness.py <output-file>`.
   Its `last` is the time of the latest entry. Its `pending` lists the tool
   calls that have no result yet. Act on the first case that applies:
   - The transcript ends with the agent's report. It finished, and its
     notification was lost. Read the report.
   - `last` moved since the previous check. The agent is alive. Re-arm the
     timer.
   - A pending call is to a tool whose name ends in `cg_run` or `cg_wait`. Find
     its run with `cg_list`, `state: running`, and this session's `session_id`
     from `cg_info`. Subagents share it. Match the run by its command. Read the
     run's output with `cg_stdout`, `from: tail`, and compare its elapsed time
     with `cg_stats` for the same command. Output that grew since the previous
     check, or an elapsed time within the usual range, means wait. Neither
     means the run is stuck. A `running` run with no `started_at` carries no
     liveness signal. Treat it as unknown.
   - A Bash call is pending. Wait. Without cg, the agent runs its checks
     through Bash, and a slow check looks the same as a stuck one. The Bash
     tool's timeout does not kill the command. It moves it to the background.
   - The agent's latest notification says it is waiting on its own background
     work, and `last` has not moved since. Wait. The agent resumes when that
     work finishes. Its output is the `<task-id>.output` file beside the
     transcript, where `<task-id>` is the ID the agent's last tool result
     names. Output that grows means it is still working.
   - Some other call is pending and `last` has not moved. Compare
     `git diff --stat` with the previous check, not `git status`. New edits to
     files that were already modified do not show in `git status`. No change
     means it is stuck.
   - Nothing is pending and `last` has not moved. The agent is dead.

   Nudge a stuck or dead agent once with SendMessage. Ask it what it is
   waiting on. If the next check shows no progress, stop it with TaskStop.
   Stopping an agent also kills every background command it started. Never
   stop one that is waiting on its own background work.
   Spawn a fresh agent with the same brief. Tell it the working tree holds the
   stopped agent's partial work, and to continue from it. Record the restart
   in the session report.

   <!-- Workaround for bugs/20261005-subagent-second-report-dropped.md. Remove once that bug is fixed. -->
   A "finished" notification may say the agent's report was delivered
   earlier while a follow-up is still unanswered. That report is the old one.
   Read the end of the agent's transcript, the notification's `<output-file>`,
   for its answer to the follow-up.

""",
         """   Send the fix and trace findings as a follow-up to the same implementer,
   using the session's follow-up tool so an idle child resumes its turn.
   A message-only tool may not restart an idle child. It re-runs the local
   checks and reports again. Associate each report with its milestone and fix
   round; an old completion notification does not satisfy a new request.

   Wait with the session's agent wait tool using bounded timeouts of at most
   60 seconds, and keep the user informed during long work. A timeout does
   not mean failure or deadlock. Inspect exposed agent status and ask for a
   progress update when needed. Do not parse Claude transcripts or start a
   shell timer. Do not kill or duplicate a running check because it is slow.
   If a child fails, establish that its commands have finished before starting
   a replacement. If that cannot be established, stop dependent writes and
   report the unresolved work. A replacement receives the original brief,
   the current diff and partial work, and the approved scope. Record restarts
   in the session report. Review agents report only and never edit files.

"""),
        ("""- Awaiting deploy: its state is `awaiting deploy`. Its code is finished,
     and only the user can say the deploy is live. It is a question in item 7.""",
         """- Awaiting deploy: its state is `awaiting deploy`. Its code is finished,
     and only the user can say the deploy is live. It is a question in item 7.
     Until explicitly confirmed live, hold its row or milestone suffix.
     Approval of the run alone does not confirm a deployment."""),
    ),
    'work-on': (
        ("""Start by calling the EnterPlanMode tool, before any other action. Skip this
step if the session is already in plan mode.
""",
         """Plan first using read-only exploration. Do not edit project files, reports,
stage, commit, or stash until the user explicitly approves the complete plan.
Do not try to switch collaboration modes. Present the plan in chat and ask
for explicit approval; wait for the user's reply. A checklist update, question
default, empty answer, timeout, or tool permission grant is not run approval.
Use an available question tool only within its supported mode and limits;
otherwise ask in chat. For multiple selections, accept IDs in text.
Workflow approval never bypasses sandbox, command approval, or higher-priority
instructions. Request command permissions through the session's actual
approval mechanism when needed.
"""),
        ("""Once in plan mode, work on the proposal milestone in $ARGUMENTS by following""",
         """Work on the proposal milestone in $ARGUMENTS by following"""),
        ("""leaves undone. Then ask the user to choose before you call ExitPlanMode.""",
         """leaves undone. Then ask the user to choose before requesting plan approval."""),
        ("""7. Once the user approves the plan, set the milestone's status to
   `IN PROGRESS`.""",
         """7. Present the complete plan in chat and wait for the user's explicit
   approval before any edits. Under an approved `work-queue` run, its plan
   and authorization cover this step; do not ask again per milestone.
   Once approved, set the milestone's status to `IN PROGRESS`."""),
        ("""12. Review the change with the `reviewer` agent, named
    `coding-standards:reviewer` when installed as a plugin.""",
         """12. Spawn an ordinary Codex subagent with the instructions in
    `${CLAUDE_PLUGIN_ROOT}/references/agents/reviewer.md`."""),
        ("""same message, spawn the `adr-impact` agent
    (`coding-standards:adr-impact`) on the working-tree diff, and tell the
    reviewer it runs beside it. When `adr-impact` is not available, skip it and
    do not tell the reviewer.""",
         """same review round, spawn a fresh subagent with the instructions in
    `${CLAUDE_PLUGIN_ROOT}/references/agents/adr-impact.md` on the diff.
    Tell the reviewer the ADR check is covered separately. If slots are
    limited, run the two reviews sequentially. Give both the checkout and
    bundle paths and the approved scope. Reviews report only and never edit.
    If delegation is unavailable, stop before implementation and explain
    the missing capability. Use exposed message, follow-up, status, and wait
    tools within their schemas; a timeout is not failure. Wait in intervals
    of at most 60 seconds and send progress updates during long reviews."""),
        ("""5. Explore the codebase""",
         """5. Confirm the session exposes delegation for the independent reviews in
   step 12 before proceeding. Stop if it does not. Explore the codebase"""),
        ("""`--review-loop`, send the same reviewer a follow-up after applying fixes.""",
         """`--review-loop`, resume the same reviewer with a follow-up after applying
    fixes. Use a tool that starts an idle child turn, not just a queued message."""),
    ),
    'implementer': (
        ("""When a tool whose name ends in `cg_run` is available, run every check through
it, with `wait_timeout_auto` set. A timed-out response does not stop the
command. Resume waiting on it with `cg_wait` and its run ID. The coordinator
watches these runs to tell a slow check from a stuck one. A check run through
Bash is invisible to it. Never wrap a check in `timeout` or anything else that
kills it.

""",
         """Run checks with the session's shell execution tool in the named checkout.
When a command returns a running session ID, wait for that same command with
the corresponding tool. Report session IDs and progress when asked. Do not
start a duplicate check after a timeout, or wrap checks in a timeout that
kills them. All checks must finish before your report.

"""),
        ("""Before you report, wait for every background command and Monitor you started to finish, or stop it.""",
         """Before you report, wait for every background command you started to finish, or stop it."""),
        ("""<!-- Workaround for bugs/20261005-subagent-second-report-dropped.md. Remove once that bug is fixed. -->
If the report is refused because one was already delivered, send the full report with SendMessage to `main` instead.

""",
         """Return the full report for this milestone or fix round to the coordinator.
Identify the round so a prior report cannot be mistaken for this answer.

"""),
        ("""Do not ask the user anything. The user approved the run up front.""",
         """Do not ask the user anything. The coordinator supplies the approved run scope.
That scope does not bypass command permissions or higher-priority instructions."""),
    ),
    'schedule-proposal': (
        ("""Then ask which to schedule, with AskUserQuestion in one multi-select call. Offer the first three ready candidates,
   and mark the first "(Recommended)". End with a "Do not schedule" option. Say in the question that "Other" takes any
   IDs from the list, such as a waiting candidate together with what it waits on.""",
         """Then ask which IDs to schedule. Use a supported question tool or ask in chat. Recommend the first three ready
   candidates, marking the first "(Recommended)". Include "Do not schedule" and accept any IDs from the list in text,
   such as a waiting candidate together with what it waits on."""),
        ("""Make a single AskUserQuestion call. Every question the scheduling needs goes in that one call.""",
         """Collect every scheduling question in one batch. Ask in chat or use supported question tools within their limits."""),
        ("""Four questions is the cap. In a batch, each question covers every proposal, with one option per entry.""",
         """Respect the available question tool's limits. In a batch, each question covers every proposal.
Ask in chat when the tool cannot represent the batch or multiple selections."""),
        ("""No code reads, no Agent sub-tasks for codebase exploration,""",
         """No code reads, no subagents for codebase exploration,"""),
    ),
    'session-report': (
        ("""with the Write tool, which creates the parent directory. Bash cannot write
   there.""",
         """using the session's file-editing or shell tool, creating the parent directory
   only with the required filesystem permission."""),
    ),
}


def translate(text, name):
    for old, new in REPLACEMENTS.get(name, ()):
        if text.count(old) != 1:
            raise ValueError(f"{name}: stale Codex adaptation for {old[:80]!r}")
        text = text.replace(old, new, 1)
    if name in ("work-queue", "work-on", "schedule-proposal"):
        text = text.replace("Use Explore agents", "Use read-only exploration subagents")
        text = text.replace("AskUserQuestion", "available user-question")
        text = text.replace("multi-select question", "question accepting IDs in text")
        text = text.replace("project's `CLAUDE.md`", "project's `AGENTS.md` and applicable `CLAUDE.md`")
    if name == "adr-impact":
        text = text.replace("project's `CLAUDE.md`", "project's `AGENTS.md` and applicable `CLAUDE.md`")
    return text
