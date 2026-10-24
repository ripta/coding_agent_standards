# Tracking

## Cross-Reference Conventions

Documents reference each other using these patterns:

- Proposals list dependencies under `## Dependencies` as a bullet list: `- PROJ-001`
- Proposals list ADRs and other references under `## References` as a bullet list: `- ADR-01: decision explanation`
- Queue rows name milestone ranges: `PROJ-003 M1-M4`
- A reference to another project's proposal keeps that project's prefix: `OTHER-007 M2`. The queue's
  `## Other proposals` section says where that project's proposals live. See `plans.md` "Other Projects' Proposals"
- ADRs list the originating proposal under `## References`: `- PROJ-001 (originating proposal, if any)`

## Referring to Milestones

A milestone belongs to a proposal. Write it `PROJ-004 milestone 5`, or
`PROJ-004 M5` for short. A range is `PROJ-004 M3-M5`.

A milestone is a plain ordinal. It never repeats the proposal number as a
prefix. `PROJ-004 milestone 4.5` is wrong. The wrong form restates a number the
reader already has.

Work has no name besides its milestone ID. A queue row is named by its range.
Prose that needs a common noun for a row says "queue row". The word "phase"
names artifacts from earlier eras only. See `eras.md`.

## Dependency Direction

Design dependencies are expressed between proposals. A proposal never depends on
a queue row.

The queue is derived from proposal dependencies. A proposal that names a queue
row as a dependency inverts that, and makes the schedule load-bearing for the
design. Rows split and reorder. Proposal and milestone IDs are permanent.

- In a proposal's `## Dependencies`, `## Impacts`, Design Decisions, and
  Milestones, reference only `PROJ-NNN`, `PROJ-NNN milestone N`, and the
  `PROJ-NNN MN` short form
- A proposal's Decision Log may name a queue row or a phase from an earlier era,
  because recording what happened is history rather than dependency
- A scheduling dependency goes in the queue row's depends-on cell, and its
  reason in the row's note. See `plans.md` "The Queue File"

## Metadata

Each artifact type uses inline markdown metadata (not YAML frontmatter), but the fields differ by type:

- Proposals: `**Status:**`, `**Created:**`, `**Updated:**`, and `**Revisit:**` when deferred
- Proposal milestones: `**Status:**`, under the milestone's heading, and `**Live after:**` on the line after it when
  the milestone's checks need another deploy unit's deployment
- ADRs: `**Status:**`, `**Date:**`

The colon goes inside the bold, in every artifact type and every field.

## Status Vocabularies

Each artifact type has its own status values. The casing differs by type. This
is deliberate, not drift.

- Proposals: lowercase words — `draft`, `designing`, `accepted`,
  `implemented`, `deferred`, `rejected`, `superseded`, `retracted`
- ADRs: lowercase words — `proposed`, `accepted`, `superseded`, `deprecated`
- Proposal milestones: uppercase — `NOT STARTED`, `IN PROGRESS`, `DONE`,
  `DROPPED`

Each vocabulary is closed. A value outside it is an error, not a synonym. A
check reports it. See `proposals.md` "Milestone Status".

Proposals and ADRs share `accepted` and `superseded`. Name the artifact
alongside those. Earlier eras used other values, such as `scheduled` for
proposals and `PLANNED` and `COMPLETE` for phases. See `eras.md`.

## Numbering Padding

Padding width differs by artifact type. This is deliberate, not an oversight:

- ADRs: 2-digit (`ADR-01`) — architectural decisions are comparatively rare per project.
- Proposals: 3-digit (`PROJ-001`) — proposal volume is typically higher over a project's lifetime.
- Milestones: unpadded (`PROJ-004 M12`) — milestones are referenced in prose and queue rows, not sorted as filenames.

Keep each artifact type's padding fixed once established; do not repad existing files. These widths are defaults for a
new project. A project that started with another width, such as `ADR-0001`, keeps it, and tools match the existing
files.

## Specs Directory

Spec and design documents may live in a centralized specs directory, symlinked into each project's `spec/` or `docs/`
directory. This keeps individual repos uncluttered while maintaining a single source of truth. If neither `spec/` nor
`docs/` are symlinks, then it means the documents live in the project repository and are committed directly there.

Proposals live in their own subdirectory under this specs directory: `spec/proposals/` (or the `docs/` equivalent). It
holds the proposals, the proposal index, `queue.md`, and `history.md`. This is why the proposal-related skills and
commands look for `spec/proposals/` and `docs/proposals/` as common locations — they're checking for this directory. A
`spec/phases/` directory is history from an earlier era. See `eras.md`.

ADRs are usually named `spec/adrs/`, although legacy projects have no fixed subdirectory name; place them alongside any
existing ADRs, or ask where they should live if none exist yet.

### Index File Name

A proposals directory has exactly one index. It is named `index.md` or `README.md`. A new index is
`index.md`. Skills and commands accept either name.

A directory holding both is out of standard. Consolidate it before any tool updates its index. Merge the rows and any
prose into one file, then delete the other. A tool that finds both stops before editing either one and tells the user.

## Markdown Quality

- Use a markdown linter with a shared config. The config is `rumdl/rumdl.toml.template` in the coding standards repo;
  copy it to `.rumdl.toml` at the project root. See `rumdl/README.md` for setup and for why it is copied rather than
  symlinked
- ATX-style headings (`#`)
- Dash-style unordered lists (`-`)
- Line length: 120 characters (excluding code blocks)
- GitHub Flavored Markdown

The 120 here governs markdown prose only. Code and code comments wrap at 100, which `claude/rules/work-discipline.md`
sets and each language's formatter enforces. The two numbers are independent.

Configure the linter rather than trusting its defaults. rumdl's built-in MD013 width is 80, so a project that ships no
`.rumdl.toml` enforces 80 while documenting 120, and the run still looks clean.
