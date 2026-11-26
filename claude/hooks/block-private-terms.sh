#!/bin/bash
# PreToolUse hook on Bash, cg_run, and cg_run_many: deny a git commit that carries a private term
# into a public repo or one whose visibility is unknown. private-terms.py does the work.
#
# The only early exit is a missing term file, so a user with no list pays a shell startup and
# nothing more. With a list, Python starts for every call, at about 35 ms. A glob over the payload
# would cost about 5 ms, but none is safe. The tokenizer joins quoted pieces and drops backslashes,
# so `g''it com\mit` is a commit, and no glob over the raw JSON lets it by. Python reads the
# payload itself, from stdin.

TERMS="$HOME/.config/coding_agent_standards/private-terms.txt"
if [ ! -s "$TERMS" ]; then
  exit 0
fi

exec python3 "$(dirname "$0")/private-terms.py" pretooluse
