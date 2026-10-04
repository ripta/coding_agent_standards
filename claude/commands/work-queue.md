---
description: Plan a queue of phase milestones up front, then implement and commit them one at a time
argument-hint: <phase>[.<milestone>] [<phase>[.<milestone>] ...] [notes]
model: opus
---

Start by calling the EnterPlanMode tool, before any other action. Skip this
step if the session is already in plan mode.

Work through the queue of phase milestones named in $ARGUMENTS. Planning
happens once, up front. Implementation then takes one milestone at a time off
the queue, and lands each one as its own commit before starting the next.

This session is the coordinator. It plans, delegates, triages, commits, and
keeps the session reports. It does not write code. Each milestone goes to a
fresh `implementer` agent, and each review to a fresh `reviewer` agent. Under a
plugin they are named `coding-standards:implementer` and
`coding-standards:reviewer`. Keeping the code out of this session's context is
what lets it hold the whole run without drifting.

This command wraps `${CLAUDE_PLUGIN_ROOT}/commands/work-on.md`. Read it now.
Its checks, artifact sync, and review still apply to every milestone. Its plan
mode and plan approval happen once for the whole queue, not per milestone, and
it commits instead of only summarizing. The phase model lives in
`${CLAUDE_PLUGIN_ROOT}/project-management/plans.md`. Always defer to a
project-specific deviation when one exists.

## What the user authorizes by approving the plan

Approving the plan is the user's explicit, durable authorization for the whole
run. It overrides these rules for this run only:

- The rule against committing on the user's behalf, in
  `${CLAUDE_PLUGIN_ROOT}/rules/git-workflow.md` and in `/work-on`. Commit each
  milestone, and each round of review fixes.
- The rule to confirm before moving on to a new milestone, in `plans.md` and
  `${CLAUDE_PLUGIN_ROOT}/rules/work-discipline.md`. Do not pause between
  milestones or between phases.
- The rule to ask before deciding an ambiguity. Make the best guess the phase
  documents, proposals, and design documents support, and record it in the
  session report.
- The rule to leave unfinished work in the tree. Stash a blocked milestone's
  unfinished work by path, as section 5 describes, and list every stash in
  the final report.

Nothing else is relaxed. Never push, never open a PR, and never run a
destructive git operation. Commit on the branch that is checked out. Never
create or switch branches.

## 1. Plan mode: build the queue

1. Parse the arguments into a queue. A bare `PHASE` (e.g., `59`) means every
   milestone in that phase that is not DONE. `PHASE.MILESTONE` (e.g., `59.3`)
   names one milestone. A range (e.g., `59.2-59.4`) names every milestone
   between its ends. Lists may use commas or "and". Milestones within a phase
   run in milestone order. Across phases, dependencies set the order, and
   argument order only breaks ties. Treat any trailing prose as notes for the
   run. A note like "hold 61" or "skip 61" holds that phase.

2. For every phase in the queue, run the checks `/work-on` makes before it
   explores the codebase: locate the phases directory, read the index, the
   phase document, and the proposal, and check the proposal status. Where
   `/work-on` says to stop on a COMPLETE phase or a DONE milestone, drop it
   from the queue and note that instead.

3. Classify each queued phase's `**Dependencies:**`, using the format in
   `plans.md`. Each dependency is one of:
   - Met: the dependency is COMPLETE. A `(deployed)` dependency also needs
     the user to confirm the deployment in item 7.
   - In-run: the dependency is queued, and every milestone it has left is
     queued too. The phase waits for the run to complete it. A `(deployed)`
     dependency is never in-run, since the run cannot deploy.
   - Unmet: anything else.

   A phase is held when the notes hold it, when it has an unmet dependency, or
   when it depends on a held phase. A held phase stays in the plan, but no
   milestone of it runs. Holding a phase never blocks the other phases. A
   dependency cycle among queued phases is a blocker.

4. Read the design documents and ADRs the phases and proposals cite. Explore
   the codebase enough to plan every milestone. Use Explore agents for this,
   so the coordinator keeps their conclusions and not the file dumps. Detailed
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
   - A proposal whose status is not `accepted` or `scheduled`. This blocks the
     run, as it does in `/work-on`.
   - A dependency cycle from item 3.
   - Whether each COMPLETE `(deployed)` dependency from item 3 is deployed.
     A "no" holds the phase that depends on it.
   - The session report directory, when item 6 could not resolve it.
   - An ambiguity that only the user can settle: a contradiction between the
     phase document and the proposal, or a choice the documents do not
     constrain at all and that would be costly to reverse.

   Everything else becomes a best guess in the plan.

8. Write the plan:
   - The queue: every milestone in its expected run order, with its phase,
     the proposal milestone it implements, and a one-line description
   - Each phase's dependencies, and how each is met
   - Each held phase, with the reason it is held
   - A short implementation approach for each milestone, and the files it
     touches
   - The local checks every milestone runs
   - The best guesses already made, each with the document it rests on
   - The session report directory

Call ExitPlanMode. That approval is the only gate in the run.

## 2. Implement each milestone

Record the current `HEAD` before the first milestone, and again before the
first milestone of each phase. These are the base commits for the phase and
final reviews. Write them into the session report so they survive context
compaction.

