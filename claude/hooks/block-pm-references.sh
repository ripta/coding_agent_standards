#!/bin/bash
# PreToolUse hook on Edit|Write: deny a source-code write whose new text
# carries a project-management reference. rules/work-discipline.md forbids
# them in code and comments. See lib-pm-refs.sh for what counts as one.
#
# Arguments are the project's proposal prefixes, such as `MOSK`. With none,
# the hook still catches ADR-N, PROJ-N, bug-N, and phase or milestone numbers.
#
# Markdown and anything under spec/ or .claude/ is exempt, since that is where
# these references belong. Only the new text is checked: Write's whole body, or
# Edit's replacement. Text already in the file is not this edit's doing.

source "$(dirname "$0")/lib-pm-refs.sh"

INPUT=$(cat)
TOOL=$(echo "$INPUT" | jq -r '.tool_name // empty')

if [[ "$TOOL" != "Write" && "$TOOL" != "Edit" ]]; then
  exit 0
fi

FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')
if [[ -z "$FILE_PATH" ]]; then
  exit 0
fi

case "$FILE_PATH" in
  */spec/*|spec/*|*/.claude/*|.claude/*|*.md) exit 0 ;;
esac

# Data files such as .json and .golden fall through, so fixtures can quote IDs.
case "$FILE_PATH" in
  *.zig|*.c|*.h|*.cc|*.cpp|*.hpp|*.go|*.rs|*.py|*.rb|*.sh) ;;
  *.js|*.mjs|*.jsx|*.ts|*.tsx|*.svelte|*.swift|*.java|*.kt|*.proto|*.sql) ;;
  */Makefile|Makefile|*.mk) ;;
  *) exit 0 ;;
esac

if [[ "$TOOL" == "Write" ]]; then
  NEW_CONTENT=$(echo "$INPUT" | jq -r '.tool_input.content // empty')
else
  NEW_CONTENT=$(echo "$INPUT" | jq -r '.tool_input.new_string // empty')
fi

if [[ -z "$NEW_CONTENT" ]]; then
  exit 0
fi

MATCH=$(printf '%s' "$NEW_CONTENT" | grep -oE "$(pm_refs_pattern "$@")" | head -1)
if [[ -z "$MATCH" ]]; then
  exit 0
fi

MATCH=$(pm_refs_trim "$MATCH")
jq -n --arg match "$MATCH" '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":("Source-code write contains the project-management reference \"" + $match + "\". Proposal, ADR, and bug IDs and phase or milestone numbers do not belong in code or comments. Drop the reference, or state the reason without naming the artifact.")}}'
exit 0
