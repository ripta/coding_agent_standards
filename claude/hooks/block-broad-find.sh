#!/bin/bash
# PreToolUse hook on Bash, cg_run, and cg_run_many: block `find` on broad directories (/, the
# user-root containing $HOME, $HOME, and $HOME/projects). Subdirectories below those are fine.
#
# This is a regex over the command text, not a shell parser. A cg call carries an argv list, so its
# words are joined with spaces, which is the text a Bash call would carry. A shell wrapper such as
# ["bash", "-c", "find / -name x"] then reads the same as it does in Bash.

INPUT=$(cat)

COMMAND=$(printf '%s' "$INPUT" | jq -r '
  .tool_input as $in
  | if .tool_name == "Bash" then ($in.command // "")
    elif .tool_name == "mcp__cg__cg_run" then ([$in.command[]? | tostring] | join(" "))
    elif .tool_name == "mcp__cg__cg_run_many" then ([$in.commands[]? | arrays | map(tostring) | join(" ")] | join("\n"))
    else "" end')

case "$COMMAND" in
  *find*) ;;
  *) exit 0 ;;
esac

deny() {
  jq -n --arg reason "$1" \
    '{hookSpecificOutput: {hookEventName: "PreToolUse", permissionDecision: "deny", permissionDecisionReason: $reason}}'
  exit 0
}

USER_ROOT=$(dirname "$HOME")
# Escape for use inside a basic POSIX regex character group.
HOME_RE=$(printf '%s' "$HOME" | sed 's/[\/&]/\\&/g')
USER_ROOT_RE=$(printf '%s' "$USER_ROOT" | sed 's/[\/&]/\\&/g')
PATTERN="find[[:space:]]+(/|$USER_ROOT_RE|$HOME_RE|$HOME_RE/projects)/?([[:space:]]|\$)"
if printf '%s' "$COMMAND" | grep -qE "$PATTERN"; then
  deny "Do not run find on broad directories (/, $USER_ROOT, $HOME, $HOME/projects). Use a specific subdirectory instead."
fi

exit 0
