# Coding Agent Standards

This repository contains personal coding standards, best practices, and Claude Code configuration for use across projects.

## Structure

- `languages/` - Language-specific coding standards
- `practices/` - Cross-cutting practices (testing, error handling, security)
- `project-management/` - Plans, proposals, design, and tracking standards
- `claude/` - Claude Code skills, hooks, and rules
- `profiles/` - Composable project profiles that import from the above

## Usage

Symlink this repo to a consistent path on each machine:

```sh
ln -s /actual/path/to/coding_agent_standards ~/coding-standards
```

Then import a profile from a project's `CLAUDE.md` or `CLAUDE.local.md`:

```markdown
@~/coding-standards/profiles/go-service.md
```

For projects you don't own, use `CLAUDE.local.md` (auto-gitignored):

```markdown
@~/coding-standards/profiles/oss-contrib.md
```
