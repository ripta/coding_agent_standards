#!/bin/bash
# PostToolUse hook on Edit|Write: format the one file the tool wrote, in the repo that holds it.
#
# It runs `make fmt-select FILES=<path>` there, and only when that repo has the target. It never
# runs `fmt`, which formats the whole tree and would rewrite files nobody edited. The session's
# working directory plays no part, since an edit through a symlink can land in another checkout.
# See "Formatting Edited Files" in practices/makefile.md for the target's contract.
#
# It always exits 0. A failed format is shown to the agent as context, not as a blocking error.

FILE=$(jq -r '.tool_input.file_path // empty')
[[ -n "$FILE" && -f "$FILE" ]] || exit 0

# make splits FILES on whitespace, so such a path cannot be passed through it.
[[ "$FILE" =~ [[:space:]] ]] && exit 0

# pwd -P resolves a symlinked directory, so the path is relative to the repo that holds the file.
DIR=$(cd "$(dirname "$FILE")" 2>/dev/null && pwd -P) || exit 0
ROOT=$(git -C "$DIR" rev-parse --show-toplevel 2>/dev/null) || exit 0

REAL="$DIR/$(basename "$FILE")"
REL="${REAL#"$ROOT"/}"

make -C "$ROOT" -n fmt-select FILES="$REL" >/dev/null 2>&1 || exit 0

if ! OUTPUT=$(make -C "$ROOT" --no-print-directory fmt-select FILES="$REL" 2>&1); then
  CONTEXT="make fmt-select failed for $REL in $ROOT:
$(printf '%s\n' "$OUTPUT" | tail -n 20)"
  jq -cn --arg context "$CONTEXT" '{hookSpecificOutput: {hookEventName: "PostToolUse", additionalContext: $context}}'
fi

exit 0
