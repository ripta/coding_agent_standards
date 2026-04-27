# Proposals

A proposal describes a feature or change at the design level before implementation begins.

## Lifecycle

```
draft → designing → accepted → scheduled → implemented
                       ↓
               deferred / rejected
```

- **draft**: Initial concept, incomplete
- **designing**: Under active design; open questions being resolved
- **accepted**: Design finalized, ready for implementation
- **scheduled**: Assigned to a phase
- **implemented**: Work merged
- **deferred**: Paused indefinitely; may revisit
- **rejected**: Will not implement

## Proposal Document Format

```markdown
# PROJ-NNN: Title

**Status:** draft
**Created:** YYYY-MM-DD
**Updated:** YYYY-MM-DD

## Dependencies
- PROJ-NNN (if any)

## Summary
Brief description of the proposal.

## Motivation
Why this change is needed.

## Design Decisions (Settled)
Decisions made with rationale.

## Design Decisions (Open)
Unresolved questions with candidate options.

## Milestones
Implementable chunks of work.

## Decision Log
Minor decisions with dates. Significant architectural decisions
should be extracted to an ADR and referenced here.

## References
- ADR-NN: decision explanation
```

## Rules

- Sequential numbering per project: `PROJ-001`, `PROJ-002`, etc.
- Numbers are permanent and never reused
- One proposal per file
- File naming: `PROJ-NNN-short-description.md` (kebab-case)

## Proposal Index (Optional)

When creating the first proposal for a project, offer to create an `index.md` in the proposals directory. The index makes scanning many proposals easier at the cost of maintaining an extra file.

Contents:

- Optional link to a glossary or other shared references at the top
- A table with columns: Proposal, Description, Status
- One row per proposal, with the proposal ID linking to its file
- An optional dependency graph section for active proposals, topologically ordered with arrows (`←`) pointing to dependencies; omit implemented proposals

Example table:

```markdown
| Proposal | Description | Status |
|----------|-------------|--------|
| [PROJ-001](PROJ-001-short-description.md) | Short description | implemented |
| [PROJ-002](PROJ-002-short-description.md) | Short description | accepted |
```

Update the index whenever a proposal is created or its status changes.
