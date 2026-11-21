# Architecture Decision Records (ADRs)

An ADR records the principles behind a significant architectural decision, and why each one holds. Most decisions do
not need one. See "What Earns an ADR".

## Principles, Not Implementation

An ADR is foundational. It lists principles and answers why each one holds. It never records an implementation.

An implementation cannot be defended later. A format, mechanism, or layout is one way to meet a goal. Once a better way
appears, nothing says why the old one must stay. A principle can be defended. Its reason either still holds, or it does
not.

Later work cites an ADR to justify a choice. The citation must lead to the reason behind the decision. So each principle
carries its own why. A reader who follows `ADR-07 P2` finds the principle and its reason in one place.

## Lifecycle

```text
proposed → accepted → superseded / deprecated
    ↓          ↓
retracted  retracted
```

- **proposed**: Written, but not yet in effect. An ADR from a proposal stays proposed until that proposal is accepted.
  Whoever accepts the proposal flips its proposed ADRs to accepted. When the proposal is rejected or retracted, its
  proposed ADRs become retracted
- **accepted**: In effect
- **superseded**: Replaced by a newer ADR, because a reason it rests on no longer holds (link to replacement)
- **deprecated**: No longer applicable. The decision was right, and has stopped applying
- **retracted**: Void. The decision was never in effect, or was wrong when written. Give the reason under the status
  line. Only the user retracts an accepted ADR, and a retraction covers only the ADRs the user names

A proposed ADR still records a settled decision. A decision that may still shift is never written as a proposed ADR. It
stays in the proposal as a candidate that waits. See "Recording ADR Candidates".

## ADR Document Format

```markdown
# ADR-NN: Short Descriptive Title

**Status:** accepted
**Date:** YYYY-MM-DD

## Context
What problem forced a decision? What constraints hold?

## Principles
- **P1**: The principle, stated as an invariant or constraint. Why it holds.
- **P2**: Struck on YYYY-MM-DD; see Amendments.

## Carve-outs
- **C1** (relaxes P1): The class of cases where P1 does not apply. Why the exception holds.

## Consequences
What are the tradeoffs? Positive and negative. Name any obligation the decision creates, but do not track it here.

## Alternatives Considered
What other principles did we weigh, and why did we not choose them?

## Amendments
- YYYY-MM-DD: Narrowed P1 to stored data. Its reason never covered data in flight. Removed: "every event".

## References
- PROJ-NNN (originating proposal, if any)
- Related ADRs
```

Leave out an empty Carve-outs or Amendments section.

A principle states the invariant or constraint first, then its reason. It never names the mechanism that meets it. See
"Architecture" below. Rationale that spans several principles goes in Context.

## Rules

- An accepted ADR is edited in place while its reasons hold. It is superseded when one does not. See "Changing an
  Accepted ADR"
- Principle and carve-out handles (`P1`, `C1`) are permanent and never reused. A struck one keeps its handle
- Sequential numbering with 2-digit zero-padding: `ADR-01`, `ADR-02`, etc. A project that already uses another width,
  such as `ADR-0001`, keeps it. Match the padding of existing ADR files
- File naming: `ADR-NN-short-description.md` (kebab-case)
- Numbers are permanent and never reused
- Old ADRs stay in the repo marked as superseded, deprecated, or retracted, not deleted

## Load-Bearing ADRs

Some decisions are broken more often than others, or break silently when they are. A project may list these in a
`## Load-Bearing ADRs` section of the ADR directory's index (`index.md` or `README.md`). This standard does not fix the
rest of the index's layout. Give each one a line on what to watch for. The `adr-impact` agent checks every listed ADR on
every run.

```markdown
## Load-Bearing ADRs

- ADR-07: an outbound event is published only after the change it describes commits. Watch for publishes inside a
  transaction.
```

Keep the list short. An ADR that every change must be checked against is rare.

## Carve-outs

A carve-out is part of the ADR. It names a class of cases where a principle does not apply, and why. It names the
principles it relaxes.

A carve-out describes a condition. It never names a proposal, milestone, ticket, or component instance. "Reads that
never leave the process" is a condition. "PROJ-012's cache" is not. A carve-out tied to one proposal cannot be defended
once that proposal is gone. The next proposal with the same need cannot apply it either.

The ADR's References may still name its originating proposal. That records where the ADR came from. It is not an
exception to any principle.

## Deviating from an ADR

A proposal that departs from an accepted ADR documents the departure in its own `## ADR Deviations` section. The ADR
never points at the proposal. Each entry names the ADR, the principles it departs from, and the carve-outs that cover
it:

```markdown
- ADR-07 P2 under C1: this proposal's reads never leave the process.
```

When no carve-out covers the case, prefer to amend the ADR. Add a general carve-out, or narrow the principle. Then the
ADR stays the full statement of its rule and its exceptions. This is a preference, not a requirement. When the user does
not amend the ADR, the entry gives the proposal's own reason instead:

```markdown
- ADR-07 P2, no carve-out: the import tool runs once, and is deleted after the migration.
```

What matters is that every deviation is documented. A deviation the proposal does not list is a conflict.

## Changing an Accepted ADR

