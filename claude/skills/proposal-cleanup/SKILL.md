---
name: proposal-cleanup
description: |
  Reconcile a project's proposals, proposal index, and queue after milestones
  finish. Marks proposals implemented when every milestone is finished, syncs
  the index, moves finished queue rows to the top, and reports drift it may not
  fix. Also trims the proposal dependency graph and prunes captured ideas, when
  the project has them.
model: sonnet
allowed-tools: AskUserQuestion, Read, Edit, Glob, Grep, Bash
---

You keep a project's proposals, proposal index, and queue in sync after milestones finish. The rules live in
`${CLAUDE_SKILL_DIR}/../../project-management/proposals.md` and `plans.md`, bundled alongside this skill. Always defer
to a project-specific deviation when one exists.

`${CLAUDE_SKILL_DIR}/../../scripts/proposals.py` reads the queue and the proposals. Run it with `python3` and
`--proposals-dir <dir>`. Use it rather than parsing the files by hand.

## Workflow

### Step 1: Locate the Proposals Directory

Find the proposals directory by checking common locations (`spec/proposals/`, `docs/proposals/`, `proposals/`). It
holds the index and `queue.md`. The index is `index.md` or `README.md`, per the "Index File Name" section of
`${CLAUDE_SKILL_DIR}/../../project-management/tracking.md`. If the directory holds both, stop before editing anything.
Tell the user to consolidate the two into one file first.

Run `python3 ${CLAUDE_SKILL_DIR}/../../scripts/detect_era.py --specs-dir <specs dir>`. If it reports an era other
than 3, or `partial`, the project has not finished migrating to era 3. Stop and tell the user to migrate first, with
`/migrate-era`. A project with no era at all has nothing to clean up yet.

### Step 2: Run the Check

Run `proposals.py check`. Sort its findings:

- **Finished, not marked.** "every milestone is finished, so the proposal should be implemented". Step 3 fixes these.
- **Index drift.** "index.md lists ..., but the proposal says ...". The proposal is the source of truth. Step 4 fixes
  these.
- **Everything else.** Report it, and leave it alone. That includes an `implemented` proposal with unfinished
  milestones, an unknown milestone status, a `DROPPED` milestone with no Decision Log link, a bad `Replaced by` line,
  and every hook fault. Each needs the user, or the work that owns the milestone.

If the check finds nothing and the queue needs no move in Step 5, tell the user and skip to Step 6.

### Step 3: Mark Finished Proposals Implemented

For each `accepted` proposal whose milestones are all `DONE` or `DROPPED`, with at least one `DONE`:

1. Set `**Status:**` to `implemented`, and `**Updated:**` to today's date.
2. Update its row in the proposal index.

A proposal in any other status is never changed here. If its milestones look finished but it is `draft`, `designing`,
`deferred`, or `rejected`, a lifecycle step was skipped. Ask the user with AskUserQuestion before changing anything.

### Step 4: Sync the Index

For each index row that disagrees with its proposal's `**Status:**`, set the row to the proposal's status. Never change
a proposal to match its index row.

### Step 5: Move Finished Queue Rows

A queue row is finished when every milestone it names is `DONE` or `DROPPED`. Under the Order rule in `plans.md` "The
Queue File", every finished row sits above every unfinished row. The finished block is the rows above the first
unfinished row. Move each finished row below that point to the end of the finished block, in its current relative
order. Never edit a row's cells.

Then look for rows the queue should no longer hold. An unfinished row of a proposal that is `deferred`, `retracted`,
`superseded`, or `rejected` means the proposal stopped without the steps in `plans.md` "Stopping a Proposal". Report
each one. Do not remove it yourself, since the steps need the user's decisions.

### Step 6 (optional): Trim the Dependency Graph

Skip this step if the proposal index has no dependency graph. The graph lists active proposals only, per `proposals.md`
"Proposal Index". Remove each proposal that this run moved to `implemented`. Drop any edge that only connected
implemented proposals. Keep the edges among proposals that are still active.

### Step 7 (optional): Prune Captured Ideas

Skip this step if the specs directory has no ideas file, such as `spec/ideas.md`. Each idea there is a `##` section. An
idea is captured when a numbered proposal, in any status, has a title or summary that clearly covers the same feature
or concern. Check each idea against the proposal index. When in doubt, keep the idea.

Remove each captured idea's whole section, from its `##` heading to the next heading. Keep the file's intro paragraphs.
Leave a trailing newline at the end of the file.

### Step 8: Verify and Report

Run `proposals.py check` again, and `proposals.py hooks --passed`. Summarize:

- Which proposals were moved to `implemented`
- Which index rows were corrected
- Which queue rows were moved
- Every finding left for the user, and why
- Each revisit hook whose date has passed. Its audit needs the user: act, extend with a reason, or abandon
- Which proposals and edges were removed from the dependency graph, if Step 6 ran
- Which ideas were removed, and the proposal that captured each, if Step 7 ran

## Rules

- Follow `proposals.md` and `plans.md` exactly, unless the project defines its own deviation.
- Never change a milestone's status, and never write an As built block. Those belong to the work that built it.
- Never mark a proposal `implemented` unless every milestone is `DONE` or `DROPPED` and at least one is `DONE`.
- Never tick a milestone check. Checks are never ticked.
- Never pick a revisit audit's outcome, and never move a hook's date. Only the user does.
- Never remove a queue row, and never edit a row's cells. Moving a finished row up is the only queue edit.
- If a proposal file a queue row names does not exist, leave that row alone and note it in the report.
