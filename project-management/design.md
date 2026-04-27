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

**Status**: Accepted
**Date**: YYYY-MM-DD

## Context
What problem are we solving? What constraints exist?

## Decision
What did we decide to do?

## Rationale
Why this decision over alternatives?

## Consequences
What are the tradeoffs? Positive and negative.

## Alternatives Considered
What other options did we evaluate?

## References
- PROJ-NNN (originating proposal, if any)
- Related ADRs
```

## Rules

- ADRs are immutable once accepted; to change, create a new superseding ADR
- Sequential numbering with 2-digit zero-padding: `ADR-01`, `ADR-02`, etc.
- File naming: `ADR-NN-short-description.md` (kebab-case)
- Numbers are permanent and never reused
- Old ADRs stay in the repo marked as superseded, not deleted
