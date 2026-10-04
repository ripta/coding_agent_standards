#!/bin/bash
# Stop hook: fail the stop when a tracked file carries a project-management
# reference, the after-the-fact check behind block-pm-references.sh. That hook
# sees only Edit and Write. This one also catches text that arrived through
# Bash, such as sed or a generated file. See lib-pm-refs.sh for the pattern.
#
# Arguments are the project's proposal prefixes, as for block-pm-references.sh.
#
# It greps the whole tracked tree, not just this turn's changes, with the same
# exemptions: markdown, spec/, and .claude/. A project must be clean before it
# wires this hook, or every stop fails on references that were already there.
#
# It skips when the tree matches HEAD, so a chat-only turn costs nothing. It
# also stands down when the stop is already a retry from a Stop hook, so a
# reference Claude cannot remove does not loop forever.

source "$(dirname "$0")/lib-pm-refs.sh"

INPUT=$(cat)
if [[ "$(echo "$INPUT" | jq -r '.stop_hook_active // false')" == "true" ]]; then
  exit 0
fi

[[ -n "$CLAUDE_PROJECT_DIR" ]] || exit 0
cd "$CLAUDE_PROJECT_DIR" || exit 0

git diff --quiet HEAD -- 2>/dev/null && exit 0

OUT=$(git grep -nE "$(pm_refs_pattern "$@")" -- ':!spec/' ':!.claude/' ':!*.md' 2>/dev/null)

if [[ -n "$OUT" ]]; then
  printf 'Project-management references found in tracked files:\n%s\nProposal, ADR, and bug IDs and phase or milestone numbers belong in spec/, not in code. Remove each reference, or state the reason without naming the artifact.\n' "$OUT" >&2
  exit 2
fi

exit 0
