# Tracking

## Cross-Reference Conventions

Documents reference each other using these patterns:

- Proposals list dependencies under `## Dependencies` as a bullet list: `- PROJ-001`
- Proposals list ADRs and other references under `## References` as a bullet list: `- ADR-01: decision explanation`
- Phases reference proposals inline: `Implements: PROJ-003`
- ADRs list the originating proposal under `## References`: `- PROJ-001 (originating proposal, if any)`

## Referring to Milestones

Phases and proposals number their milestones separately. Write each in its own
form and never mix them.

- A phase milestone is `phase 7.1`. Bare `phase 7` means the whole phase.
- A proposal milestone is `PROJ-004 milestone 5`, or `PROJ-004 M5` for short.

A proposal milestone is a plain ordinal. It never repeats the proposal number as
a prefix. `PROJ-004 milestone 4.5` is wrong, and so is `Phase 7 milestone 7.1`.

Both wrong forms restate a number the reader already has. They also make the two
namespaces look alike, which then needs a warning somewhere to tell them apart.
The forms above cannot be read as each other, so no warning is needed.

## Dependency Direction

Dependencies are expressed between proposals. A proposal never depends on a
phase or a phase milestone.

Phases are derived from proposal dependencies. A proposal that names a phase as
a dependency inverts that, and makes the schedule load-bearing for the design.
Phase numbers can be renumbered, split, and reordered; proposal numbers are
permanent. A dependency anchored to a phase breaks when the plan changes.

- In a proposal's `## Dependencies`, `## Impacts`, Design Decisions, and
  Milestones, reference only `PROJ-NNN` and `PROJ-NNN milestone N`
- A proposal's Decision Log may name a phase, because recording that a promotion
  happened is history rather than dependency
- When a dependency has a scheduling consequence worth writing down, record the
  consequence in the phase index, not in the proposal

## Metadata

Each artifact type uses inline markdown metadata (not YAML frontmatter), but the fields differ by type:

- Proposals: `**Status:**`, `**Created:**`, `**Updated:**`
- ADRs: `**Status:**`, `**Date:**`
- Phases: `**Goal:**`, `**Status:**`, `**Complexity:**`, `**Dependencies:**` (no document-level dates; rely on git history)

## Numbering Padding

Padding width differs by artifact type. This is deliberate, not an oversight:

- ADRs: 2-digit (`ADR-01`) — architectural decisions are comparatively rare per project.
- Proposals: 3-digit (`PROJ-001`) — proposal volume is typically higher over a project's lifetime.
- Phases: unpadded (`Phase 12`) — phases are referenced in prose and status tables, not sorted as filenames the same way IDs are.

Keep each artifact type's padding fixed once established; do not repad existing files.

## Specs Directory

Spec and design documents may live in a centralized specs directory, symlinked into each project's `spec/` or `docs/` directory. This keeps individual repos uncluttered while maintaining a single source of truth. If neither `spec/` nor `docs/` are symlinks, then it means the documents live in the project repository and are committed directly there.

Proposals and phases each live in their own subdirectory under this specs directory: `spec/proposals/` and `spec/phases/` (or the `docs/` equivalent). This is why proposals.md, plans.md, and the proposal-related skills look for `spec/proposals/` and `docs/proposals/` as common locations — they're checking for this directory. ADRs are usually named `spec/adrs/`, although legacy projects have no fixed subdirectory name; place them alongside any existing ADRs, or ask where they should live if none exist yet.

## Markdown Quality

- Use a markdown linter (e.g., rumdl) with a shared config
- ATX-style headings (`#`)
- Dash-style unordered lists (`-`)
- Line length: 120 characters (excluding code blocks)
- GitHub Flavored Markdown
