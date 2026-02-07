# Plans (Phases)

A phase is a unit of implementation work. Each phase implements exactly one proposal (or a portion of one).

## Rules

- One proposal per phase; never combine proposals in a single phase
- A proposal may be split across multiple phases
- Phase numbers are sequential integers (1, 2, 3...)
- Phases may be renumbered if not yet started (to insert new work)
- Proposal numbers are permanent and never change

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
