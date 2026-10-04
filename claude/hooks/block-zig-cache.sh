#!/bin/bash
# PreToolUse hook on Bash: deny running a binary out of .zig-cache/ and deleting
# .zig-cache. The build system owns the cache. A binary found there may be stale,
# and deleting the cache only hides whatever problem prompted it. Run the
# installed artifact under ./zig-out/bin/ instead, rebuilt with `zig build`.
#
# This is a heuristic regex match, not a shell parser. It treats a .zig-cache/
# path in command position as an execution, with or without a `timeout` prefix.

INPUT=$(cat)
TOOL=$(echo "$INPUT" | jq -r '.tool_name // empty')
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty')

deny() {
  echo "{\"hookSpecificOutput\":{\"hookEventName\":\"PreToolUse\",\"permissionDecision\":\"deny\",\"permissionDecisionReason\":\"$1\"}}"
  exit 0
}

if [[ "$TOOL" == "Bash" ]]; then
  EXEC='(^|[;&|][[:space:]]*)(timeout[[:space:]]+[^[:space:]]+[[:space:]]+)?[^[:space:];&|]*\.zig-cache/'
  if printf '%s' "$COMMAND" | grep -qE "$EXEC"; then
    deny "Do not run binaries from .zig-cache. Run the artifact under ./zig-out/bin/ instead, rebuilt with zig build. The build system owns the cache."
  fi

  if printf '%s' "$COMMAND" | grep -qE '(^|[;&|[:space:]])rm[[:space:]].*\.zig-cache'; then
    deny "Do not delete .zig-cache. The build system owns the cache, and deleting it hides the problem that prompted it."
  fi
fi

exit 0
