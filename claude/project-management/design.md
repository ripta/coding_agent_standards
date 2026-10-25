# Architecture Decision Records (ADRs)

An ADR captures a significant architectural decision with its context and consequences. Most decisions do not need
one. See "What Earns an ADR".

## Lifecycle

```
proposed → accepted → superseded / deprecated
```

- **proposed**: Written, but not yet in effect. An ADR from a proposal stays proposed until that proposal is accepted.
  Whoever accepts the proposal flips its proposed ADRs to accepted
- **accepted**: In effect
- **superseded**: Replaced by a newer ADR (link to replacement)
- **deprecated**: No longer applicable

A proposed ADR still records a settled decision. A decision that may still shift is never written as a proposed ADR. It
stays in the proposal as a candidate that waits. See "Recording ADR Candidates".

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
- **It is hard to reverse.** It commits a schema, a wire format, a published contract, or stored data to a property a
  redeploy cannot undo, such as "stored events stay readable by every later version"
- **It departs from the past.** It replaces an approach the project used before, or an earlier ADR, so the next person
  who finds the old pattern needs to know it is gone

Being hard, debated, or important to one proposal does not pass this test. Neither does a decision that shapes only one
component's internals. Those stay in the proposal or the design doc that made them.

Architecture is the invariant or constraint, never the implementation. A format, syntax, mapping, derivation, storage
layout, or mechanism is never itself an ADR, even when it is hard to reverse. When such a choice is hard to reverse, the
candidate is the invariant it serves. The concrete form stays in the proposal.

The ADR also states the rule that any change breaking the invariant must follow, such as how a breaking migration keeps
old and new readers working. That rule is a constraint, so it belongs. The migration's steps and their order are a plan,
so the Decision test keeps them out.

To tell the two apart, ask what would force the ADR to change. Adding another instance of the same kind must not.
Changing the concrete format must not. When either would, the candidate is implementation. Lift it to the invariant
behind it before weighing it.

For example, a name syntax that callers store is implementation. The ADR behind it says that identities shared across
machines carry stable identifiers. It also says how a migration that breaks an identifier must proceed. A new kind of
identity, or a new syntax, leaves that ADR unchanged.

### Decision

An ADR records a choice that has been made, and why. It holds nothing about the future. Keep these out:

- Future work, follow-up tasks, ideas, and TODO lists. Put them in a proposal
- Plans, migration steps, schedules, and target dates. Put the plan in a proposal and the order in the queue. A rule
  every breaking migration must follow is a constraint, not a plan. It belongs, per "Architecture" above
- Bugs and known issues. Put them in the project's bugs directory or issue tracker
- Implementation status or progress. Proposal milestones hold that
- Open questions. Resolve them before the ADR is accepted

A consequence may name work the decision makes necessary, such as "every client must migrate to v2". That is a fact
about the decision. Tracking that work belongs elsewhere. Link to the proposal under References instead.

### Record

An accepted ADR should not need to change. Write it only once the decision is settled and well-defined: its scope is
clear, and nothing it depends on is still being measured or designed. A decision that is likely to shift soon, such as
one waiting on a benchmark or on an in-flight proposal, is not ready. Keep it in the proposal until it settles.

An accepted ADR takes minor edits only: fixing a typo or a broken link, adding a reference, clarifying wording without
changing what it means, and updating its status when it is superseded or deprecated. Anything that changes what was
decided, its scope, or its consequences is a new decision. Write a new ADR that supersedes the old one.

## Recording ADR Candidates

A candidate is a decision that passes the Architecture and Decision tests. Record every candidate in its originating
proposal's Decision Log, whatever happens to it. Then a later reader can tell a decision that was weighed and declined
from one nobody weighed. A decision with no candidate entry did not pass the bar, or predates this rule.

Each candidate gets one entry. It names the Architecture criterion it meets and ends with its outcome:

```markdown
- 2026-10-17: ADR candidate (hard to reverse): stored events stay readable by every later version. Written as ADR-07.
- 2026-10-17: ADR candidate (cuts across the system): retries go through the shared client. Declined: its README covers it.
- 2026-10-17: ADR candidate (departs from the past): drop the cache layer. Waits on the PROJ-012 M3 benchmark.
- 2026-10-17: ADR candidate (hard to reverse): a session belongs to exactly one account. Undecided. Found in PROJ-007 M2.
```

- **Written as ADR-NN**: the ADR exists. The proposal's References lists it too
- **Declined**: the user chose not to write it, or it failed a test on a later check. Give the reason in a few words
- **Waits on**: it fails only the Record test. Name a concrete revisit hook, as "Deferring Decisions" in
  `proposals.md` requires
- **Undecided**: it passes all three tests, but the user has not chosen yet. Implementation runs record candidates this
  way. The next proposal review asks about them

When the outcome changes, edit it in place and add the date of the change, such as `Written as ADR-07 on 2026-11-02`.
Keep the entry's original date. A change with no originating proposal records its candidates in its session report
instead. Without a session report, the run lists them in its final response.

## Listing ADR Candidates

A list of ADR candidates shown to the user holds only candidates that pass all three tests. A candidate that fails any
test stays off the list. Its outcome goes in the Decision Log instead.

Each item names the invariant, not the format or mechanism that implements it. Lift an implementation-level candidate
to its invariant before listing it, per "Architecture" above. Several such candidates may lift to one invariant. List
that invariant once.

Each item shows how it passes every test, in a short phrase per test:

- **Architecture**: the criterion it meets, and the concrete thing that meets it
- **Decision**: the choice it records
- **Record**: why it will not shift

```markdown
- Stored events stay readable by every later version. Architecture: hard to reverse, events persist across deploys.
  Decision: readers accept every past event shape, over rewriting stored events. Record: nothing it depends on is still
  in design.
```

An item that does not show all three tests has not been shown to pass. Treat it as passing none, and leave it off.
