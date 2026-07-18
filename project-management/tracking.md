# Tracking

## Cross-Reference Conventions

Documents reference each other using these patterns:

- Proposals list dependencies under `## Dependencies` as a bullet list: `- PROJ-001`
- Proposals list ADRs and other references under `## References` as a bullet list: `- ADR-01: decision explanation`
- Phases reference proposals inline: `Implements: PROJ-003`
- ADRs list the originating proposal under `## References`: `- PROJ-001 (originating proposal, if any)`

## Metadata

All documents use inline markdown metadata (not YAML frontmatter):

```markdown
# Title

**Status:** accepted
**Created:** YYYY-MM-DD
**Updated:** YYYY-MM-DD
```

## Specs Directory

Spec and design documents live in a centralized specs directory, symlinked into each project's `spec/` or `docs/` directory. This keeps individual repos uncluttered while maintaining a single source of truth.

## Markdown Quality

- Use a markdown linter (e.g., rumdl) with a shared config
- ATX-style headings (`#`)
- Dash-style unordered lists (`-`)
- Line length: 120 characters (excluding code blocks)
- GitHub Flavored Markdown
