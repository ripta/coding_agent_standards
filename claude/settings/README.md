# Settings Templates

These are reference templates for `.claude/settings.local.json` permission whitelists.

Copy the relevant template into your project and adjust as needed:

```sh
cp ~/.claude/coding-standards-current/settings/go-dev.json myproject/.claude/settings.local.json
```

Or merge multiple templates for fullstack projects (e.g., Go + Svelte).

These are starting points -- add project-specific tools (e.g., `Bash(bin/sqlc *)`) as needed.

A template may also wire hooks from `claude/hooks/` that fit its ecosystem. `zig-dev.json` wires
`block-zig-cache.sh`. Hook commands use the absolute path `$HOME/.claude/coding-standards-current/hooks/`, the plugin
link. A hook then runs the installed commit and not the checkout's working tree.
