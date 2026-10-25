---
description: Plan a run of queue rows up front, then implement and commit their milestones one at a time
argument-hint: "[next [N] | all | <PROJ-NNN>[ M<n>[-M<m>]] ...] [notes]"
model: opus
---

Start by calling the EnterPlanMode tool, before any other action. Skip this
step if the session is already in plan mode.

Work through the queue rows named in $ARGUMENTS. Planning happens once, up
front. Implementation then takes one milestone at a time, and lands each one
as its own commit before starting the next.

This session is the coordinator. It plans, delegates, triages, commits, and
keeps the session reports. It does not write code. Each milestone goes to a
fresh `implementer` agent, and each review to a fresh `reviewer` and
`adr-impact` agent. Under a plugin they are named
`coding-standards:implementer`, `coding-standards:reviewer`, and
`coding-standards:adr-impact`. Keeping the code out of this session's context is
what lets it hold the whole run without drifting.

This command wraps `${CLAUDE_PLUGIN_ROOT}/commands/work-on.md`. Read it now.
Its checks, proposal updates, and review still apply to every milestone. Its
plan mode and plan approval happen once for the whole run, not per milestone,
and it commits instead of only summarizing. The queue lives in
`${CLAUDE_PLUGIN_ROOT}/project-management/plans.md`. Always defer to a
project-specific deviation when one exists.

`${CLAUDE_PLUGIN_ROOT}/scripts/proposals.py` reads the queue and the
proposals, as in `/work-on`. Use it rather than parsing the files by hand.
Pass any `--proposals-for PREFIX=PATH` override the user gives to every call
in the run.

## What the user authorizes by approving the plan

Approving the plan is the user's explicit, durable authorization for the whole
run. It overrides these rules for this run only:

- The rule against committing on the user's behalf, in
  `${CLAUDE_PLUGIN_ROOT}/rules/git-workflow.md` and in `/work-on`. Commit each
  milestone, and each round of review fixes, in the code repo and in the specs
  repo. This covers the session reports when they live in either repo, as
  section 4 describes.
- The rule to confirm before moving on to a new milestone, in `plans.md` and
  `${CLAUDE_PLUGIN_ROOT}/rules/work-discipline.md`. Do not pause between
  milestones or between rows.
- The rule to ask before deciding an ambiguity. Make the best guess the
  proposals and design documents support, and record it in the session
  report. This includes the rule in `/work-on` step 6 to ask the user to
  choose when a more complete approach exists. Plan the complete approach.
- The rule to hand the user commands to run, in
  `${CLAUDE_PLUGIN_ROOT}/rules/shell-discipline.md` "Commands the User Runs".
  The run runs every command itself. That includes commands that need the
  user's credentials, such as a fixture re-record that reads a token. Run
  those with the sandbox disabled, through the permission prompt. The plan
  names each one, so approving it covers them. When a run fails, diagnose and
  fix the cause before running it again. Do not call a failure transient
  without evidence. When the permission check still denies a command, tell
  the user in one line what it needs, and keep working on what does not
  depend on it.
- The rule to leave unfinished work in the tree. Stash a blocked milestone's
  unfinished work by path, as section 5 describes, and list every stash in
  the final report.

Nothing else is relaxed. Never push, never open a PR, and never run a
destructive git operation. Commit on the branch that is checked out. Never
create or switch branches. Never act on an edit this run did not make.

## 1. Plan mode: build the run

1. Parse the arguments into queue rows. Treat any trailing prose as notes for
   the run. A note like "hold PROJ-004" holds that proposal's rows. The
   arguments take one of three forms:
   - A count. `next N` means the next N rows the run can take, in queue order.
     N counts rows, not milestones. `next` alone, or no arguments at all, means
     `next 1`. Run `proposals.py next --count N`, with a `--hold PROJ-NNN` for
     each proposal the notes hold. Its `run` list is the run. A row in it may
     wait on a row picked before it. Its `skipped` list holds each row it
     passed over, with the reasons. These rows are not in the run, so they
     raise no questions in item 7. The user names a skipped row by its ID to
     run it. When `run` is empty, or `next` reports there is no queue, see
     "When there is nothing to run" below.
   - `all` means every unfinished row in `queue.md`. With none, see "When
     there is nothing to run".
   - Rows by ID. `PROJ-NNN` means every unfinished row of that proposal.
     `PROJ-NNN M3` means the row that names M3, from M3 on. `PROJ-NNN M3-M5`
     means those milestones, which must sit in one row.

   Rows run in queue order, whatever order the arguments give. Milestones
   within a row run in number order.

