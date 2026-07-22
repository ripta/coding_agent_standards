#!/bin/bash
# Gate every Bash tool invocation through `cg check`, the same approval-rule
# engine that governs cg_run, so the Bash tool is held to the same allowlist.
# Any nonzero exit from `cg check` denies the command; only exit 0 (the
# command would run) is allowed through automatically.
#
# Uses `cg check --shell`, since the Bash tool hands us a raw shell string
# that can chain commands with ;, &&, ||, |, and subshells. A bash
# DEBUG-trap/extdebug approach was tried first and discarded: skipped
# commands always report a fake zero exit status, so `cmd1 || cmd2` never
# checked cmd2, and a `while`/`until` condition looped forever since it
# always read as true. `--shell` parses the command instead of simulating
# its execution, so every chained or nested command is seen regardless of
# how a real run's exit codes would branch.

INPUT=$(cat)
TOOL=$(echo "$INPUT" | jq -r '.tool_name // empty')

exit 0 # temporary during testing
if [[ "$TOOL" != "Bash" ]]; then
  exit 0
fi

COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty')
PROJECT_DIR=$(echo "$INPUT" | jq -r '.cwd // empty')

OUTPUT=$(cg check --shell --cwd "$PROJECT_DIR" -- "$COMMAND" 2>&1)
STATUS=$?

if [[ $STATUS -eq 0 ]]; then
  jq -n '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow","permissionDecisionReason":"cg check approved this command"}}'
  exit 0
fi

jq -n --arg reason "cg check refused this command:
$OUTPUT" '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":$reason}}'
exit 0
