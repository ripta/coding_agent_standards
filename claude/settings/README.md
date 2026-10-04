# Settings Templates

These are reference templates for `.claude/settings.local.json` permission whitelists.

Copy the relevant template into your project and adjust as needed:

```sh
cp ~/coding-standards/claude/settings/go-dev.json myproject/.claude/settings.local.json
```

Or merge multiple templates for fullstack projects (e.g., Go + Svelte).

These are starting points -- add project-specific tools (e.g., `Bash(bin/sqlc *)`) as needed.

A template may also wire hooks from `claude/hooks/` that fit its ecosystem. `zig-dev.json` wires
`block-zig-cache.sh`. Hook commands use the absolute path `$HOME/projects/coding_agent_standards`. Adjust it if the repo
lives elsewhere.