2. For every row, run the checks `/work-on` makes before it explores the
   codebase: locate the proposals directory and the specs repo, run
   `proposals.py row` on the row's first unfinished milestone, read the
   proposal, and check its status. Where `/work-on` says to stop on a
   finished milestone, drop it from the run and note that instead.

3. Classify each row's dependencies from the `row` output, and each
   milestone's `live_after` entry. The `next` output lists both kinds under a
   row's `awaiting_deploy`, and every `Live after` line under `live_after`.
   Run `proposals.py row` on a later milestone to read its entry. Each is one
   of:
   - Met: its state is `met`.
   - Awaiting deploy: its state is `awaiting deploy`. Its code is finished,
     and only the user can say the deploy is live. It is a question in item 7.
   - In-run: its state is `unmet`, and every milestone it waits on is in this
     run. The row waits for the run to finish them. A deploy dependency is
     never in-run, since the run cannot deploy.
   - Blocked: its state is `blocked`. It needs the user, so it is a question in
     item 7. Never hold it silently.
   - Unresolved: its state is `unresolved`. Another project's proposals cannot
     be found, so the row is held. It is not a question. The plan names the
     fix from its reason: an entry for the prefix under `## Other proposals`
     in `queue.md`, or a `--proposals-for PREFIX=PATH` flag when the checkout
     sits elsewhere on this machine. See `plans.md` "Other Projects'
     Proposals".
   - Unmet: anything else.

   A row is held when the notes hold it, when it has an unmet, blocked, or
   unresolved dependency, when an earlier row of its proposal is held, or when it depends
   on a held row. A row gate the user says is not live holds its row too. A
   held row stays in the plan, but no milestone of it runs. Holding a row
   never blocks the other rows. A dependency cycle among rows in the run is a
   blocker.

   A `live_after` entry that is unmet, or that the user says is not live,
   holds only its milestone and the milestones after it in the row. The
   milestones before it still run. Mark the held ones HELD.

   These are the only ways a row or milestone is held. A check only the user
   can perform never holds one. Examples are a live trial, a test in the
   user's browser, or the user's ruling on a trial's outcome. Build everything
   up to that check. When the rest of the milestone's checks pass, mark it
   `DONE` and say in its As built block which check is left to the user. When
   the proposal makes that check a condition of `DONE`, split it into a new
   milestone by amendment, as section 2 step 4 describes. Then run everything
   before it.

4. Read the design documents and ADRs the proposals cite. Explore the codebase
   enough to plan every milestone. Use Explore agents for this, so the
   coordinator keeps their conclusions and not the file dumps. Detailed
   exploration for a later milestone is the implementer's job, since earlier
   milestones change the code it will see.

5. Find the project's local checks: formatters, linters, type checkers, and
   tests. Look at the Makefile, CI config, pre-commit config, and the
   project's `CLAUDE.md`. Every milestone runs them before it commits.

6. Resolve the session report directory now, so the run never blocks on it.
   Follow the "Resolve the target directory" section of
   `${CLAUDE_PLUGIN_ROOT}/skills/session-report/SKILL.md`. If the directory is
   not configured, ask for it with the questions in item 7.

7. Front-load every question. Ask them together, in one batch, before calling
   ExitPlanMode. These always count as questions:
   - A proposal whose status is not `accepted`. This blocks its rows, as it
     does in `/work-on`.
   - Each `blocked` dependency from item 3, with its reason. Name a
     `Replaced by` hint when there is one.
   - A dependency cycle from item 3.
   - Whether each `awaiting deploy` entry from item 3 is live. Ask once per
     deployment, even when several entries wait on it. A yes lets the work
     run. A no on a row gate holds its row. A no on a `Live after` line holds
     only that milestone and the ones after it in the row, as item 3 says.
     See `plans.md` "Awaiting Deploy".
   - The session report directory, when item 6 could not resolve it.
   - An ambiguity that only the user can settle: a contradiction between the
     proposal and the code or an ADR, or a choice the documents do not
     constrain at all and that would be costly to reverse. A guess is costly
     to reverse only when it reaches users before the user can review it. The
     run never pushes, so its own commits are not costly to reverse.

   This list is closed. Everything else becomes a best guess in the plan.
   Never offer to hold, pause, or skip work, or to hand a step to the user,
   as an option. Needing the user's credentials, browser, or live check is
   not a question. Item 3 and "What the user authorizes by approving the
   plan" cover them.

