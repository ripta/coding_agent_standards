#!/bin/bash
# PreToolUse hook on Bash: deny `rm` when one invocation has both a recursive and a force flag.
# rm-rf.py does the work. This wrapper keeps the cost of every other Bash call to a shell startup,
# since Python starts far slower. Its reason looks at each operand on disk, and suggests `unlink`
# for a file or symlink and `rmdir` for an empty directory.

INPUT=$(cat)
COMMAND=$(printf '%s' "$INPUT" | jq -r '.tool_input.command // empty')

case "$COMMAND" in
  *rm*) ;;
  *) exit 0 ;;
esac

printf '%s' "$INPUT" | python3 "$(dirname "$0")/rm-rf.py"
