#!/bin/bash
# SessionStart hook: tell a guardian session that comes back by resume, /clear, or fork to re-run
# its Starting steps before it handles anything. Leaving the session ran its stop hooks, and the
# new context does not hold the protocol. A fork also claims a name its parent holds, so Starting's
# rival check must run.
#
# A guardian is recognized by its custom title, `<domain name>_guardian`. SessionStart carries the
# title, while SessionEnd does not. Startup has nothing to re-run, and compaction keeps the session.
#
# The domain the start hooks saved goes into the context. A complete one is reused without asking
# the user, since nothing about it changed. An incomplete one names only what is missing.

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
CONTEXT+=" Before anything else, act on /coding-standards:guardian ${NAME}."
CONTEXT+=" Re-run every Starting step, including the rival check and the start hooks."
CONTEXT+=" Handle no request until Starting is done."

SCRIPT="$(cd "$(dirname "$0")/.." && pwd)/scripts/guardian_hooks.py"
REPORT=$(python3 "$SCRIPT" saved "$NAME" 2>/dev/null) || REPORT=""
PROBLEMS=$(echo "$REPORT" | jq -r '(.problems // ["the saved domain could not be read"]) | join("; ")' 2>/dev/null) \
  || PROBLEMS="the saved domain could not be read"

if [ -n "$REPORT" ] && [ -z "$PROBLEMS" ]; then
  DOMAIN=$(echo "$REPORT" | jq -c '.domain')
  CONTEXT+=" Its saved domain is complete: ${DOMAIN}. Reuse it in Starting step 1 without asking the user."
else
  CONTEXT+=" Its saved domain cannot be reused as is: ${PROBLEMS}."
  CONTEXT+=" Take what is missing from the ledger header first, and ask the user only for what neither holds."
fi

jq -cn --arg context "$CONTEXT" '{hookSpecificOutput: {hookEventName: "SessionStart", additionalContext: $context}}'
exit 0
