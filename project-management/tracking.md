# Tracking

## Cross-Reference Conventions

Documents reference each other using these patterns:

- Proposals list dependencies under `## Dependencies` as a bullet list: `- PROJ-001`
- Proposals list ADRs and other references under `## References` as a bullet list: `- ADR-01: decision explanation`
- Phases reference proposals inline: `Implements: PROJ-003`
- ADRs list the originating proposal under `## References`: `- PROJ-001 (originating proposal, if any)`

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

Spec and design documents live in a centralized specs directory, symlinked into each project's `spec/` or `docs/` directory. This keeps individual repos uncluttered while maintaining a single source of truth.

Proposals and phases each live in their own subdirectory under this specs directory: `spec/proposals/` and `spec/phases/` (or the `docs/` equivalent). This is why proposals.md, plans.md, and the proposal-related skills look for `spec/proposals/` and `docs/proposals/` as common locations — they're checking for this directory under either symlink target. ADRs have no fixed subdirectory name; place them alongside any existing ADRs, or ask where they should live if none exist yet.

## Markdown Quality

- Use a markdown linter (e.g., rumdl) with a shared config
- ATX-style headings (`#`)
- Dash-style unordered lists (`-`)
- Line length: 120 characters (excluding code blocks)
- GitHub Flavored Markdown
