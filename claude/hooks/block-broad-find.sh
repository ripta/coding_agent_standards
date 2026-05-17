#!/bin/bash
# Block `find` on broad directories (/, the user-root containing $HOME, $HOME,
# and $HOME/projects). Subdirectories below those are fine.

INPUT=$(cat)
TOOL=$(echo "$INPUT" | jq -r '.tool_name // empty')
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty')

deny() {
  echo "{\"hookSpecificOutput\":{\"hookEventName\":\"PreToolUse\",\"permissionDecision\":\"deny\",\"permissionDecisionReason\":\"$1\"}}"
  exit 0
}

if [[ "$TOOL" == "Bash" ]]; then
  USER_ROOT=$(dirname "$HOME")
  # Escape for use inside a basic POSIX regex character group.
  HOME_RE=$(printf '%s' "$HOME" | sed 's/[\/&]/\\&/g')
  USER_ROOT_RE=$(printf '%s' "$USER_ROOT" | sed 's/[\/&]/\\&/g')
  PATTERN="find[[:space:]]+(/|$USER_ROOT_RE|$HOME_RE|$HOME_RE/projects)/?([[:space:]]|\$)"
  if echo "$COMMAND" | grep -qE "$PATTERN"; then
    deny "Do not run find on broad directories (/, $USER_ROOT, $HOME, $HOME/projects). Use a specific subdirectory instead."
  fi
fi

exit 0
