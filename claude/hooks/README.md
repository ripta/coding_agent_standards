# Hooks

`hooks.json` is loaded by the `coding-standards` plugin. It wires three events:

- `PreToolUse` on `Bash` runs `block-broad-find.sh`.
- `PostToolUse` on `Edit|Write` runs `make fmt` when the target exists.
- `Stop` reminds you to run `make test` and `make lint` when those targets exist.

`block-redirection.sh` and `cg-check.sh` ship here too. They are not wired into
`hooks.json`. Reference them from a project's own settings when you want them.

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
