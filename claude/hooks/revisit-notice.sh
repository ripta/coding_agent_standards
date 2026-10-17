#!/usr/bin/env bash
# Prints one line at session start when a revisit hook in the project's proposals has passed. A
# deferral is only useful if someone notices its hook fire, and nobody runs a listing on a hunch.
#
# It prints nothing when no hook has passed, when the project has no proposals directory, or
# when anything fails. A broken notice must never get in the way of a session.

root="${CLAUDE_PROJECT_DIR:-$PWD}"
script="${CLAUDE_PLUGIN_ROOT:-}/scripts/proposals.py"
[ -f "$script" ] || exit 0
command -v python3 >/dev/null || exit 0

for dir in "$root/spec/proposals" "$root/docs/proposals"; do
  if [ -d "$dir" ]; then
    python3 "$script" notice --proposals-dir "$dir" 2>/dev/null
    break
  fi
done
exit 0
