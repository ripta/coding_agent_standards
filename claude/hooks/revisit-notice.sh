#!/usr/bin/env bash
# Prints one line per proposals directory at session start when a revisit hook in it has passed. A
# deferral is only useful if someone notices its hook fire, and nobody runs a listing on a hunch.
#
# A monorepo can keep a proposals directory per app, so this checks every spec/proposals and
# docs/proposals under the project root. Each line names its directory.
#
# It prints nothing when no hook has passed, when the project has no proposals directory, or
# when anything fails. A broken notice must never get in the way of a session.

root="${CLAUDE_PROJECT_DIR:-$PWD}"
script="${CLAUDE_PLUGIN_ROOT:-}/scripts/proposals.py"
[ -f "$script" ] || exit 0
command -v python3 >/dev/null || exit 0

# Prints each path, relative to the root, that ends in a spec or docs entry. Such an entry may be
# a directory or a symlink to a central specs directory. A symlink kept out of the repo is listed
# as an ignored file, so the listing takes ignored entries too. Ignored directories stay collapsed,
# which keeps vendored trees such as node_modules out of the search.
candidates() {
  if git -C "$root" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    {
      git -C "$root" ls-files -z --cached --recurse-submodules
      git -C "$root" ls-files -z --others --exclude-standard
      git -C "$root" ls-files -z --others --ignored --exclude-standard --directory
    } 2>/dev/null | tr '\0' '\n' | awk -F/ '
      {
        path = ""
        for (i = 1; i <= NF; i++) {
          path = (i == 1) ? $i : path "/" $i
          if ($i == "spec" || $i == "docs") print path
        }
      }' | sort -u
  else
    (cd "$root" && find . -maxdepth 5 \( -name .git -o -name node_modules \) -prune -o \
      \( -name spec -o -name docs \) -print) 2>/dev/null | sed 's|^\./||' | sort -u
  fi
}

# Two entries can reach one directory, such as links to the same central specs, and it gets one
# notice. The physical path tells them apart.
seen=$'\n'
while IFS= read -r rel; do
  dir="$root/$rel/proposals"
  [ -d "$dir" ] || continue

  real="$(cd "$dir" 2>/dev/null && pwd -P)" || continue
  case "$seen" in
    *$'\n'"$real"$'\n'*) continue ;;
  esac
  seen="$seen$real"$'\n'

  python3 "$script" notice --proposals-dir "$dir" 2>/dev/null
done < <(candidates)

exit 0
