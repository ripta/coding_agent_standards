# Tracking

## Cross-Reference Conventions

Documents reference each other using these patterns:

- Proposals reference dependencies: `Depends on: PROJ-001, PROJ-002`
- Proposals reference ADRs: `Follows: ADR-01`
- Phases reference proposals: `Implements: PROJ-003`
- ADRs reference proposals: `Origin: PROJ-001`

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
