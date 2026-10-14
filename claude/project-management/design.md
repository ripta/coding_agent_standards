# Architecture Decision Records (ADRs)

An ADR captures a significant architectural decision with its context and consequences. Most decisions do not need
one. See "What Earns an ADR".

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

- An accepted ADR takes minor edits only. A change to what it decides gets a new, superseding ADR. See "Record"
- Sequential numbering with 2-digit zero-padding: `ADR-01`, `ADR-02`, etc. A project that already uses another width,
  such as `ADR-0001`, keeps it. Match the padding of existing ADR files
- File naming: `ADR-NN-short-description.md` (kebab-case)
- Numbers are permanent and never reused
- Old ADRs stay in the repo marked as superseded, not deleted

## Load-Bearing ADRs

Some decisions are broken more often than others, or break silently when they are. A project may list these in a
`## Load-Bearing ADRs` section of the ADR directory's index (`index.md` or `README.md`). This standard does not fix the
rest of the index's layout. Give each one a line on what to watch for. The `adr-impact` agent checks every listed ADR on
every run.

```markdown
## Load-Bearing ADRs

- ADR-07: every outbound event goes through the outbox. Watch for direct publishes to the message bus.
```

Keep the list short. An ADR that every change must be checked against is rare.

## What Earns an ADR

Most design decisions do not need an ADR. The proposal that made a decision already records it, with its options and
rationale. An ADR earns its place when someone could break the decision later without ever reading that proposal.

The name sets the bar. A candidate must pass all three tests: it is architecture, it is a decision, and it is ready to
be a record. When no candidate passes, the right number of ADRs is zero.

### Architecture

The decision is significant and foundational. At least one of these holds:

- **It cuts across the system.** Other components, services, or future work must follow it, such as "every outbound
  event goes through the outbox"
- **It is hard to reverse.** It fixes a schema, a wire format, a published contract, or stored data in a way a redeploy
  cannot undo
- **It departs from the past.** It replaces an approach the project used before, or an earlier ADR, so the next person
  who finds the old pattern needs to know it is gone

Being hard, debated, or important to one proposal does not pass this test. Neither does a decision that shapes only one
component's internals. Those stay in the proposal or the design doc that made them.

### Decision

An ADR records a choice that has been made, and why. It holds nothing about the future. Keep these out:

- Future work, follow-up tasks, ideas, and TODO lists. Put them in a proposal or a phase
- Plans, migration steps, schedules, and target dates. Put them in a proposal or a phase document
- Bugs and known issues. Put them in the project's bugs directory or issue tracker
- Implementation status or progress. Phase milestone rows hold that
- Open questions. Resolve them before the ADR is accepted

A consequence may name work the decision makes necessary, such as "every client must migrate to v2". That is a fact
about the decision. Tracking that work belongs elsewhere. Link to the proposal or phase under References instead.

### Record

An accepted ADR should not need to change. Write it only once the decision is settled and well-defined: its scope is
clear, and nothing it depends on is still being measured or designed. A decision that is likely to shift soon, such as
one waiting on a benchmark or on an in-flight proposal, is not ready. Keep it in the proposal until it settles.

An accepted ADR takes minor edits only: fixing a typo or a broken link, adding a reference, clarifying wording without
changing what it means, and updating its status when it is superseded or deprecated. Anything that changes what was
decided, its scope, or its consequences is a new decision. Write a new ADR that supersedes the old one.