Track every queued milestone's run status: QUEUED, IN PROGRESS, DONE, HELD, or
BLOCKED. A phase is ready when it is not held or blocked and every dependency
is met. An in-run dependency becomes met when the run marks that phase
COMPLETE.

When a tool whose name ends in `work_queue_status` is available, it shows the
run's progress to the user. Call it with the whole queue right after
ExitPlanMode. Call it again whenever a milestone's run status or the current
step changes, and with step `finished` when the run is done. Skip it when the
tool is absent.

Pick the next milestone this way:

- While the current phase has a QUEUED milestone, take the next one. Phases run
  whole, so each phase's commits form one contiguous range for its review.
- Otherwise, start the first ready phase in argument order.
- When no phase is ready, the run is done.

For each milestone picked:

1. When this is the first milestone of a phase, sync the phase-begin artifacts
   from `plans.md` "Artifact Sync". Set the milestone's status to IN PROGRESS.

2. Spawn a fresh `implementer` agent. Brief it with the phase milestone, the
   proposal milestone, the plan's section for this milestone, the local
   checks, the session report path, and the run's notes. Do not re-enter plan
   mode, and do not present a plan for approval.

3. Read its report. If it reports a blocker, follow section 5.

4. Spawn a fresh `reviewer` agent. Tell it the phase milestone and the
   proposal milestone. Triage what it reports:
   - Mark comment, style, and plan-gap findings as fix.
   - Mark a `CONFIRMED` finding as fix.
   - Mark a `PLAUSIBLE` finding as trace. The implementer fixes it only if the
     trace confirms it.
   - Dismiss a finding that is wrong, and record why. Read the cited code to
     decide this, but no further.

   Send the fix and trace findings to the same implementer with SendMessage,
   so it keeps its context. It re-runs the local checks and reports again.

5. Check the implementer's last report. Every check must have run and passed.
   Its file list must match `git status`. Ask the implementer about any
   mismatch before committing.

6. Commit the milestone. The review fixes land in the same commit. Stage the
   files by path; never `git add -A` or `git add .`. Write the message by
   `${CLAUDE_PLUGIN_ROOT}/rules/commit-style.md`.

7. Amend the phase's session report (see section 4). Copy in the
   implementer's best guesses and deviations, so the next implementer sees
   them.

8. Move on to the next milestone without waiting for the user.

## 3. Phase and final reviews

When the last queued milestone of a phase is committed:

1. If every milestone in the phase is now DONE, sync the phase-complete
   artifacts from `plans.md` "Artifact Sync": the phase status, the proposal
   status, and both indexes.

2. Spawn a fresh `reviewer` agent for a holistic review of the phase. Give it
   the commit range from the phase's base commit to `HEAD`, and every
   milestone the range covers. Ask it to weigh how the milestones fit
   together, on top of its usual axes.

3. Triage the findings as in section 2. Send them to a fresh `implementer`,
   with the commit range and the milestones it covers in place of a single
   milestone. Commit the fixes, and any artifact sync, as their own commit.
   Amend the session report.

4. Continue with the next ready phase.

When the run is done, run one more review the same way, over the range
from the run's base commit to `HEAD`. Commit its fixes, and amend the last
session report.

## 4. Session reports

Write one report per phase, using the `session-report` skill. Create the file
when the phase starts, and name it for the phase, e.g.
`YYYYMMDD-phase-59-<short-title>.md`. Then amend that same file after every
milestone and review: re-read it and update it in place. The skill's rule to
extend the slug on a filename collision applies only when creating a phase's
file, not when amending it. Do not start a new file per milestone.

The report records, per milestone:

- The commit, by short SHA and subject
- The checks run, and their result
- Every best guess: the ambiguity, the choice made, the document it rests on,
  and what would change if the guess is wrong
- Each review finding, and its disposition: fixed, dismissed with the reason,
  or deferred
- Any deviation from the phase document, and anything left open

The first phase report of the run also carries the run state, near the top:
the base commits, every queued milestone with its run status, and each held or
blocked phase with its reason. Update it whenever a status changes. Later
phase reports link to it. After a context compaction, re-read it, the session
reports, and the phase documents to find where the run stands, then continue.

## 5. When to block a phase

Block a phase, and say why, only when:

- A build or test failure cannot be fixed within the milestone's scope
- A review finding needs a design decision the documents do not cover, and
  any guess would be costly to reverse
- The work turns out to contradict the proposal or an ADR

Before blocking, commit any finished work that passes the checks. Unfinished
work must not leak into the next phase's commits, and it must never be
discarded. Stash it by path with a message that names the milestone, e.g.
`git stash push --include-untracked -m "work-queue: blocked 61.2" -- <paths>`.
The paths include the phase document and index edits made for the milestone.
Record the stash, the unfinished work, and the blocker in the session report.

Mark the phase's remaining milestones BLOCKED. Mark every milestone of a phase
that depends on it, directly or not, HELD. Then continue with the next ready
phase. Everything short of these conditions is a best
guess, not a block.

## 6. Finish

Report to the user:

- The commits made, in order
- The session report paths
- The best guesses that most deserve their review
- Each held or blocked phase, what it waits on, and any stash holding its
  unfinished work
- Anything else left open
