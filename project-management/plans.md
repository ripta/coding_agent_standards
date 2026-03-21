# Plans (Phases)

A phase is a unit of implementation work. Each phase implements exactly one proposal (or a portion of one).

## Rules

- One proposal per phase; never combine or fold phases together
- A proposal may be split across multiple phases
- Phase numbers are sequential integers (1, 2, 3...)
- Proposal numbers are permanent and never change
- Milestones within a phase are numbered from `.1` upward (e.g., Phase 5.1, 5.2, 5.3)

## Before Starting a Phase

- Before beginning implementation work on a proposal, check its status field.
- Only `accepted` or `scheduled` proposals may be implemented.
- If the status is `draft`, `deferred`, or `rejected`, stop and tell the user. This applies even if the user asks you to implement it -- flag the status conflict and ask for confirmation to change the status first.
- A detailed implementation plan does NOT imply the proposal has been accepted. The status field is the sole source of truth.
- Creating a proposal is NOT the same as promoting it. Do not promote a proposal to a phase unless the user explicitly asks. A plan document that contains phase numbers or milestones does not authorize promotion; it is a design sketch until the user says to schedule it.

## Promoting a Proposal to a Phase

When a proposal is accepted and scheduled for implementation:

1. Never renumber completed phases. Completed phases keep their number forever.
2. The new phase gets the next number after the highest existing phase. Renumber existing pending-only phases upward to make room if needed.
3. If a partially-completed phase needs rework due to the new phase, split it:
   - Keep the completed milestones in the original phase and mark it COMPLETE
   - Create a follow-up phase after the new phase containing the rework milestones plus any remaining incomplete milestones from the original
   - Renumber remaining pending phases upward to accommodate both new phases
4. Create milestones numbered from `.1` upward within each new phase.
5. Add the phase(s) to the status summary table and the pending phases section in the implementation plan.
6. Update the proposal's status (and any proposal index) to reflect that implementation is underway.
7. Do not combine or fold phases together; each phase is separate by default.
8. Milestone tables use three columns by default: Milestone, Description, and Status. Valid status values are `NOT STARTED`, `IN PROGRESS`, or `DONE`. Projects may override this format.

## Milestone Workflow

- Read and maintain the implementation plan before and after every milestone
- Confirm with the user before moving on to a new milestone
- Phases and milestones are project management artifacts; do not reference phase or milestone numbers in code or comments

## Phase Document Format

```markdown
# Phase N: Title

**Goal**: One-line description
**Status**: PLANNED | IN PROGRESS | COMPLETE
**Complexity**: LOW | MEDIUM | HIGH
**Dependencies**: None | Phase X, Phase Y

## Scope

Implements: PROJ-NNN (or PROJ-NNN sections 1-3)

## Problem Statement

User-facing issue this phase solves.

## Design Decisions

### Topic
**Decision**: What was decided
**Rationale**: Why this approach

## Implementation

### Files to Modify
1. `path/to/file.ext` - Purpose

### Changes Required
1. Description of change

## Acceptance Criteria
- [ ] Criterion 1
- [ ] Criterion 2
```

## Naming

- File: `phase-N-short-description.md`
- Example: `phase-12-user-authentication.md`
