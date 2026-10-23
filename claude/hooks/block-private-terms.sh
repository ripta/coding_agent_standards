#!/bin/bash
# PreToolUse hook on Bash: deny a git commit that carries a private term into a public repo or
# one whose visibility is unknown. private-terms.py does the work. This wrapper keeps the cost
# of every other Bash call to a shell startup, since Python starts far slower.

TERMS="$HOME/.config/coding_agent_standards/private-terms.txt"
if [ ! -s "$TERMS" ]; then
  exit 0
fi

INPUT=$(cat)
case "$INPUT" in
  *git*commit*) ;;
  *) exit 0 ;;
esac

printf '%s' "$INPUT" | python3 "$(dirname "$0")/private-terms.py" pretooluse
