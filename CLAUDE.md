# Coding Agent Standards

This repository contains personal coding standards, best practices, and Claude Code configuration for use across
projects.

## Structure

- `languages/` - Language-specific coding standards
- `practices/` - Cross-cutting practices (testing, error handling, security)
- `.claude/` - Project-local Claude Code config for this repo (skills, settings)
- `claude/` - Claude Code skills, commands, hooks, rules, and project management standards exported for use by other
  projects (via `--add-dir` or `@import`), and packaged as the `coding-standards` plugin
- `claude/commands/` - Slash commands. Keep them thin: a command reads its rules from `${CLAUDE_PLUGIN_ROOT}/rules/` or
  `${CLAUDE_PLUGIN_ROOT}/project-management/` instead of restating them. Every command carries frontmatter with at least
  a `description`, plus `argument-hint` when it takes arguments
- `claude/project-management/` - Plans, proposals, design, tracking, and commit chunking standards. Lives under
  `claude/` so it ships with the plugin
- `codex/` - Codex skills that have no Claude Code equivalent, packaged as a separate Codex plugin. A skill belongs here
  only when it depends on something Codex has and Claude Code does not
- `mods/` - Claude Code mods (function-hook plugins that can draw UI). Each is its own opt-in plugin listed in
  `.claude-plugin/marketplace.json`, so projects using `coding-standards` do not get them. A mod that serves a
  `claude/` command ships inside `claude/` instead, so everyone who gets the command gets the mod. Its hooks module is
  `claude/hooks/<name>.tsx`, its state contract is `claude/types/index.d.ts`, and its tests are in `claude/tests/`
- `profiles/` - Composable project profiles that import from the above
- `bugs/` - Bugs this repo works around, mostly in Claude Code. Each lists its repro and which workarounds to remove
  once it is fixed

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

The setup checker (`bin/check-setup`) looks for this repo at `~/projects/coding_agent_standards` or
`~/coding-standards`.
