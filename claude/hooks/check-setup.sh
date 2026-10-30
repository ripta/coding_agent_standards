#!/usr/bin/env bash
# Checks that this machine and this project are set up for the coding standards. Runs on
# SessionStart, and prints nothing when everything is in place.
#
# Output goes to stdout and is visible to Claude as hook context.
#
# Hooks run outside the sandbox, so this can create the state directory even before the
# settings allow it. Creating it means writing ~/.local/state, which the allowance itself never
# covers.
set -euo pipefail

root="${CLAUDE_PLUGIN_ROOT:-}"
WARNINGS=()

# --- Machine: the state directory, and the settings that let sandboxed sessions write it ---
mkdir -p "$HOME/.local/state/coding_agent_standards" 2>/dev/null || true

if [ -n "$root" ] && command -v python3 >/dev/null; then
  status=0
  python3 "$root/scripts/setup_permissions.py" --check >/dev/null 2>&1 || status=$?
  case "$status" in
    0|3) ;;
    1) WARNINGS+=("~/.claude/settings.json lacks entries the standards need, such as the state directories under ~/.local/state, or the guard that lets skills read ~/.config/coding_agent_standards. Ask the user to run 'python3 ~/.claude/coding-standards-current/scripts/setup_permissions.py' from their own terminal.") ;;
    4) WARNINGS+=("The ~/.config guard hook in ~/.claude/settings.json runs a script missing from ~/.claude/coding-standards-current, so the file tools can read all of ~/.config. Ask the user to update the coding-standards plugin and start a new session.") ;;
    *) WARNINGS+=("setup_permissions.py --check could not read ~/.claude/settings.json. Ask the user to run it with --check from their own terminal to see why.") ;;
  esac
fi

# --- Project: only inside a git checkout, and never in the standards repo itself ---
if git rev-parse --is-inside-work-tree &>/dev/null; then
  PROJECT_ROOT="$(git rev-parse --show-toplevel)"
  # In a linked worktree, this is the main checkout. Otherwise it is PROJECT_ROOT.
  MAIN_ROOT="$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")"

  if [ ! -f "$MAIN_ROOT/claude/.claude-plugin/plugin.json" ]; then
    STANDARDS_REFERENCED=false
    for f in "$PROJECT_ROOT/CLAUDE.md" "$PROJECT_ROOT/CLAUDE.local.md" "$PROJECT_ROOT/.claude/CLAUDE.md"; do
      if [ -f "$f" ] && grep -qE "(coding-standards|coding_agent_standards)" "$f" 2>/dev/null; then
        STANDARDS_REFERENCED=true
        break
      fi
    done

    if [ "$STANDARDS_REFERENCED" = false ] && [ "$MAIN_ROOT" != "$PROJECT_ROOT" ] \
      && grep -qsE "(coding-standards|coding_agent_standards)" "$MAIN_ROOT/CLAUDE.local.md"; then
      WARNINGS+=("This worktree has no CLAUDE.local.md, so the coding standards it imports in $MAIN_ROOT do not load. List CLAUDE.local.md in $MAIN_ROOT/.worktreeinclude so new worktrees get a copy, and copy it into this one.")
    elif [ "$STANDARDS_REFERENCED" = false ]; then
      WARNINGS+=("Coding standards not referenced. Add a @~/projects/coding_agent_standards/profiles/<profile>.md import to CLAUDE.md or CLAUDE.local.md in this project.")
    fi

    # Profiles live outside the project, so Claude Code loads them only once the project
    # approves external imports. Without approval it skips them silently.
    if grep -qsE "^@.*(coding-standards|coding_agent_standards)" \
        "$PROJECT_ROOT/CLAUDE.md" "$PROJECT_ROOT/CLAUDE.local.md" "$PROJECT_ROOT/.claude/CLAUDE.md" \
      && command -v jq &>/dev/null && [ -f "$HOME/.claude.json" ]; then
      APPROVED="$(jq -r --arg p "$PROJECT_ROOT" '.projects[$p].hasClaudeMdExternalIncludesApproved // false' "$HOME/.claude.json" 2>/dev/null || echo unknown)"
      if [ "$APPROVED" = false ]; then
        WARNINGS+=("This project imports the coding standards but has not approved external imports, so none of them load. Start an interactive session here and accept the external imports prompt.")
      fi
    fi
  fi
fi

if [ ${#WARNINGS[@]} -gt 0 ]; then
  echo "CODING STANDARDS SETUP:"
  for w in "${WARNINGS[@]}"; do
    echo "  - $w"
  done
fi
