#!/usr/bin/env bash
# Points ~/.claude/coding-standards-current at this plugin's install directory.
# Profiles import the standards through that link, so a project's instructions
# come from the same commit as the plugin's tools. Runs on SessionStart.
#
# The link is replaced by rename, so the link itself never goes missing. A read
# that follows it during a repoint can still fail rarely on macOS, about 1 in
# 2000 reads. ln -sfn fails about 100 times as often.
set -euo pipefail

root="${CLAUDE_PLUGIN_ROOT:-}"
link="$HOME/.claude/coding-standards-current"

# Link only an installed snapshot. A --plugin-dir session points the root at a
# working tree, and linking it would leak uncommitted edits into every project.
case "$root" in
  "$HOME"/.claude/plugins/cache/*) ;;
  *) exit 0 ;;
esac

if [ ! -d "$root" ]; then
  exit 0
fi

if [ -L "$link" ] && [ "$(readlink "$link")" = "$root" ]; then
  exit 0
fi

if [ -e "$link" ] && [ ! -L "$link" ]; then
  echo "coding-standards: $link exists and is not a symlink. Remove it so profiles can import the standards."
  exit 0
fi

tmp="$link.tmp.$$"
ln -s "$root" "$tmp"
# rename(2) replaces the old link in one step. mv would follow a link to a
# directory and move the new link inside it.
if ! perl -e 'rename $ARGV[0], $ARGV[1] or die "$!\n"' "$tmp" "$link"; then
  rm -f "$tmp"
  echo "coding-standards: could not update $link. Profiles may import a stale snapshot of the standards."
fi
