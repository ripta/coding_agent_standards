# Hooks

`hooks.json` is loaded by the `coding-standards` plugin. It wires three events:

- `PreToolUse` on `Bash` runs `block-broad-find.sh`.
- `PostToolUse` on `Edit|Write` runs `make fmt` when the target exists.
- `Stop` reminds you to run `make test` and `make lint` when those targets exist.

`block-redirection.sh` and `cg-check.sh` ship here too. They are not wired into
`hooks.json`. Reference them from a project's own settings when you want them.

## Opt-In Hooks

These are not wired into `hooks.json` either. Each one suits only some
projects. Wire one from the project's `.claude/settings.json` by absolute path,
since `${CLAUDE_PLUGIN_ROOT}` is not set there. The examples assume the repo
lives at `~/projects/coding_agent_standards`.

- `block-pm-references.sh` denies an Edit or Write to a source file whose new
  text names a proposal, ADR, or bug ID, or a phase or milestone number. It
  enforces the rule in `rules/work-discipline.md`. Markdown, `spec/`, and
  `.claude/` are exempt. Pass the project's proposal prefixes as arguments.
- `audit-pm-refs.sh` is the same check on Stop, over every tracked file. It
  also catches text that arrived through Bash. It greps the whole tree, so clean
  up existing references before wiring it, or every stop fails. Both hooks take
  their pattern from `lib-pm-refs.sh`.
- `protect-golden-files.sh` denies hand-writing a `.golden` file, through Edit,
  Write, or Bash. Goldens must come from the project's update target.
- `block-zig-cache.sh` denies running a binary from `.zig-cache/` and deleting
  the cache. `settings/zig-dev.json` already wires it.

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [
          {
            "type": "command",
            "command": "$HOME/projects/coding_agent_standards/claude/hooks/block-pm-references.sh MOSK"
          }
        ]
      },
      {
        "matcher": "Edit|Write|Bash",
        "hooks": [
          {
            "type": "command",
            "command": "$HOME/projects/coding_agent_standards/claude/hooks/protect-golden-files.sh"
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "$HOME/projects/coding_agent_standards/claude/hooks/audit-pm-refs.sh MOSK"
          }
        ]
      }
    ]
  }
}
```

## Parked Configs Do Not Belong in hooks.json

Claude Code refuses to load a plugin whose `hooks.json` has a matcher-shaped
object anywhere outside the `hooks` object. The loader scans every other
top-level key three levels deep. Any object with a non-empty `hooks` array trips
it. The error names `PreToolUse/PermissionRequest` no matter which key caused it.

A leading underscore does not exempt the key. Neither does a `_note` field. Keep
disabled configs in this file as fenced code, not in `hooks.json`.

## Disabled: make lint on git commit

This ran `make lint` before every `git commit`. It is off because it blocks
commits in projects with no Makefile or no `lint` target.

To re-enable, add this to `hooks.PreToolUse` in `hooks.json`:

```json
{
  "matcher": "Bash(git commit*)",
  "hooks": [
    {
      "type": "command",
      "command": "make lint"
    }
  ]
}
```
