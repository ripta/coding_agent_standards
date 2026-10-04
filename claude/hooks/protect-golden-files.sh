#!/bin/bash
# PreToolUse hook on Edit|Write|Bash: deny hand-written golden files. A golden
# file records what the code under test actually produced. Edited by hand, it
# records what someone expected instead, and the test stops checking anything.
# Regenerate goldens with the project's update target, such as
# `make update-golden`.
#
# The Bash check is a heuristic regex, not a shell parser. It catches writes
# through redirection, tee, cp, mv, and heredocs that name a .golden file.

INPUT=$(cat)
TOOL=$(echo "$INPUT" | jq -r '.tool_name // empty')
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty')

deny() {
  echo "{\"hookSpecificOutput\":{\"hookEventName\":\"PreToolUse\",\"permissionDecision\":\"deny\",\"permissionDecisionReason\":\"$1\"}}"
  exit 0
}

if [[ "$TOOL" == "Write" || "$TOOL" == "Edit" ]]; then
  if [[ "$FILE_PATH" == *.golden ]]; then
    deny "Golden files must be regenerated with the project's update target, such as make update-golden, not written or edited by hand."
  fi
fi

if [[ "$TOOL" == "Bash" ]]; then
  if printf '%s' "$COMMAND" | grep -qE '(>|tee|cp|mv|cat[[:space:]]*<<).*\.golden'; then
    deny "Golden files must be regenerated with the project's update target, such as make update-golden, not created through shell commands."
  fi
fi

exit 0