8. Write the plan:
   - The run: every milestone in its expected run order, with its row and a
     one-line description
   - Each row's dependencies, and how each is met
   - Each held row, with the reason it is held, and the fix for each
     unresolved dependency
   - Each row `next` skipped, with its reasons
   - Each command that needs the user's credentials, and the milestone that
     runs it
   - Each check left to the user, and the milestone it belongs to
   - A short implementation approach for each milestone, and the files it
     touches
   - The local checks every milestone runs
   - The best guesses already made, each with the document it rests on
   - The session report directory

Call ExitPlanMode. That approval is the only gate in the run.

### When there is nothing to run

A `next` or `all` run may find no row to take. Then offer to schedule
proposals instead, and hand off. Do not schedule in plan mode. Plan mode
cannot write, and scheduling has its own approval in `/schedule-proposal`.

- No `queue.md`, or no unfinished row in it. Run `proposals.py candidates`.
  Show its tiers, and ask which to schedule, the way
  `${CLAUDE_PLUGIN_ROOT}/skills/schedule-proposal/SKILL.md` Step 2, item 3,
  does. That includes its one multi-select AskUserQuestion call.
- Unfinished rows exist, but `next` skipped them all. Report the skipped rows
  with their reasons. A reason may name a proposal or milestone that no queue
  row names. When `candidates` lists that proposal, offer it the same way. A
  general list of candidates does not help here, so offer only those.

When the user picks nothing, or there is nothing to offer, stop. Otherwise
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

## 2. Implement each milestone

Record the code repo's current `HEAD` before the first milestone, and again
before the first milestone of each row. These are the base commits for the row
and final reviews. Keep a list of every specs-repo commit the run makes, by
SHA, per row. When the specs live in the code repo, the code commits are the
specs commits. Write all of this into the session report so it survives
context compaction.

Track every milestone's run status: QUEUED, IN PROGRESS, DONE, DROPPED, HELD,
or BLOCKED. A milestone the proposal marks `DROPPED` is never work to run. A
row is ready when it is not held or blocked and every dependency is met. An
in-run dependency becomes met when the run finishes it.

When a tool whose name ends in `work_queue_status` is available, it shows the
run's progress to the user. Call it with the whole run right after
ExitPlanMode. Call it again whenever a milestone's run status or the current
step changes, and with step `finished` when the run is done. Skip it when the
tool is absent.

Pass each row in its `rows` array, with the row's range as `id`. Pass each
milestone with its `PROJ-NNN MN` ID, and a `DROPPED` milestone with run status
`DROPPED`. Use step `row-review` for a row review.

Pick the next milestone this way:

- While the current row has a QUEUED milestone, take the next one. Rows run
  whole, so each row's commits form one contiguous range for its review.
- Otherwise, start the first ready row in queue order.
- When no row is ready, the run is done.

For each milestone picked:

1. Set the milestone's status to `IN PROGRESS` in the proposal.

2. Spawn a fresh `implementer` agent. Brief it with the milestone, its row,
   the proposal file, the specs repo when it differs from the code repo, the
   plan's section for this milestone, the local checks, the session report
   path, and the run's notes. Do not re-enter plan mode, and do not present a
   plan for approval.

3. Read its report. If it reports a blocker, check it against section 5. A
   blocker that section 5 does not cover becomes a best guess.

