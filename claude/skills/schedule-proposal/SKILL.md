---
name: schedule-proposal
description: |
  Schedule an accepted proposal (PROJ-NNN) by adding its milestones to the
  project's queue. Spec-only: edits queue.md and the proposal's Decision Log.
  No code planning or implementation. Invoked as `/schedule-proposal PROJ-NNN`.
model: sonnet
allowed-tools: AskUserQuestion, Read, Write, Edit, Glob, Grep, Bash
---

You schedule one proposal by adding queue rows for its milestones. This is spec-only. You do not plan code, scan the
codebase, or implement anything. Your only artifacts are `queue.md` and the proposal.

The queue lives in `${CLAUDE_SKILL_DIR}/../../project-management/plans.md`. Metadata, status vocabularies, and
milestone references live in `${CLAUDE_SKILL_DIR}/../../project-management/tracking.md`. The proposal format lives in
`${CLAUDE_SKILL_DIR}/../../project-management/proposals.md`. All three are bundled alongside this skill. They are the
only source for the formats, and this skill does not carry its own copy. Always defer to a project-specific deviation
when one exists.

`${CLAUDE_SKILL_DIR}/../../scripts/proposals.py` reads the queue and the proposals. Run it with `python3` and
`--proposals-dir <dir>`. Use it rather than parsing the files by hand.

## Inputs

The skill's argument is a proposal identifier such as `PROJ-033`. If it is missing or malformed, ask for it with
AskUserQuestion, on its own, before anything else. Nothing below can be detected without it.

## Workflow

### Step 1: Load the standards

Read `plans.md`, `tracking.md`, and `proposals.md` from `${CLAUDE_SKILL_DIR}/../../project-management/`. If any cannot
be read, stop and tell the user this skill is installed without its standards. Do not schedule from memory.

Then check the project for deviations. Look in its `CLAUDE.md`, `AGENTS.md`, and any local planning doc. If a project
convention conflicts with the standard, follow the project.

### Step 2: Locate and validate, without asking

Do all of this before any question.

1. **Directories.** Find the proposals directory (`spec/proposals/`, or the `docs/` equivalent). It may be a symlink
   into a separate specs repo. Follow it. If the project has a phases directory and no `queue.md`, it has not migrated
   to era 3. Stop and tell the user it must migrate first, with `/migrate-era`.
2. **Queue.** Read `queue.md` in the proposals directory. If it does not exist, this is the project's first scheduled
   work. Step 5 creates it in the form `plans.md` "The Queue File" gives.
3. **Proposal.** Find `<ID>-*.md` in the proposals directory. If none exists, tell the user and stop. Read it and
   capture the title, `**Status:**`, `**Tradeoffs:**` if present, Dependencies, Design Decisions (Settled), Design
   Decisions (Open), Milestones, Risks, and the Decision Log.
4. **Validate.** Run `proposals.py check`. Stop and report the failed check if any of these is true:
   - The proposal's `**Status:**` is anything other than `accepted`.
   - `check` reports a finding on this proposal, such as milestones that are not subsections with a status line, or
     an index row that disagrees.
   - Design Decisions (Open) contains any item. An empty or absent section is fine. Route the user to
     `proposal-reviewer`.
5. **Unscheduled milestones.** List the proposal's milestones that are not `DONE` or `DROPPED` and that no queue row
   names. If there are none, tell the user the proposal is already fully scheduled, name its rows, and stop. A
   proposal may already have some rows. Then the unscheduled milestones must form one or more contiguous ranges that
   follow its last scheduled milestone. A gap between scheduled milestones cannot be filled, since rows of one
   proposal run in order. Stop and tell the user when you find one. Note whether its existing rows carry notes,
   since every row of a multi-row proposal needs one.
6. **A revived proposal.** If the Decision Log has an entry that recorded removed queue rows at a deferral, read the
   ranges, depends-on cells, and notes it recorded. Offer them as the starting layout in Step 4.
7. **Dependencies.** For each `PROJ-NNN` in the proposal's Dependencies, find its state:
   - `implemented`: the dependency is met. It needs no depends-on entry.
   - `accepted` with queue rows: it becomes a depends-on entry. Name the milestone this work needs, as `PROJ-NNN MN`,
     when the proposal's text says which. Otherwise name the proposal, `PROJ-NNN`. A named milestone that is already
     `DONE` is met and needs no entry, unless it is a `(deployed)` dependency.
   - Anything else, or `accepted` with no queue rows: hold it for Step 3. A row that depends on it would be blocked.

   Then check each depends-on entry for a deployment boundary. Search the proposal's Dependencies, Milestones, and
   Risks for the boundary signals listed in `plans.md` "Deployment Dependencies". Record each entry that has a signal,
   and quote the signal. Every other entry is code-only.
