# Proposals

A proposal describes a feature or change at the design level before implementation begins.

## Lifecycle

```text
draft → designing → accepted → implemented
                       ↓
               deferred / rejected
```

Any status may become **superseded**. Any status except `implemented` may become **retracted**.

- **draft**: Initial concept, incomplete
- **designing**: Under active design; open questions being resolved
- **accepted**: Design finalized, ready for implementation. Scheduling it adds queue rows and leaves its status alone.
  See `plans.md` "Scheduling a Proposal"
- **implemented**: Every milestone is finished, and at least one is `DONE`. See "Milestone Status"
- **deferred**: Paused, with a revisit hook that says when to look again. See "Revisit Hooks"
- **rejected**: Will not implement
- **superseded**: Replaced by a different proposal, from any prior status (with reference to the other proposal)
- **retracted**: No longer in effect, from any unimplemented status (with reason)

## Proposal Document Format

```markdown
# PROJ-NNN: Title

**Status:** draft
**Created:** YYYY-MM-DD
**Updated:** YYYY-MM-DD
**Revisit:** (deferred proposals only) when <condition>; on or after YYYY-MM-DD (<anchor>)

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

### M1: Title

**Status:** NOT STARTED

One-line goal (optional).

- A check the finished work must pass
- Another check

### M2: Title

**Status:** DONE

- A check the finished work must pass

**As built:**

- What implementation found that the checks above do not say

## Decision Log

Minor decisions with dates. Each ADR candidate gets an entry with its
outcome, per design.md "Recording ADR Candidates".

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
- A milestone's number is permanent once any queue row names it. Until then it may be renumbered
- A proposal never depends on a queue row. See `tracking.md` "Dependency Direction"
- A proposal may carry an optional `**Tradeoffs:** expedient — <reason>` line after `**Updated:**`. It lowers the bar
  for design options in the proposal and in the queue rows that implement it. Add it only when the user asks for it.
  See the "Choosing Options" section of `rules/decision-making.md`
- A `deferred` proposal carries a `**Revisit:**` line after `**Updated:**`. See "Revisit Hooks"

## Milestones

A milestone is a subsection of the Milestones section. Its heading is `### MN: Title`. A `**Status:**` line follows,
then an optional one-line goal. Then come plain bullets, each phrased as a check. The bullets are the milestone's
acceptance criteria. There is no separate description and no separate checklist.

The bullets are never ticked. A ticked box would be a second record of progress beside the milestone's status.

Rationale goes in Design Decisions or in the goal line, not in a bullet. A measurement or decision-revisit milestone
states its check as a recorded result, such as "the gate result and every slower row are recorded in the As built
block".

### Milestone Status

A milestone's `**Status:**` line is the only record of its execution progress. The values are:

- `NOT STARTED`: no work has begun
- `IN PROGRESS`: work has begun and is not finished
- `DONE`: the work is merged and its checks pass
- `DROPPED`: the work will not be done under this milestone

A milestone is finished when it is `DONE` or `DROPPED`. `DROPPED` is terminal. A dropped milestone is never revived.
New work takes a new milestone number.

Dropping a milestone is a divergence, and needs the user's approval. Its reason goes in the Decision Log, and the
milestone's As built block links to that entry. When the work moved to another milestone, the As built block also
carries a fixed line:

```markdown
Replaced by: PROJ-NNN MN
```

The line names only a milestone that a queue row names, since only those are never renumbered. Until the replacing work
is scheduled, it names the replacing proposal, `Replaced by: PROJ-NNN`.

An `accepted` proposal becomes `implemented` when every milestone is finished and at least one is `DONE`. Whoever
finishes the last milestone writes `implemented` in the proposal and the proposal index.

A check reports each of these:

- A milestone status outside the four values above. A misspelling such as `CANCELED` would otherwise read as pending
  forever
- A `DROPPED` milestone with no Decision Log link
- A `Replaced by` line that names a milestone that does not exist, one that is itself `DROPPED`, or one that no queue
  row names
- An `accepted` or `implemented` proposal whose status disagrees with its milestones, in either direction
- An `accepted` proposal whose milestones are all `DROPPED`. It can never become `implemented`, and its dependents would
  wait silently. The user retracts or supersedes it
