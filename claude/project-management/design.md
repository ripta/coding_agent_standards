# Architecture Decision Records (ADRs)

An ADR captures a significant architectural decision with its context and consequences.

## Lifecycle

```
proposed → accepted → superseded / deprecated
```

- **proposed**: Under discussion
- **accepted**: In effect
- **superseded**: Replaced by a newer ADR (link to replacement)
- **deprecated**: No longer applicable

## ADR Document Format

```markdown
# ADR-NN: Short Descriptive Title

**Status:** accepted
**Date:** YYYY-MM-DD

## Context
What problem are we solving? What constraints exist?

## Decision
What did we decide to do?

## Rationale
Why this decision over alternatives?

## Consequences
What are the tradeoffs? Positive and negative. Name any obligation the decision creates, but do not track it here.

## Alternatives Considered
What other options did we evaluate?

## References
- PROJ-NNN (originating proposal, if any)
- Related ADRs
```

## Rules

- ADRs are immutable once accepted; to change, create a new superseding ADR
- Sequential numbering with 2-digit zero-padding: `ADR-01`, `ADR-02`, etc. A project that already uses another width,
  such as `ADR-0001`, keeps it. Match the padding of existing ADR files
- File naming: `ADR-NN-short-description.md` (kebab-case)
- Numbers are permanent and never reused
- Old ADRs stay in the repo marked as superseded, not deleted

## What Does Not Belong in an ADR

An ADR records one decision and why it was made. It holds nothing that changes after acceptance, because it is
immutable. Keep these out:

- Future work, follow-up tasks, and TODO lists. Put them in a proposal or a phase.
- Bugs and known issues. Put them in the project's bugs directory or issue tracker.
- Implementation status or progress. Phase milestone rows hold that.
- Open questions. Resolve them before the ADR is accepted.
- Step-by-step implementation plans. Put them in a phase document.

A consequence may name work the decision makes necessary, such as "every client must migrate to v2". That is a fact
about the decision. Tracking that work belongs elsewhere. Link to the proposal or phase under References instead.
