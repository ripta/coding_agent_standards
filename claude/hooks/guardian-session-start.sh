#!/bin/bash
# SessionStart hook: tell a guardian session that comes back by resume, /clear, or fork to re-run
# its Starting steps before it handles anything. Leaving the session ran its stop hooks, and the
# new context does not hold the protocol. A fork also claims a name its parent holds, so Starting's
# rival check must run.
#
# A guardian is recognized by its custom title, `<domain name>_guardian`. SessionStart carries the
# title, while SessionEnd does not. Startup has nothing to re-run, and compaction keeps the session.

INPUT=$(cat)
SOURCE=$(echo "$INPUT" | jq -r '.source // empty')
TITLE=$(echo "$INPUT" | jq -r '.session_title // empty')

case "$SOURCE" in
  resume | clear | fork) ;;
  *) exit 0 ;;
esac

if [[ ! "$TITLE" =~ ^([A-Za-z0-9][A-Za-z0-9._-]*)_guardian$ ]]; then
  exit 0
fi

NAME="${BASH_REMATCH[1]}"
CONTEXT="This session is ${TITLE}, and it came back by ${SOURCE}. Its guardian Starting steps no longer hold."
CONTEXT+=" Before anything else, act on /coding-standards:guardian ${NAME} as if the user had just typed it."
CONTEXT+=" Re-run every Starting step, including the rival check and the start hooks."
CONTEXT+=" Handle no request until Starting is done."

jq -cn --arg context "$CONTEXT" '{hookSpecificOutput: {hookEventName: "SessionStart", additionalContext: $context}}'
exit 0