Edit an accepted ADR in place while its reasons still hold. Widening or narrowing a principle is an edit. So is striking
a principle or a carve-out, adding or rewording a carve-out, and adding a principle that serves the ADR's existing
reason. An ADR written too widely or too narrowly gets fixed where it stands.

Write a superseding ADR when a reason no longer holds: the context changed, or the reason was wrong. The old ADR stays
as the record of the reason that was in force. A principle that must reverse is a sign that its reason changed.

Only the user approves a change to what an accepted ADR requires. An agent may propose one. It never applies one on its
own, in any mode.

Each change adds one line to the ADR's `## Amendments` section. The line gives the date, what changed, and why. It
quotes the removed text word for word. Like a carve-out, it gives its reason in terms of the principles, never by naming
a proposal. A struck principle or carve-out keeps its handle, as `**P2**: Struck on YYYY-MM-DD; see Amendments.` A
citation from a frozen proposal then still resolves.

These need no Amendments line: fixing a typo or a broken link, adding a reference, clarifying wording without changing
what it means, and updating the status. Rewriting an older ADR's Decision and Rationale into handled principles counts
as clarifying wording, as long as no principle changes meaning.

## What Earns an ADR

Most design decisions do not need an ADR. The proposal that made a decision already records it, with its options and
rationale. An ADR earns its place when someone could break the decision later without ever reading that proposal.

The name sets the bar. A candidate must pass all three tests: it is architecture, it is a decision, and it is ready to
be a record. When no candidate passes, the right number of ADRs is zero.

### Architecture

The decision is significant and foundational. At least one of these holds:

- **It cuts across the system.** Other components, services, or future work must follow it, such as "an outbound
  event is published only after the change it describes commits"
- **It is hard to reverse.** It commits a schema, a wire format, a published contract, or stored data to a property a
  redeploy cannot undo, such as "stored events stay readable by every later version"
- **It departs from the past.** It replaces an approach the project used before, or an earlier ADR, so the next person
  who finds the old pattern needs to know it is gone

Being hard, debated, or important to one proposal does not pass this test. Neither does a decision that shapes only one
component's internals. Those stay in the proposal or the design doc that made them.

Architecture is the invariant or constraint, never the implementation. See "Principles, Not Implementation". A format,
syntax, mapping, derivation, storage layout, or mechanism is never itself an ADR, even when it is hard to reverse. When
such a choice is hard to reverse, the candidate is the invariant it serves. The concrete form stays in the proposal.

The ADR also states the rule that any change breaking the invariant must follow, such as how a breaking migration keeps
old and new readers working. That rule is a constraint, so it belongs. The migration's steps and their order are a plan,
so the Decision test keeps them out.

To tell the two apart, ask what would force a principle to change. Adding another instance of the same kind must not.
Changing the concrete format must not. Replacing the mechanism with another that serves the same goal must not. When
any of these would, the candidate is implementation. Lift it to the invariant behind it before weighing it.

To apply the last test, name one other mechanism that would serve the same goal. When that alternative would break the
candidate's wording without harming its goal, the wording names a mechanism. Lift it again. For example, "the
coordinator never writes code" is a mechanism. A design that kept the coordinator reachable while a reviewed fix ran
elsewhere would break it. The invariants behind it are that the coordinator stays reachable, and that someone other
than the session that made a claim checks it.

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

A decision against an approach is a decision too. It earns an ADR by the same three tests. The usual case is rejecting a
widely recommended practice: it would make the design more robust, and the project decides its tradeoff is not worth it
here. The ADR keeps later work from adding it back without reading why. Its status is accepted, and its principle names
what is rejected and why. Its carve-outs name where the rejection does not hold.

Most decisions not to do something do not pass the tests. They stay in the proposal that made them.

### Record

Write an ADR only once the decision is settled and well-defined: its scope is clear, and nothing it depends on is still
being measured or designed. A decision that is likely to shift soon, such as one waiting on a benchmark or on an
in-flight proposal, is not ready. Keep it in the proposal until it settles.

Settled does not mean final. A principle found too wide or too narrow later is amended in place. See "Changing an
Accepted ADR".

## Recording ADR Candidates

A candidate is a decision that passes the Architecture and Decision tests. Record every candidate in its originating
proposal's Decision Log, whatever happens to it. Then a later reader can tell a decision that was weighed and declined
from one nobody weighed. A decision with no candidate entry did not pass the bar, or predates this rule.

Each candidate gets one entry. Its claim names the invariant, lifted per "Architecture" above, never the mechanism or
format that serves it. Later reviews inherit the entry's wording, so a mechanism recorded here tends to reach the
user's list unchanged. The entry names the Architecture criterion it meets and ends with its outcome:

```markdown
- 2026-10-17: ADR candidate (hard to reverse): stored events stay readable by every later version. Written as ADR-07.
- 2026-10-17: ADR candidate (cuts across the system): every outbound call retries under one policy. Declined: its README covers it.
- 2026-10-17: ADR candidate (departs from the past): reads come from the source of truth. Waits on the PROJ-012 M3 benchmark.
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

An item that rests on a decision tagged `addition` says so, and names the addition. An ADR turns an addition into a
rule for all later work. See `proposals.md` "Decision Log Tags".

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
