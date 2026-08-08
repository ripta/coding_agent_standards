# Plans (Phases)

A phase is a unit of implementation work. Each phase implements exactly one proposal (or a portion of one).

## Rules

- One proposal per phase; never combine or fold phases together
- A proposal may be split across multiple phases
- Phase numbers are sequential integers (1, 2, 3...)
- Proposal numbers are permanent and never change
- Milestones within a phase are numbered from `.1` upward, and are referred to as `Phase 5.1`, `Phase 5.2`, `Phase 5.3`. Bare `Phase 5` means the whole phase. Proposal milestones use a different form; see `tracking.md` "Referring to Milestones"
- Acceptance criteria are written per milestone, not per phase. Each criterion belongs to exactly one milestone. A
  milestone is then reviewable against its own floor while the rest of the phase is still in progress
- Milestones are units of implementation work only. Design work -- a design spike,
  an ADR, a research write-up -- is NOT an implementation milestone. Never list a
  design spike as a numbered row in a phase's milestone table, and never count it
  toward the phase's milestone progress. A phase whose only completed work is design
  is `PLANNED` with `0/N`, not `IN PROGRESS`. Record design completion in the
  proposal/phase Design Decisions, the ADR, and any research document -- not as a
  numbered, DONE milestone.

## Before Starting a Phase

- Before beginning implementation work on a proposal, check its status field.
- Only `accepted` or `scheduled` proposals may be implemented.
- If the status is `draft`, `deferred`, or `rejected`, stop and tell the user. This applies even if the user asks you to implement it -- flag the status conflict and ask for confirmation to change the status first.
- A detailed plan does NOT imply the proposal has been accepted. The status field is the sole source of truth.
- Creating a proposal is NOT the same as promoting it. Do not promote a proposal to a phase unless the user explicitly asks. A plan document that contains phase numbers or milestones does not authorize promotion; it is a design sketch until the user says to schedule it.
- Evaluate whether the planned work requires refactoring existing code. If a feature would be substantially cleaner after restructuring nearby code, include that work in the phase scope rather than deferring it or working around it.

## Promoting a Proposal to a Phase

When a proposal is accepted and scheduled for implementation:

1. Never renumber completed phases. Completed phases keep their number forever.
2. The new phase gets the next number after the highest existing phase. Renumber existing pending-only phases upward to make room if needed.
3. If a partially-completed phase needs rework due to the new phase, split it:
   - Keep the completed milestones in the original phase and mark it COMPLETE
   - Create a follow-up phase after the new phase containing the rework milestones plus any remaining incomplete milestones from the original
   - Renumber remaining pending phases upward to accommodate both new phases
4. Create milestones numbered from `.1` upward within each new phase. These are phase-local and do not inherit the proposal's milestone numbers.
5. Add the phase(s) to the status summary table and the Pending Phases section of the phase index.
6. Update the proposal's status and the proposal index to reflect that implementation is underway.
7. Do not combine or fold phases together; each phase is separate by default.
8. Milestone tables use four columns: Milestone, Proposal, Description, and Status. Valid status values are `NOT STARTED`, `IN PROGRESS`, or `DONE`. The Proposal column names the proposal milestone each row implements, written in `PROJ-004 M1` form. It is what makes a proposal milestone's status answerable, so a project that overrides this format must keep it.

## Milestone Workflow

- Read and maintain the phase document and the phase index before and after every milestone
- Confirm with the user before moving on to a new milestone
- Phases and milestones are project management artifacts; do not reference phase or milestone numbers in code or comments
- If the originating proposal defers a decision to one of its milestones, the phase milestone that implements it must explicitly name the deferred questions it is responsible for revisiting (see `proposals.md` "Deferring Decisions")

## Artifact Sync

Every phase document must include steps to update tracking artifacts as work progresses. These updates are part of the work, not an afterthought.

- When a milestone completes: tick its acceptance criteria, then update the phase document status and the phase index
- When a phase completes: update the phase status to COMPLETE, update the proposal status, and update both index pages
- When a phase begins: update the phase status to IN PROGRESS, remove it from Pending Phases, and update both index pages
- Plans must list which tracking artifacts exist and will be updated; do not assume they can be skipped

## Phase Document Format

```markdown
# Phase N: Title

**Goal:** One-line description
**Status:** PLANNED | IN PROGRESS | COMPLETE
**Complexity:** LOW | MEDIUM | HIGH
**Dependencies:** None | Phase X, Phase Y

## Scope

Implements: PROJ-NNN (or PROJ-NNN sections 1-3)

## Problem Statement

User-facing issue this phase solves.

## Design Decisions

### Topic
**Decision:** What was decided
**Rationale:** Why this approach

## Milestones

| Milestone | Proposal | Description | Status |
|-----------|----------|-------------|--------|
| N.1 | PROJ-NNN M1 | Description | NOT STARTED |
| N.2 | PROJ-NNN M2 | Description | NOT STARTED |

## Implementation

### Files to Modify
1. `path/to/file.ext` - Purpose

### Changes Required
1. Description of change

## Acceptance Criteria

### Phase N.1
- [ ] Criterion 1
- [ ] Criterion 2

### Phase N.2
- [ ] Criterion 1
```

## Naming

- File: `phase-N-short-description.md`
- Example: `phase-12-user-authentication.md`

## Phase Index

When creating the first phase for a project, create an `index.md` in the phases directory, even if this is the only phase that will ever exist.

Contents:

- A brief explanation that each phase implements one proposal (or a portion of one), and each phase contains one or more milestones
- A status summary table with columns: Phase, Proposal, Description, Status, Progress
- One row per phase; progress shown as completed/total milestones (e.g., `3/5`)
- A Pending Phases section listing the phases that are `PLANNED` but not yet started. A phase is added on promotion
  and removed the moment it begins, so the section holds exactly the `PLANNED` rows of the table above it
- A note to update the file as phases progress

Example table:

```markdown
| Phase | Proposal | Description | Status | Progress |
|-------|----------|-------------|--------|----------|
| 1 | PROJ-001 | Short description | COMPLETE | 4/4 |
| 2 | PROJ-002 | Short description | IN PROGRESS | 2/5 |
| 3 | PROJ-003 | Short description | PLANNED | 0/3 |
```

Update the index whenever a phase is created, a milestone completes, or a phase status changes.