8. **Positions.** Note where new rows can go. Finished rows sit at the top of the queue and never move. A new row goes
   at the end of the queue, or before any unfinished row. A row must not go above a row it depends on, or above an
   earlier row of the same proposal.

Report what you found in a few lines before asking anything. Name each code-only dependency as code-only.

### Step 3: Ask once, up front

Make a single AskUserQuestion call. Every question the scheduling needs goes in that one call. Skip any question the
request or Step 2 already answered.

- **Confirm and position.** "Schedule `PROJ-NNN: <title>`, and where?" Always ask. Accepting a proposal is not
  scheduling it, and `plans.md` requires an explicit request. Offer "At the end of the queue", one option for each
  unfinished row it may go before, and a "Do not schedule" option. When there are many unfinished rows, offer the end,
  the next few rows, and let the user name another in "Other".
- **Deployed.** Ask only about depends-on entries that Step 2 found a boundary signal for. For each one, ask whether
  this work needs it running in production, and name the signal in the option. Only the user can confirm a deployment.
  Ask in one multi-select question within the same call. Skip it when no entry has a signal.
- **Blocked dependencies.** If a dependency is not `accepted` or `implemented`, or has no queue rows, ask whether to
  schedule anyway. The new row would be blocked until the dependency is scheduled or settled.
- **Splitting.** Ask only when the user's request or a revived layout suggests more than one row, or when other work
  should be built between this proposal's milestones. Each split needs a note saying why. Rows split only along
  milestone boundaries.

Four questions is the cap.

### Step 4: Compute the layout and confirm

Compute each new row: its milestone range, its depends-on cell, and its note. A note carries the reason for a
dependency or a split. Every row of a proposal that has more than one row needs a note saying why. When this run
gives a proposal its second row, an existing row may lack a note. Never edit it. Name it in the plan, and ask the user
to add the note.

Show the user the full plan: the rows, where each goes, and the lines added to the proposal. This is the one approval
gate. Do not write until the user approves.

### Step 5: Write the queue rows

Insert each row at its approved position in `queue.md`. Never move, renumber, or edit an existing row. If the queue
does not exist yet, create it with the heading, the table header, and the new rows.

### Step 6: Update the proposal

- Set `**Updated:**` to today's date.
- Add a Decision Log entry: `- YYYY-MM-DD: Scheduled as <range> in queue.md.` Name every row when there are several.
  `tracking.md` allows a Decision Log to name a queue row, because the entry records history.
- Do not change `**Status:**`. Scheduling leaves it `accepted`. Do not change the proposal index.

Milestone numbers named by a queue row are now permanent. Say so in the report.

### Step 7: Verify

Run `proposals.py check`, and `proposals.py row PROJ-NNN` for the first new row. Report each dependency's state from
`row`. Fix any `check` finding this run caused.

### Step 8: Report

Summarize:

- The proposal scheduled, and where its rows went.
- Each new row, with its range, depends-on cell, and note.
- Each dependency, with its state, and any that is blocked.
- Every file created or edited.
- That the milestone numbers the rows name are now permanent.

## Rules

- Spec-only. No code reads, no Agent sub-tasks for codebase exploration, and no planning beyond what the proposal
  contains.
- Never invent milestones or checks. If the proposal lacks them, route the user to `proposal-reviewer`.
- Detect before asking, then ask once. The layout confirmation in Step 4 is the only later checkpoint. Write nothing
  before the user approves it.
- Never move, split, or edit an existing queue row. Never renumber a milestone.
- Treat any non-`accepted` proposal status as a hard stop. Do not change it to make scheduling possible.
- Treat any open design question as a hard stop, and route the user to `proposal-reviewer`.
- A depends-on cell names `PROJ-NNN` or `PROJ-NNN MN`. Only the user decides `(deployed)`. Ask only when Step 2 found
  a boundary signal.
- Use the status values from `tracking.md`. Milestones are `NOT STARTED`, `IN PROGRESS`, `DONE`, or `DROPPED`.