4. Run `proposals.py check`, and `proposals.py freeze` with a `--row-commit`
   for each specs commit this row has made. Then spawn a fresh `reviewer`
   agent. Tell it the milestone, the proposal file, the specs repo, the row's
   specs commits, and that an `adr-impact` agent runs beside it. When the
   session reports live in the code repo, name their paths and say they are
   out of review scope. In the same message, spawn a fresh `adr-impact` agent
   (`coding-standards:adr-impact`) on the working-tree diff. Triage what they
   report, along with the two script results:
   - Mark comment, style, and plan-gap findings as fix. The exception is a
     shortcut the plan did not approve. Mark it as trace, and have it fixed the
     way the plan specified.
   - Mark a `CONFIRMED` finding as fix.
   - Mark a `PLAUSIBLE` finding as trace. The implementer fixes it only if the
     trace confirms it.
   - Mark an amendment finding, a `check` finding, and a freeze hunk with
     origin `row` as fix. The exception is a text hunk in a proposal whose
     `corrections_logged` is above zero. It may be a correction of fact, so
     follow the reviewer's judgment on it.
   - A finding whose fix is to amend the proposal is still fix. This holds when
     the proposal contradicts itself, or when its check text cannot be met as
     written. The implementer amends the proposal per "Amending a Proposal" in
     `proposals.md`. It writes the plan's best guess into the amended text, and
     marks the Decision Log entry as a run best guess. It never escalates to
     section 5.
   - Never send a freeze hunk with origin `other` or `unknown`, or a finding
     with disposition `user`, to the implementer. Another session may have
     made that edit. Record it in the session report for the user.
   - Triage an ADR conflict the same way. When honoring the ADR would change
     the approved plan, it is a blocker. Follow section 5.
   - Record an `ADVISORY` conflict in the session report. It never blocks.
   - Check each uncovered decision `adr-impact` reports, and each ADR
     candidate the implementer names, against the bar in the "What Earns an
     ADR" section of `${CLAUDE_PLUGIN_ROOT}/project-management/design.md`.
     Record each that passes in the session report. Step 6 below adds it to the
     proposal's Decision Log. Do not write ADRs. Section 6 reports them once
   - Dismiss a finding that is wrong, and record why. Read the cited code to
     decide this, but no further.

   Send the fix and trace findings to the same implementer with SendMessage,
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

5. Check the implementer's last report. Every check must have run and passed.
   Its file list must match `git status` in the code repo, and the specs repo's
   status for the proposal. Leave the run's session reports out of this
   comparison. Ask the implementer about any mismatch before committing.

6. Add the milestone's ADR candidates to the proposal's Decision Log as
   `Undecided`, per "Recording ADR Candidates" in `design.md`. Skip one the log
   already holds.

   Commit the milestone. The review fixes land in the same commit. Commit the
   files by path with `git commit -- <paths>`. Staging by path is not enough.
   Another session may share the checkout and have its own files staged, and a
   bare `git commit` takes them too. Never use `git add -A`, `git add .`, or
   `git commit -a`. Write the message by
   `${CLAUDE_PLUGIN_ROOT}/rules/commit-style.md`. Before committing, check the
   message against it, including Forbidden Openers. Reviewers see diffs, not
   messages, so this check is the coordinator's.

   When the specs live in a separate repo, also commit the proposal there, by
   path, with a subject in that repo's own style. Record its SHA in the row's
   list of specs commits. When they live in the code repo, the proposal goes in
   the same commit.

7. Amend the row's session report (see section 4). Copy in the implementer's
   best guesses and deviations, so the next implementer sees them. When the
   report lives in a repo step 6 commits to, amend it before that commit, and
   commit it by path with the milestone.

8. Move on to the next milestone without waiting for the user.

## 3. Row and final reviews

When the last milestone of a row in the run is committed:

1. Spawn a fresh `reviewer` agent for a holistic review of the row. Give it
   the code commit range from the row's base commit to `HEAD`, the row's specs
   commits, and every milestone the range covers. Ask it to weigh how the
   milestones fit together, on top of its usual axes. Run a fresh `adr-impact`
   agent on the same range beside it, and tell the reviewer so. Run
   `proposals.py freeze` with the row's specs commits, as in section 2.

2. Triage the findings as in section 2. Send them to a fresh `implementer`,
   with the commit range and the milestones it covers in place of a single
   milestone. Commit the fixes as their own commit, in each repo they touch.
   Record any specs commit. Check its message as in section 2, step 6. Amend
   the session report.

3. Only now finish the row, per `plans.md` "Working a Milestone". A proposal
   whose milestones are all finished becomes `implemented`, and the proposal
   index says so. The row moves from `queue.md` to the end of `history.md`. Run
   `proposals.py check`, and fix what it reports. Commit these edits by path,
   and record the specs commit. Writing `implemented` before the review's
   fixes land would freeze the proposal before its last amendment.

4. Continue with the next ready row.

When the run is done, run one more review the same way, over the range
from the run's base commit to `HEAD`, with every specs commit the run made.
This final review is also the run's ADR review. Ask the reviewer for one, so it
checks every ADR the range adds or edits. Row reviews do not ask for it. Commit
its fixes, check the message as in section 2, step 6, and amend the last
session report. A fix to a proposal the run already marked `implemented` is a
correction of fact. It needs its Decision Log entry, per `proposals.md`
"Implemented Proposals Are Frozen".

