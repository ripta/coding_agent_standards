#!/bin/bash
# UserPromptSubmit hook: name the session `<domain name>_guardian` when the prompt invokes
# /guardian with a domain name as its first argument. Invoking the command is the intent to
# rename, so this replaces any custom title the session already has.
#
# The hook sees the line as typed, before the command expands. A first argument that looks like
# a path is a checkout, not a domain name, so the session is left alone. The guardian then asks
# for the domain and tells the user the /rename line to type.

INPUT=$(cat)
PROMPT=$(echo "$INPUT" | jq -r '.prompt // empty')
CURRENT=$(echo "$INPUT" | jq -r '.session_title // empty')

INVOKE='^[[:space:]]*/(coding-standards:)?guardian([[:space:]]+([A-Za-z0-9][A-Za-z0-9._-]*))?([[:space:]]|$)'
if [[ ! "$PROMPT" =~ $INVOKE ]]; then
  exit 0
fi

NAME="${BASH_REMATCH[3]}"
if [[ -z "$NAME" ]]; then
  exit 0
fi

TITLE="${NAME}_guardian"
if [[ "$CURRENT" == "$TITLE" ]]; then
  exit 0
fi

jq -cn --arg title "$TITLE" '{hookSpecificOutput: {hookEventName: "UserPromptSubmit", sessionTitle: $title}}'
exit 0
