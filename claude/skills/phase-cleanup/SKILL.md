---
name: phase-cleanup
description: |
  Move completed phases from zig_implementation.md to zig_completed_detailed.md.
  Updates the completed phases summary, proposal statuses, and the proposal index.
model: sonnet
allowed-tools: Read, Edit, Glob, Grep
---

You move fully-completed phases out of the "Pending Phases" section of `spec/zig_implementation.md` into
`spec/zig_completed_detailed.md`, and update all related status documents.

## Workflow

### Step 1: Identify Completed Phases

Read the "Pending Phases" section of `spec/zig_implementation.md`. A phase is complete when **every milestone** in its
table has status `DONE`. Phases that are `IN PROGRESS`, `PENDING`, or `NOT STARTED` stay in the pending section.

Report the list of completed phases found. If none, inform the user and stop.

### Step 2: Read zig_completed_detailed.md Tail

Read the last ~50 lines of `spec/zig_completed_detailed.md` to find the last phase entry and understand the current
format. Each entry follows this structure:

```markdown
## Phase N: Title (PROJ-NNN)

| Milestone | Description | Status |
|-----------|-------------|--------|
| N.1 | Description | DONE |

Summary paragraph describing what was added and why.

**Key files:** `path/to/file1`, `path/to/file2`
```

If a phase had a `**Depends on:**` line, preserve it between the heading and the table.

### Step 3: Append to zig_completed_detailed.md

For each completed phase, append an entry after the last existing phase. Include:

1. `## Phase N: Title (PROJ-NNN)` heading
2. Dependency note if present (e.g., `**Depends on:** Phases X-Y (description)`)
3. Milestone table (copied from pending section)
4. A 2-3 sentence summary paragraph derived from the milestone descriptions — what was added and why it matters
5. `**Key files:**` line listing the primary files mentioned in the milestones

### Step 4: Remove from zig_implementation.md

Delete the completed phase entries from the "Pending Phases" section. The first remaining in-progress or pending phase
should now be the first entry under `## Pending Phases`.

### Step 5: Update zig_completed_topics.md

In `spec/zig_completed_topics.md`, add brief summaries for each moved phase to the appropriate topic group:

- Match the phase's domain to an existing topic heading (e.g., "Numeric Tower", "Parsing and Pragmas", "Infrastructure
  and Tooling")
- Update the heading's phase list to include the new phase numbers
- Append a sentence or two to the topic's paragraph describing the new phases
- If no existing topic fits, extend "Infrastructure and Tooling" as a catch-all

### Step 6: Update zig_index.md

In `spec/zig_index.md`, update the status table rows for each moved phase: change `PENDING` to `DONE` and update the
progress column to reflect completion.

### Step 7: Update Proposal Statuses

For each moved phase, check the corresponding project proposal file (`spec/proposals/PROJ-NNN-*.md`):

1. Read its `**Status:**` line
2. If it says `scheduled`, change it to `implemented`
3. If it already says `implemented`, skip it

Then update the matching rows in `spec/proposals/index.md` index table to match.

### Step 8: Clean Up ideas.md

Read `spec/proposals/ideas.md`. For each idea section (`## Idea: ...`), check whether the idea has been captured in a numbered
project proposal (regardless of that proposal's status). Cross-reference against the `spec/proposals/index.md` index.

An idea is "captured" if there is a project whose title or summary clearly covers the same feature or concern. When in
doubt, err on the side of keeping the idea.

For each captured idea, remove its entire section (the `## Idea:` heading and all paragraphs under it) from `ideas.md`.
Leave a trailing newline at the end of the file.

### Step 9: Report

Summarize what was done:

- Which phases were moved
- Which proposal statuses were updated
- Any phases that were skipped (still in progress) and why
- Which ideas were removed from ideas.md and which project they corresponded to
