# Coding Agent Standards

This repository contains personal coding standards, best practices, and Claude Code configuration for use across projects.

## Structure

- `languages/` - Language-specific coding standards
- `practices/` - Cross-cutting practices (testing, error handling, security)
- `project-management/` - Plans, proposals, design, and tracking standards
- `.claude/` - Project-local Claude Code config for this repo (skills, settings)
- `claude/` - Claude Code skills, hooks, and rules exported for use by other projects (via `--add-dir` or `@import`)
- `profiles/` - Composable project profiles that import from the above

## Usage

Import a profile from a project's `CLAUDE.md` or `CLAUDE.local.md`:

```markdown
@~/projects/coding_agent_standards/profiles/go-service.md
```

For projects you don't own, use `CLAUDE.local.md` (auto-gitignored):

```markdown
@~/projects/coding_agent_standards/profiles/oss-contrib.md
```

If the repo is at a non-standard path, symlink it:

```sh
ln -s /actual/path/to/coding_agent_standards ~/coding-standards
```

The setup checker (`bin/check-setup`) looks for this repo at `~/projects/coding_agent_standards` or `~/coding-standards`.