- An `accepted` proposal whose milestones are not in this form. Live work must carry milestone status

The check skips `deferred`, `rejected`, `superseded`, and `retracted` proposals, whose milestones may be dropped without
the proposal being built. It also skips history from earlier eras. `scripts/proposals.py check` in the plugin runs it.

### As Built

Each milestone that has started ends with an `**As built:**` block. It records what implementation found: bugs found
and fixed along the way, residuals, measurements, fixture choices, and scope narrowed. A `DONE` or `DROPPED` milestone
always has one, even if it says only "Nothing beyond the checks." The fixed label keeps a note from blending into the
checks above it.

The block follows these rules:

- A bug with its own file is linked, not retold
- Lists of files, symbols, and line numbers are left out. They lose their value once the work merges
- Measurement tables go in one named place, the Decision Log or a linked research document
- A divergence's reason lives only in the Decision Log. The as-built note points to it
- A note that spans milestones goes on the milestone that found it. A note about ordering goes in the queue

Keeping the note beside the milestone text lets a reader check the text against what shipped in one read.

## Amending a Proposal

When implementation changes, narrows, or corrects a decision or milestone, edit that decision or milestone text in
place. A Decision Log entry records the change, its date, what the text said before, and why it changed. Recording it in
the Decision Log alone is not enough. The text a reader trusts would stay wrong.

An amended decision or milestone carries one marker, such as "Amended 2026-10-17; see Decision Log." A later revision
replaces the marker. It does not add a second one. The marker tells a reader the text changed. The log entry keeps the
prior meaning without relying on git history, which does not follow a spec moved between repos.

Amending a decision that an accepted ADR records needs a new ADR that supersedes it. An accepted ADR takes minor edits
only, so editing the proposal alone would leave the two disagreeing. See `design.md` "Record".

## Implemented Proposals Are Frozen

Once a proposal is `implemented`, only these edits are allowed:

- Corrections of fact in its As built blocks
- Correcting a wrong claim about what shipped
- Links and references
- A "Superseded in part by PROJ-NNN; see Decision Log" marker on a replaced decision or milestone
- Decision Log entries that record a revisit-hook audit, and replacing the hook's date after that audit
- Status changes the lifecycle allows from `implemented`, such as to `superseded`
- The `**Updated:**` date

Any other change goes to a new proposal.

When the text and the shipped code disagree, the user says which is wrong. When the code is wrong, it is a bug, and the
text stays. When the text is wrong, it is a correction of fact. Its Decision Log entry says "Correction of fact" and
gives the prior meaning.

The freeze check enforces this. For each proposal a commit ever marked `implemented`, it diffs the file from that commit
to the working tree, whatever the status says now. That commit is the base, so the commit that writes `implemented` and
the last As built block is never a frozen edit. A proposal imported already `implemented` uses its first commit. A
status change passes only to `superseded`, and a `**Revisit:**` change only with its audit in the Decision Log.

The check reports every change outside the list, and says whether the work under review made it. Uncommitted edits count
as the work's own. A change someone else made goes to the user, never to the implementer. `scripts/proposals.py freeze`
in the plugin runs it.

## Revisit Hooks

A revisit hook says when to look at deferred work again. It is one line:

```markdown
**Revisit:** when the parser handles streaming input; on or after 2027-01-15 (two releases after PROJ-012 ships)
```

It carries a condition, an on-or-after date with the anchor that justifies it, or both. A date without an anchor is
not a hook. The anchor says why that date, such as a release, a measurement window, or another proposal landing.

Every `deferred` proposal carries one, after `**Updated:**`. Deferred work that has no proposal becomes a `deferred`
proposal. A deferred decision carries one in its settled entry. See "Deferring Decisions".

When the date passes, an audit is required. Its outcome is one of these:

- Act: the deferred work resumes, or the decision is settled
- Extend: the date moves later, with the reason
- Abandon: the work is retracted or rejected, or the decision is closed

The outcome goes in the Decision Log, and the hook's date is replaced.

## History from Earlier Eras

