#!/bin/bash
# Block Bash commands that redirect output (>, >>, 2>&1, &>, ...) or pipe into
# head/tail, and point the agent at cg_run instead. cg_run and cg_run_many capture
# stdout/stderr without 2>&1 and truncates long output on its own, so neither
# pattern is needed from the agent.
#
# This is a heuristic regex match, not a shell parser: quoted strings
# containing ">" or "->" can trigger a false positive. Comparison operators
# (>=, <=) are stripped first to avoid the most common false-positive source.

INPUT=$(cat)
TOOL=$(echo "$INPUT" | jq -r '.tool_name // empty')
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty')

deny() {
  echo "{\"hookSpecificOutput\":{\"hookEventName\":\"PreToolUse\",\"permissionDecision\":\"deny\",\"permissionDecisionReason\":\"$1\"}}"
  exit 0
}

if [[ "$TOOL" == "Bash" ]]; then
  STRIPPED=$(printf '%s' "$COMMAND" | sed -E 's/[<>]=/  /g')

  if printf '%s' "$STRIPPED" | grep -qE '(\|&|&>|[0-9]*>{1,2}&?[0-9]*)'; then
    deny "Shell redirection is disabled by your safety hook. Use the cg_run or cg_run_many MCP tool instead -- it captures stdout/stderr without needing 2>&1, so no redirection is necessary."
  fi

  if printf '%s' "$COMMAND" | grep -qE '\|[[:space:]]*(head|tail)([[:space:]]|$)'; then
    deny "Piping into head/tail is disabled by your safety hook. Use the cg_run or cg_run_many MCP tool instead -- it truncates long output automatically, so you don't need to pipe to head/tail yourself."
  fi
fi

exit 0
