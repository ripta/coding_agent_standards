#!/usr/bin/env bash
# Creates the standards' machine-local state directory, and warns when the user's settings do
# not yet let sandboxed sessions write it. Runs on SessionStart.
#
# Hooks run outside the sandbox, so this can create the directory even before the settings
# allow it. Creating it means writing ~/.local/state, which the allowance itself never covers.
set -euo pipefail

root="${CLAUDE_PLUGIN_ROOT:-}"
mkdir -p "$HOME/.local/state/coding_agent_standards" 2>/dev/null || true

if [ -z "$root" ] || ! command -v python3 >/dev/null; then
  exit 0
fi

if ! python3 "$root/scripts/setup_permissions.py" --check >/dev/null 2>&1; then
  echo "coding-standards: ~/.claude/settings.json lacks entries the standards need, so sandboxed sessions cannot write ~/.local/state/coding_agent_standards. Ask the user to run 'python3 ~/.claude/coding-standards-current/scripts/setup_permissions.py' from their own terminal."
fi
