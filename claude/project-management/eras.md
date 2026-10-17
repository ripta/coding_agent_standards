# Eras

An era is a numbered style of project management. Each era is a set of
conventions for where design, execution state, and implementation order live.
The eras below follow the history of the standards in this directory.

Use eras to describe an existing project or artifact, and to name what a change
to the standards would replace.

## Writing About Eras

Write `era 1` in lowercase, like the common noun "phase". It is not an
identifier like `Phase 7`. The number is enough to index on.

The first time a document mentions an era, add a short gloss that names what
that era introduced. Later mentions in the same document use the bare number.
The gloss must tell its era apart from the others, so it names the era's
defining change. It does not name a rule that later eras kept.

| Era | First-mention gloss | Standards adopted it |
|-----|---------------------|----------------------|
| 0 | era 0, where phases were sections of one rolling plan | before 2026-02-07 |
| 1 | era 1, which introduced proposals and one file per phase | 2026-02-07 |
| 2 | era 2, which split phase and proposal milestones into separate namespaces | 2026-08-08 |

For example, "era 1, which introduced proposals and one file per phase" is a
good first mention. "era 1, where one proposal existed per phase" is not. Era 2
kept that rule, so the phrase does not tell the two apart.

## Classifying an Artifact

An artifact belongs to the era whose markers it carries. The date it was
written does not decide its era. Projects adopt a new era late, and some never
adopt it. A phase document written after 2026-08-08 that still carries the era
1 markers is an era 1 document.

A project can hold artifacts from several eras. A layout can also carry forward
while its contents adopt later rules. When the layout and the rules differ,
name both, as in "an era 0 plan with era 2 milestone tables".

A rule added in the middle of an era does not start a new era. An era changes
when the model changes: where design lives, where status lives, or how
milestones are numbered. A future change of that size takes the next number.

## Era 0: The Rolling Plan

Era 0 predates these standards. Implementation is planned in one file that
holds every pending phase as a section. Finished phases move out of the plan
into an archive file of detailed notes. Some projects also keep a separate
index of every phase with its status and progress, or a summary of finished
work grouped by topic. Others keep the whole plan in the index itself.

The phase is the primary design record. Proposals are absent, or they are
optional documents that a phase title cites in parentheses. Work inserted
between existing phases takes a fractional number such as `4.5`, or a run such
as `5.1` through `5.16`, rather than renumbering what follows.

Some era 0 projects keep one file per phase but still have no proposals. Their
phase documents hold the whole design: schema, code and test listings,
benchmarks, and a completion summary of what shipped.

Markers:

- Pending phases as `## Phase N: Title` sections in a single plan file
- An archive file that finished phases move into
- Fractional phase numbers for inserted work
- No proposal, or a proposal cited only in the phase title
- A milestone table with a Status column and no Proposal column
- Dependencies written as prose, such as a `**Depends on:**` line with the
  reason

## Era 1: Proposals and Phase Files

Era 1 introduced the proposal as a separate design artifact with its own
lifecycle. It also introduced one file per phase. Each phase implements exactly
one proposal, or a portion of one. A proposal reaches a phase only by
promotion. A phase index holds one row per phase.

These rules arrived during era 1 without changing the model:

- 2026-03-21: check a proposal's status before implementing it
- 2026-04-23: optional proposal and phase indexes
- 2026-05-05: every deferred decision names a concrete revisit hook
- 2026-05-31: the `superseded` and `retracted` proposal statuses
- 2026-06-06: the Impacts section for cross-proposal effects
- 2026-06-07: refactoring is part of a phase's scope
- 2026-07-03: design spikes are not milestones
- 2026-07-18: indexes are created by default
- 2026-07-19: a Milestones section in the phase template

Markers:

- `**Status**:` with the colon outside the bold
- A milestone table under `## Implementation` or `## Milestones` with no
  Proposal column
- One acceptance criteria list for the whole phase
- A Scope line such as `Implements: PROJ-NNN (milestones 1-3)` as the only map
  from phase to proposal milestones
- A proposal milestone table that carries its own status

Known weak points:

- Phase documents restate the proposal. Their problem statement, decisions, and
  milestone rows are often copied.
- Status lives in two places. A proposal's milestone rows drift from its phase.
- A phase renumbers proposal milestones with nothing that records the mapping.
- Acceptance checkboxes are often left unticked under a `COMPLETE` status.
- A divergence found during implementation is recorded in the phase, the
  proposal, both, or neither.

## Era 2: Separate Milestone Namespaces

Era 2 split phase milestones and proposal milestones into separate namespaces.
A phase milestone is `Phase 7.1`. A proposal milestone is `PROJ-004 M5`.
Execution status has a single owner, the phase milestone row. A proposal
milestone carries no status of its own. A Proposal column on each phase
milestone row names the proposal milestone it implements.

Era 2 also attached acceptance criteria to each milestone, put the metadata
colon inside the bold, and added the glossary. Later in the era, the phase
template dropped its file-list section (2026-10-04), and indexes could be named
`README.md` (2026-10-04). Every ADR candidate gained a Decision Log entry with
its outcome (2026-10-17).

Markers:

- `**Status:**` with the colon inside the bold
- A `| Milestone | Proposal | Description | Status |` table with rows such as `| 7.1 | PROJ-004 M1 | ... |`
- `### Phase N.1` headings that group acceptance criteria by milestone
- A Tracking Artifacts section listing the files to update as the phase progresses
- A Design Decisions section that points to the proposal instead of restating it

Known weak points:

- The problem statement is still restated from the proposal's motivation.
- Acceptance criteria are often half the phase document, and mostly derive from
  the milestone text.
- The Tracking Artifacts list exists because one change touches four or five
  files.
- A divergence found during implementation lands in the proposal's Decision
  Log. The proposal's decision and milestone text above it stays stale.
- No artifact has a designated place for why a proposal was split across
  phases, or why other work came between them.
- Dependencies live in each phase's header. The phase index records none of
  them.
