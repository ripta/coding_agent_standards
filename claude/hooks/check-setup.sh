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
  err="$(python3 "$root/scripts/setup_permissions.py" --check 2>&1 >/dev/null)" || status=$?
  case "$status" in
    0|3) ;;
    5) WARNINGS+=("~/.claude/settings.json lacks entries the standards need, such as the state directories under ~/.local/state, or the guard that lets skills read ~/.config/coding_agent_standards. Ask the user to run 'python3 ~/.claude/coding-standards-current/scripts/setup_permissions.py' from their own terminal.") ;;
    4) WARNINGS+=("The ~/.config guard hook in ~/.claude/settings.json runs a script missing from ~/.claude/coding-standards-current, so the file tools can read all of ~/.config. Ask the user to update the coding-standards plugin and start a new session.") ;;
    *) WARNINGS+=("setup_permissions.py --check could not run under $(python3 --version 2>&1), exit $status: ${err##*$'\n'} Ask the user to run it with --check from their own terminal to see why.") ;;
  esac
fi

# --- Project: only inside a git checkout, and never in the standards repo itself ---
NOTICES=()
if git rev-parse --is-inside-work-tree &>/dev/null; then
  # In a linked worktree, this is the main checkout. Otherwise it is the project root.
  # --path-format needs git 2.31, so the common dir is made absolute by hand. It is relative to the cwd.
  MAIN_ROOT="$(dirname "$(CDPATH='' cd "$(git rev-parse --git-common-dir)" && pwd)")"

  if [ ! -f "$MAIN_ROOT/claude/.claude-plugin/plugin.json" ]; then
    # The same test as link-current.sh. An installed snapshot is the one the link is about to
    # point at. Anything else is a --plugin-dir working tree.
    case "$root" in
      "$HOME"/.claude/plugins/cache/*) session=installed ;;
      *) session=plugin-dir ;;
    esac

    # One python3 call does the whole project check, to stay inside the hook's timeout. A failure
    # here must never fail the hook.
    if [ -z "$root" ] || ! command -v python3 >/dev/null; then
      WARNINGS+=("Could not check this project's standards imports, since python3 or CLAUDE_PLUGIN_ROOT is missing.")
    else
      status=0
      out="$(python3 "$root/scripts/standards_imports.py" check --plugin-root "$root" --session "$session" \
        --cwd "$PWD" --home "$HOME" 2>&1)" || status=$?
      if [ "$status" -ne 0 ]; then
        WARNINGS+=("standards_imports.py check could not run under $(python3 --version 2>&1), exit $status: ${out##*$'\n'} Ask the user to run it from their own terminal to see why.")
      else
        while IFS= read -r line; do
          case "$line" in
            "warning: "*) WARNINGS+=("${line#warning: }") ;;
            "notice: "*) NOTICES+=("${line#notice: }") ;;
          esac
        done <<< "$out"
      fi
    fi
  fi
fi

# A notice is not a setup problem, so it stays out of the setup list.
for n in ${NOTICES[@]+"${NOTICES[@]}"}; do
  echo "coding-standards: $n"
done

if [ ${#WARNINGS[@]} -gt 0 ]; then
  echo "CODING STANDARDS SETUP:"
  for w in "${WARNINGS[@]}"; do
    echo "  - $w"
  done
fi
