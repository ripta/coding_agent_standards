---
description: Plan a queue of phase milestones up front, then implement and commit them one at a time
argument-hint: <phase>[.<milestone>] [<phase>[.<milestone>] ...] [notes]
model: opusplan
---

Start by calling the EnterPlanMode tool, before any other action. Skip this
step if the session is already in plan mode.

Work through the queue of phase milestones named in $ARGUMENTS. Planning
happens once, up front. Implementation then takes one milestone at a time off
the queue, and lands each one as its own commit before starting the next.

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

Nothing else is relaxed. Never push, never open a PR, and never run a
destructive git operation.

## 1. Plan mode: build the queue

1. Parse the arguments into an ordered queue. A bare `PHASE` (e.g., `59`) means
   every milestone in that phase that is not DONE. `PHASE.MILESTONE` (e.g.,
   `59.3`) names one milestone. A range (e.g., `59.2-59.4`) names every
   milestone between its ends. Lists may use commas or "and". Queue order is
   argument order, then milestone order within a phase. Treat any trailing
   prose as notes for the run.

2. For every phase in the queue, run the checks `/work-on` makes before it
   explores the codebase: locate the phases directory, read the index, the
   phase document, and the proposal, and check the proposal status. Where
   `/work-on` says to stop on a COMPLETE phase or a DONE milestone, drop it
   from the queue and note that instead.

3. Check each phase's `**Dependencies:**`. A queued phase that depends on a
   phase that is neither COMPLETE nor earlier in the queue is a blocker. So is
   a queue order that puts a phase before its dependency.

4. Read the design documents and ADRs the phases and proposals cite. Explore
   the codebase enough to plan every milestone. Detailed exploration for a
   later milestone can wait until that milestone starts, since earlier
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
   - A dependency blocker from item 3.
   - The branch, when the current branch is the mainline. Offer to create one.
   - The session report directory, when item 6 could not resolve it.
   - An ambiguity that only the user can settle: a contradiction between the
     phase document and the proposal, or a choice the documents do not
     constrain at all and that would be costly to reverse.

   Everything else becomes a best guess in the plan.

8. Write the plan:
   - The queue: every milestone in order, with its phase, the proposal
     milestone it implements, and a one-line description
   - A short implementation approach for each milestone, and the files it
     touches
   - The local checks every milestone runs
   - The best guesses already made, each with the document it rests on
   - The branch, and the session report directory

Call ExitPlanMode. That approval is the only gate in the run.

## 2. Implement each milestone

Record the current `HEAD` before the first milestone, and again before the
first milestone of each phase. These are the base commits for the phase and
final reviews. Write them into the session report so they survive context
compaction.

For each milestone in the queue, in order:

1. Re-read its acceptance criteria and explore the code as it stands now.
   Plan the milestone yourself. Do not re-enter plan mode, and do not present
   the plan for approval.

2. When this is the first milestone of a phase, sync the phase-begin artifacts
   from `plans.md` "Artifact Sync". Set the milestone's status to IN PROGRESS.

3. Implement it. Then tick its acceptance criteria and set its status to DONE,
   in the phase document and the phase index.

4. Run the local checks. Fix every failure and warning, including lint
   warnings in code the milestone touched.

5. Review it with the `reviewer` agent, named `coding-standards:reviewer` when
   installed as a plugin. Spawn a fresh agent for every review. Tell it the
   phase milestone and the proposal milestone. Triage what it reports:
   - Fix comment, style, and plan-gap findings directly.
   - Fix a `CONFIRMED` finding.
   - Trace a `PLAUSIBLE` finding before acting. Fix it only if the trace
     confirms it.
   - Dismiss a finding that is wrong, and record why.

   Re-run the local checks after the fixes.

6. Commit the milestone. The review fixes land in the same commit. Stage the
   files by path; never `git add -A` or `git add .`. Write the message by
   `${CLAUDE_PLUGIN_ROOT}/rules/commit-style.md`.

7. Amend the phase's session report (see section 4).

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

3. Triage the findings as in section 2. Commit the fixes, and any artifact
   sync, as their own commit. Amend the session report.

4. Continue with the next phase in the queue.

When the whole queue is done, run one more review the same way, over the range
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

Keep the base commits, and the queue with each milestone's status, near the
top. After a context compaction, re-read the session reports and the phase
documents to find where the run stands, then continue.

## 5. When to stop

Stop the run, and say why, only when:

- A build or test failure cannot be fixed within the milestone's scope
- A review finding needs a design decision the documents do not cover, and
  any guess would be costly to reverse
- The work turns out to contradict the proposal or an ADR

Before stopping, commit any finished work that passes the checks. Leave
unfinished work uncommitted, never discarded, and record it and the blocker in
the session report. Everything short of this is a best guess, not
a stop.

## 6. Finish

Report to the user: the commits made, in order; the session report paths; the
best guesses that most deserve their review; and anything left open.
