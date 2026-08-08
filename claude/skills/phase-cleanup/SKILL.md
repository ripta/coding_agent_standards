---
name: phase-cleanup
description: |
  Sync phase-tracking artifacts after milestones complete. Scans a project's phases
  directory for phases whose milestones are all DONE, flips their status to COMPLETE,
  and propagates that completion to the phase index and the originating proposal
  (and its index).
model: sonnet
allowed-tools: Read, Edit, Glob, Grep
---

You keep a project's phase-tracking artifacts in sync after milestones finish, following the phase model in `project-management/plans.md` (from the coding-agent-standards repo, in context when `profiles/baseline.md` is imported; when it is not readable, follow the format reproduced in this skill). Always defer to a project-specific deviation when one exists.

## Workflow

### Step 1: Locate the Phases Directory and Index

Find the phases directory by checking common locations (`spec/phases/`, `docs/phases/`, `phases/`). Read its `index.md` if present — the status summary table is the fastest way to see every phase and its current status. If there is no index, enumerate phase files directly (`phase-N-*.md`).

### Step 2: Identify Newly-Completed Phases

For each phase whose Status is not already `COMPLETE`, read its Milestones table. A phase is complete when every milestone row has Status `DONE`. Phases with any `NOT STARTED` or `IN PROGRESS` milestone stay as-is.

Then read the phase's `## Acceptance Criteria`, which are written per milestone. If a milestone reads `DONE` but has unchecked criteria, the two artifacts disagree. Do not resolve it yourself and do not tick the boxes. Report the mismatch, leave that phase alone, and let the user decide which one is wrong.

Report the list of newly-completed phases found. If none, inform the user and stop.

### Step 3: Update Each Phase Document

For each newly-completed phase, update its own file: change `**Status:**` from `PLANNED` or `IN PROGRESS` to `COMPLETE`.

### Step 4: Update the Phase Index

In the phases directory's `index.md`, update the row for each completed phase: set Status to `COMPLETE` and Progress to the full milestone count (e.g. `5/5`).

If the index has a Pending Phases section, remove any completed phase still listed there. That section holds only `PLANNED` phases.

### Step 5: Update the Originating Proposal

For each completed phase, find the proposal it implements (the `Implements:` line in its Scope section). A proposal may be split across multiple phases, so check the phase index for every other phase that also implements the same proposal:

- If every phase implementing that proposal is now `COMPLETE`, and the proposal's status is `scheduled`, change it to `implemented`.
- If other phases implementing the same proposal are still incomplete, leave the proposal's status as-is and note this in the report.
- If the proposal's status is already `implemented` or anything else, leave it and note why.

### Step 6: Update the Proposal Index

Update the matching rows in the proposals directory's `index.md` to reflect each changed proposal status.

### Step 7: Report

Summarize:

- Which phases were moved to `COMPLETE`
- Which proposal statuses were updated
- Any phases or proposals that were left unchanged, and why

## Rules

- Follow the phase and milestone model in `project-management/plans.md` exactly, unless the project defines its own deviation.
- Never mark a phase `COMPLETE` unless every milestone in its table is `DONE`.
- Never tick an acceptance criterion. That is the implementer's record, and a `DONE` milestone with unchecked criteria is a disagreement to report, not to paper over.
- Update the phase document, phase index, proposal, and proposal index together — per plans.md's Artifact Sync rules, these updates are part of the work, not an afterthought.
- Do not advance a proposal to `implemented` while any of its other phases remain incomplete.
- If a phase has no matching proposal file, leave the proposal step for that phase and note it in the report.