## 4. Session reports

Write one report per row, using the `session-report` skill. Create the file
when the row starts, and name it for the row, e.g.
`YYYYMMDD-proj-004-m3-m5-<short-title>.md`. Then amend that same file after
every milestone and review: re-read it and update it in place. The skill's rule
to extend the slug on a filename collision applies only when creating a row's
file, not when amending it. Do not start a new file per milestone.

The report records, per milestone:

- The commits, by short SHA and subject, in the code repo and the specs repo
- The checks run, and their result
- Every best guess: the ambiguity, the choice made, the document it rests on,
  and what would change if the guess is wrong
- Each review finding, and its disposition: fixed, dismissed with the reason,
  deferred, or left for the user. When the implementer's Traces report a
  finding as not confirmed, record its diagnosis as unresolved, here and in any
  Decision Log entry, whatever verdict the reviewer gave
- Any deviation from the proposal, and anything left open

The first row report of the run also carries the run state, near the top: the
base commits, each row's specs commits, every milestone with its run status,
and each held or blocked row with its reason. Update it whenever a status
changes. Later row reports link to it. After a context compaction, re-read it,
the session reports, the proposals, `queue.md`, and `history.md` to find
where the run stands, then continue. A run resumed in a new session does the same. The run's
reports are still its own to amend, even once committed.

The report directory may sit inside the code repo or the specs repo, e.g. at
`./spec/reports`. Decide which by the directory's owning repo, per the
skill's "Resolve the target directory" section, not by the path as written.
A `./spec` that links to a separate specs repo puts the reports in the specs
repo. Then the run commits the reports in that repo. Each commit the run makes
there carries the reports' current amendments, by path. A report cannot hold
the SHA of the commit that carries it, so the next amendment adds it. When the
run is done, commit the reports' last amendments by path as their own commit.
In the code repo, check its message as in section 2, step 6. In the specs repo,
write its subject in that repo's own style, as for the other specs commits.

## 5. When to block a row

Block a row, and say why, only when:

- A build or test failure cannot be fixed within the milestone's scope
- A review finding needs a design decision the documents do not cover, and
  any guess would be costly to reverse
- The work contradicts an ADR, and honoring the ADR would change the approved
  plan
- The work contradicts the proposal's goals, and no amendment can reconcile
  them

These are last resorts. "What the user authorizes by approving the plan"
relaxes the rule to ask before deciding an ambiguity. This section does not
restore it. Read the conditions this way:

- A guess is costly to reverse only when it reaches users before the user can
  review it. The run never pushes, so its own commits are not costly to
  reverse. A format or API that no milestone ships on its own is not either.
- A proposal that contradicts itself is not a contradiction with the work.
  Pick the narrowest reading the proposal and the shipped code support, and
  amend the proposal to match, as section 2 step 4 describes.
- A best guess the approved plan records stays a best guess when review
  confirms the ambiguity behind it. The plan approval already covered it.

Before blocking, commit any finished work that passes the checks. Unfinished
work must not leak into the next row's commits, and it must never be
discarded. Stash it by path with a message that names the milestone, e.g.
`git stash push --include-untracked -m "work-queue: blocked PROJ-004 M4" -- <paths>`.
Stash the milestone's proposal edits the same way in the specs repo when it is
separate. Record each stash, the unfinished work, and the blocker in the
session report. The milestone stays `IN PROGRESS` in the proposal.

Mark the row's remaining milestones BLOCKED. Mark every milestone of a row
that depends on it, directly or not, HELD. Then continue with the next ready
row. Everything short of these conditions is a best guess, not a block.

## 6. Finish

Report to the user:

- The commits made, in order, in each repo
- The session report paths
- The best guesses that most deserve their review
- The ADR candidates the run recorded, deduplicated, each with how it passes
  the three tests, per "Listing ADR Candidates" in `design.md`, and the
  proposal whose Decision Log holds it. Most runs have none.
  Do not write them. The user decides which get written, usually in the next
  `/proposal-reviewer` run
- Every edit the run found but did not make: freeze hunks with origin `other`
  or `unknown`, and findings with disposition `user`
- Each held or blocked row, what it waits on, and any stash holding its
  unfinished work
- Anything else left open
