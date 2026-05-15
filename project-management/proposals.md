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

- Sequential numbering per project, prefixed with a short project-specific token in place of `PROJ`. Pick a prefix that
  is easily distinguishable and identifiable for the project (e.g., `HP-001` for hotpod, `RPT-001` for a project named
  Reporting). `PROJ-` is permitted but discouraged when a more specific prefix is available; the prefix is fixed once
  chosen.
- Numbers are permanent and never reused
- One proposal per file
- File naming: `<PREFIX>-NNN-short-description.md` (kebab-case), where `<PREFIX>` is the project-specific token

## Deferring Decisions

When a design question cannot be resolved at proposal time and is intentionally deferred, the deferral must point at a concrete revisit mechanism. Vague deferrals like "revisit if needed" or "we'll see in implementation" are not acceptable, because the question gets forgotten.

Acceptable revisit hooks include:

- A specific milestone in the proposal that revisits the question (e.g., "validated under the empirical-review milestone")
- A named follow-up proposal that will be filed to capture the resolution (e.g., "if X is observed, file PROJ-NNN with the chosen mitigation")
- A condition tied to a specific artifact, such as golden output review or a performance benchmark, that determines when the question is reopened

Every deferred question must move from the Open section to the Settled section as a "decision to defer" with the revisit hook captured both in the settled entry and in the Decision Log.

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