A proposal is history from an earlier era when it is no longer live and its milestones are not in the form above. No
longer live means `implemented`, `rejected`, `superseded`, or `retracted`. An era 1 milestone table with a status column
does not count as the era 3 form, though it uses the same status words. See `eras.md`.

The check and the tools skip history. A milestone of an `implemented` history proposal counts as met for a plain
dependency on it. A `(deployed)` dependency on it stays unmet until the user confirms the deployment.

## Deferring Decisions

When a design question cannot be resolved at proposal time and is intentionally deferred, the deferral must point at a
concrete revisit mechanism. Vague deferrals like "revisit if needed" or "we'll see in implementation" are not
acceptable, because the question gets forgotten.

Acceptable revisit hooks include:

- A specific milestone in the proposal that revisits the question (e.g., "validated under PROJ-004 M5")
- A named follow-up proposal that will be filed to capture the resolution (e.g., "if X is observed, file PROJ-NNN with
  the chosen mitigation")
- A condition tied to a specific artifact, such as golden output review or a performance benchmark, that determines when
  the question is reopened

Every deferred question must move from the Open section to the Settled section as a "decision to defer" with the revisit
hook captured both in the settled entry and in the Decision Log. A hook with a condition or a date is written as a
`**Revisit:**` line. See "Revisit Hooks".

## Risks

Every proposal carries a Risks section describing what could go wrong with the design — not implementation bugs, but
design-level exposure: wrong assumptions, one-way doors, blast radius, failure modes nobody would notice.

- Each risk states a **likelihood** and an **impact** (low/medium/high) and carries either a **mitigation** (how the
  risk is reduced or detected early) or an explicit **acceptance** with rationale. A risk with neither is an open design
  question and belongs in Design Decisions (Open) instead.
- One-way-door decisions — hard or impossible to reverse after shipping, such as schema or data migrations, published
  API contracts, wire formats, or data backfills — must appear as risks unless the design itself removes the
  irreversibility (e.g., a down-migration, versioned contract, or feature flag), in which case the settled decision
  notes that.
- "None identified" is acceptable only with a one-sentence reason (e.g., purely additive tooling with no consumers).
- A risk rated high likelihood and high impact blocks advancing the proposal to `accepted` until it is mitigated or
  explicitly accepted, with the acceptance recorded in the Decision Log.
- Deferring a risk's mitigation follows the same rules as deferring a decision: it needs a concrete revisit hook (see
  "Deferring Decisions").

## Cross-Proposal Impact

When a design decision in one proposal would change later proposals, the first proposal must note this. If proposal A
has a decision that affects proposals B and C, A's text says so, and B and C are updated at the time A is decided,
reviewed, or designed.

The Dependencies section already captures one direction (Y depends on X). The reverse — that X knows Y cares about a
specific part of X — is worth capturing too. Note the impacted proposal *and* the specific section(s) of this proposal
it cares about, not the entirety (unless that's accurate).

This is a recommended practice, not a strict requirement. Prioritize it on:

- Large projects (roughly 100+ proposals) where holding all the cross-references in your head no longer works.
- Projects that draft proposals in waves of 3–4 or more at once, where drift is most likely.

For small projects with one proposal in flight at a time, the maintenance cost usually isn't worth it.

Rot is expected. The list of impacted proposals can grow stale as work progresses. When drift is obvious while editing a
proposal, fix or remove the stale references opportunistically, even if cleanup wasn't why you opened the file. If rot
becomes unmanageable, this approach may be replaced with something else.

## Proposal Index

When creating the first proposal for a project, create an `index.md` in the proposals directory, even if this is the
only proposal that will ever exist. An existing `README.md` index is also accepted. See `tracking.md` "Index File Name".

Contents:

- Optional link to a glossary or other shared references at the top
- A table with columns: Proposal, Description, Status
- One row per proposal, with the proposal ID linking to its file
- An optional dependency graph section for active proposals, topologically ordered with arrows (`←`) pointing to
  dependencies; omit implemented proposals

Example table:

```markdown
| Proposal | Description | Status |
|----------|-------------|--------|
| [PROJ-001](PROJ-001-short-description.md) | Short description | implemented |
| [PROJ-002](PROJ-002-short-description.md) | Short description | accepted |
```

Update the index whenever a proposal is created or its status changes.
