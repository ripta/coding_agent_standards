# Proposals

A proposal describes a feature or change at the design level before implementation begins.

## Lifecycle

```
draft → designing → accepted → scheduled → implemented
                       ↓
               deferred / rejected
```

Any status may become **superseded**. Any status except `implemented` may become **retracted**.

- **draft**: Initial concept, incomplete
- **designing**: Under active design; open questions being resolved
- **accepted**: Design finalized, ready for implementation
- **scheduled**: Assigned to a phase
- **implemented**: Work merged
- **deferred**: Paused indefinitely; may revisit
- **rejected**: Will not implement
- **superseded**: Replaced by a different proposal, from any prior status (with reference to the other proposal)
- **retracted**: No longer in effect, from any unimplemented status (with reason)

## Proposal Document Format

```markdown
# PROJ-NNN: Title

**Status:** draft
**Created:** YYYY-MM-DD
**Updated:** YYYY-MM-DD

## Dependencies

- PROJ-NNN (if any)

## Impacts

- PROJ-NNN — section(s) of this proposal that affect it

## Summary

Brief description of the proposal.

## Motivation

Why this change is needed.

## Design Decisions (Settled)

Decisions made with rationale.

## Design Decisions (Open)

Unresolved questions with candidate options.

## Risks

- **Risk description** — likelihood: medium, impact: high.
  Mitigation: how it is reduced or detected early. (Or — Accepted: why it is tolerable.)

## Milestones

Implementable chunks of work.

| Milestone | Description |
|-----------|-------------|
| 1 | Description |
| 2 | Description |

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
- Milestones are plain ordinals counting from 1, and never carry the proposal number as a prefix. Refer to one as
  `PROJ-004 milestone 5`, or `PROJ-004 M5` for short. See `tracking.md` "Referring to Milestones"
- Milestones carry no status. To find one's status, read the phase milestone rows whose Proposal column names it. See
  `tracking.md` "Status Vocabularies"
- A proposal never depends on a phase. See `tracking.md` "Dependency Direction"

## Deferring Decisions

When a design question cannot be resolved at proposal time and is intentionally deferred, the deferral must point at a concrete revisit mechanism. Vague deferrals like "revisit if needed" or "we'll see in implementation" are not acceptable, because the question gets forgotten.

Acceptable revisit hooks include:

- A specific milestone in the proposal that revisits the question (e.g., "validated under PROJ-004 M5")
- A named follow-up proposal that will be filed to capture the resolution (e.g., "if X is observed, file PROJ-NNN with the chosen mitigation")
- A condition tied to a specific artifact, such as golden output review or a performance benchmark, that determines when the question is reopened

Every deferred question must move from the Open section to the Settled section as a "decision to defer" with the revisit hook captured both in the settled entry and in the Decision Log.

## Risks

Every proposal carries a Risks section describing what could go wrong with the design — not implementation bugs, but design-level exposure: wrong assumptions, one-way doors, blast radius, failure modes nobody would notice.

- Each risk states a **likelihood** and an **impact** (low/medium/high) and carries either a **mitigation** (how the risk is reduced or detected early) or an explicit **acceptance** with rationale. A risk with neither is an open design question and belongs in Design Decisions (Open) instead.
- One-way-door decisions — hard or impossible to reverse after shipping, such as schema or data migrations, published API contracts, wire formats, or data backfills — must appear as risks unless the design itself removes the irreversibility (e.g., a down-migration, versioned contract, or feature flag), in which case the settled decision notes that.
- "None identified" is acceptable only with a one-sentence reason (e.g., purely additive tooling with no consumers).
- A risk rated high likelihood and high impact blocks advancing the proposal to `accepted` until it is mitigated or explicitly accepted, with the acceptance recorded in the Decision Log.
- Deferring a risk's mitigation follows the same rules as deferring a decision: it needs a concrete revisit hook (see "Deferring Decisions").

## Cross-Proposal Impact

When a design decision in one proposal would change later proposals, the first proposal must note this. If proposal A has a decision that affects proposals B and C, A's text says so, and B and C are updated at the time A is decided, reviewed, or designed.

The Dependencies section already captures one direction (Y depends on X). The reverse — that X knows Y cares about a specific part of X — is worth capturing too. Note the impacted proposal *and* the specific section(s) of this proposal it cares about, not the entirety (unless that's accurate).

This is a recommended practice, not a strict requirement. Prioritize it on:

- Large projects (roughly 100+ proposals) where holding all the cross-references in your head no longer works.
- Projects that draft proposals in waves of 3–4 or more at once, where drift is most likely.

For small projects with one proposal in flight at a time, the maintenance cost usually isn't worth it.

Rot is expected. The list of impacted proposals can grow stale as work progresses. When drift is obvious while editing a proposal, fix or remove the stale references opportunistically, even if cleanup wasn't why you opened the file. If rot becomes unmanageable, this approach may be replaced with something else.

## Proposal Index

When creating the first proposal for a project, create an `index.md` in the proposals directory, even if this is the only proposal that will ever exist.

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
