# Hook Templates

Reusable hook configurations for Claude Code. Each file contains a single hook definition.

## Usage

Copy the relevant hook into your project's `.claude/settings.local.json` (personal) or `.claude/settings.json` (team-shared) under the `"hooks"` key. Merge multiple hooks by combining their event keys.

## Available Hooks

- **post-edit-format.json** - Auto-runs `make fmt` after Edit/Write operations
- **pre-commit-lint.json** - Runs `make lint` before any `git commit` command
- **stop-remind-test.json** - Prints a test reminder when Claude finishes responding

## Example: Combining Hooks

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [{ "type": "command", "command": "make fmt 2>/dev/null || true" }]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "Bash(git commit*)",
        "hooks": [{ "type": "command", "command": "make lint" }]
      }
    ]
  }
}
```
