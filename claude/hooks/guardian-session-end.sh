#!/bin/bash
# SessionEnd hook: run a guardian's stop hooks when its session ends. guardian_hooks.py start
# records the domain name under the session's ID. Every other session has no record, so this
# exits at once for them.
#
# SessionEnd gets a 1.5s budget, and a plugin hook's timeout cannot raise it. The stop hooks run
# detached in a new session instead, with their output in stop.log beside the ledger. A crash or kill may skip
# SessionEnd, so a stop hook can never be the only thing that releases a held resource.

INPUT=$(cat)
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty')
if [[ ! "$SESSION_ID" =~ ^[A-Za-z0-9-]+$ ]]; then
  exit 0
fi

GUARDIANS="$HOME/.local/state/coding_agent_standards/guardians"
RECORD="$GUARDIANS/by-session/$SESSION_ID"
if [[ ! -f "$RECORD" ]]; then
  exit 0
fi

DOMAIN=$(head -n 1 "$RECORD")
rm -f "$RECORD"
if [[ ! "$DOMAIN" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]]; then
  exit 0
fi

SCRIPT="$(cd "$(dirname "$0")/.." && pwd)/scripts/guardian_hooks.py"
python3 "$SCRIPT" stop "$DOMAIN" --detach
exit 0
