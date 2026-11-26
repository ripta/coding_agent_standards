#!/usr/bin/env bash
# Deterministic git metrics for the risk-assessment skill.
#
# Usage: risk-metrics.sh [BASE [HEAD]]
#   (no args)   working tree (staged + unstaged + untracked) vs HEAD
#   BASE        working tree vs BASE
#   BASE HEAD   BASE...HEAD (merge-base diff)
#
# Paths in the output are relative to the repo root, whatever directory the script runs from. A
# changed submodule is replaced by the files that changed inside it, under the submodule's path.
#
# The hotspot and ownership metrics read the history before the change, never the change itself.
# That is HEAD for the working tree, BASE for BASE, and the merge-base of BASE and HEAD for both.
# A renamed file shows its new path, and its history is read under the old path.
# A submodule's history comes from its own repo, at the commit the superproject recorded before.
#
# Output is labeled TSV sections. Read-only: never modifies the repo.
set -euo pipefail

BASE="${1:-}"
HEAD_REF="${2:-}"

if [[ -n "$HEAD_REF" ]]; then
  DIFF_SPEC="$BASE...$HEAD_REF"
  LABEL="$DIFF_SPEC"
  INCLUDE_UNTRACKED=0
elif [[ -n "$BASE" ]]; then
  DIFF_SPEC="$BASE"
  LABEL="$BASE vs working tree"
  INCLUDE_UNTRACKED=1
else
  DIFF_SPEC="HEAD"
  LABEL="HEAD vs working tree"
  INCLUDE_UNTRACKED=1
fi

# The arguments are refs, never paths, so nothing above depends on the directory. Everything below
# does: `git diff` prints root-relative paths, but `git ls-files --others` and a pathspec are
# relative to the current directory.
ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

if [[ -n "$HEAD_REF" ]]; then
  HISTORY_REV="$(git merge-base "$BASE" "$HEAD_REF")"
else
  HISTORY_REV="$(git rev-parse --verify "${BASE:-HEAD}^{commit}")"
fi

TEST_PATTERN='_test\.|\.test\.|\.spec\.|(^|/)tests?/|(^|/)testdata/'
EMPTY_TREE="$(git hash-object -t tree /dev/null)"

# One row per changed file: added, deleted, path from the root, repo, path inside the repo before
# the change, and the commit in that repo whose history counts. The repo is "." for the
# superproject, or the submodule's path from the root. The commit is "-" when there is no history.
ROWS=""

# One row per changed submodule: path, old commit, new commit, status.
SUBMODULES=""

add_row() {
  ROWS+="$1"$'\t'"$2"$'\t'"$3"$'\t'"$4"$'\t'"$5"$'\t'"$6"$'\n'
}

# collect REPO WORKTREE REV SPEC...
#
# Adds the files changed in REPO against SPEC to ROWS. WORKTREE is 1 when SPEC is compared with the
# working tree, which also brings in untracked files. It is 0 when SPEC names two commits. REV is
# the commit whose history counts for REPO.
#
# A changed submodule is expanded by diffing the two commits the superproject records for it. A
# working tree comparison runs from the old commit to whatever the submodule has checked out. When
# the submodule cannot be diffed, its gitlink row stays and SUBMODULES says why.
collect() {
  local repo="$1" worktree="$2" rev="$3"
  shift 3

  local prefix="" expanded="" raw numstat others stage="" from
  local meta sub old_mode new_mode old new state subrev add del path file count line

  [[ "$repo" == . ]] || prefix="$repo/"

  raw="$(git -C "$repo" diff --raw --no-abbrev --no-renames "$@" --)"
  while IFS=$'\t' read -r meta sub; do
    [[ -n "$sub" ]] || continue
    read -r old_mode new_mode old new _ <<<"${meta#:}"
    [[ "$old_mode" == 160000 || "$new_mode" == 160000 ]] || continue

    if [[ "$new_mode" != 160000 ]]; then
      SUBMODULES+="$prefix$sub"$'\t'"${old:0:12}"$'\t'"${new:0:12}"$'\t'"removed"$'\n'
      continue
    fi
    [[ "$old_mode" == 160000 ]] || old="$EMPTY_TREE"

    state=expanded
    if [[ ! -e "$repo/$sub/.git" ]]; then
      state=not-initialized
    else
      if [[ "$worktree" == 1 ]]; then
        new="$(git -C "$repo/$sub" rev-parse HEAD)"
      fi
      if [[ "$old" != "$EMPTY_TREE" ]] \
        && ! git -C "$repo/$sub" cat-file -e "${old}^{commit}" 2>/dev/null; then
        state=missing-objects
      elif ! git -C "$repo/$sub" cat-file -e "${new}^{commit}" 2>/dev/null; then
        state=missing-objects
      fi
    fi

    if [[ "$state" == expanded ]]; then
      expanded+="$sub"$'\n'
      subrev="$old"
      [[ "$old" != "$EMPTY_TREE" ]] || subrev=-
      if [[ "$worktree" == 1 ]]; then
        collect "$prefix$sub" 1 "$subrev" "$old"
      else
        collect "$prefix$sub" 0 "$subrev" "$old" "$new"
      fi
    fi
    SUBMODULES+="$prefix$sub"$'\t'"${old:0:12}"$'\t'"${new:0:12}"$'\t'"$state"$'\n'
  done <<<"$raw"

  # With -z a rename is "added TAB deleted TAB", then the old path, then the new path, each ended by
  # a NUL. The NULs become newlines so the output survives the command substitution. Git quotes
  # nothing under -z, and `a => b` or `{a => b}` never has to be taken apart.
  numstat="$(git -C "$repo" diff --numstat -z "$@" -- | tr '\0' '\n')"
  while IFS= read -r line; do
    case "$stage" in
      old)
        from="$line"
        stage=new
        continue
        ;;
      new)
        add_row "$add" "$del" "$prefix$line" "$repo" "$from" "$rev"
        stage=""
        continue
        ;;
    esac

    IFS=$'\t' read -r add del path <<<"$line"
    [[ -n "$add" ]] || continue
    if [[ -z "$path" ]]; then
      stage=old
      continue
    fi
    case $'\n'"$expanded" in
      *$'\n'"$path"$'\n'*) continue ;;
    esac
    add_row "$add" "$del" "$prefix$path" "$repo" "$path" "$rev"
  done <<<"$numstat"

  if [[ "$worktree" == 1 ]]; then
    others="$(git -C "$repo" ls-files --others --exclude-standard)"
    while IFS= read -r file; do
      [[ -n "$file" ]] || continue
      count="$(wc -l <"$repo/$file" | tr -d ' ')"
      add_row "$count" 0 "$prefix$file" "$repo" "$file" "$rev"
    done <<<"$others"
  fi
}

collect . "$INCLUDE_UNTRACKED" "$HISTORY_REV" "$DIFF_SPEC"

FILES="$(printf '%s' "$ROWS" | cut -f3)"

echo "## target"
echo "$LABEL"

echo
echo "## files (added, deleted, path; '-' = binary)"
printf '%s' "$ROWS" | cut -f1-3

if [[ -n "$SUBMODULES" ]]; then
  echo
  echo "## submodules (path, old commit, new commit, status; only 'expanded' lists the submodule's files)"
  printf '%s' "$SUBMODULES"
fi

echo
echo "## summary"
printf '%s' "$ROWS" | cut -f1-3 | awk -F'\t' -v test_pat="$TEST_PATTERN" '
  {
    files++
    if ($1 != "-") { add += $1; del += $2 }
    path = $3
    if (path ~ test_pat) { test_files++; if ($1 != "-") test_add += $1 }
  }
  END {
    printf "files_changed\t%d\n", files
    printf "insertions\t%d\n", add
    printf "deletions\t%d\n", del
    printf "test_files\t%d\n", test_files
    printf "test_insertion_ratio\t%.2f\n", (add ? test_add / add : 0)
  }'

echo
echo "## hotspots (bugfix commits touching file in last 12 months, path)"
while IFS=$'\t' read -r _ _ path repo old rev; do
  [[ -n "$path" ]] || continue
  n=0
  if [[ "$rev" != - ]]; then
    n="$(git -C "$repo" log "$rev" --since='12 months ago' -i -E --grep='fix|bug|regress' --pretty=%h -- "$old" | wc -l | tr -d ' ')"
  fi
  printf '%s\t%s\n' "$n" "$path"
done <<<"$ROWS" | sort -rn

echo
echo "## ownership (last commit date, distinct authors in 24 months, path)"
while IFS=$'\t' read -r _ _ path repo old rev; do
  [[ -n "$path" ]] || continue
  last=""
  authors=0
  if [[ "$rev" != - ]]; then
    last="$(git -C "$repo" log "$rev" -1 --format=%as -- "$old")"
    authors="$(git -C "$repo" log "$rev" --since='24 months ago' --format=%ae -- "$old" | sort -u | wc -l | tr -d ' ')"
  fi
  [[ -n "$last" ]] || last="never (new file)"
  printf '%s\t%s\t%s\n' "$last" "$authors" "$path"
done <<<"$ROWS"

echo
echo "## risk_markers (marker, path)"
mark() {
  local marker="$1" pattern="$2"
  grep -E "$pattern" <<<"$FILES" | sed "s/^/$marker	/" || true
}
mark migration '(^|/)migrations?(/|$)|\.sql$'
mark schema 'schema'
mark dependency-manifest '(^|/)(go\.(mod|sum)|package(-lock)?\.json|yarn\.lock|pnpm-lock\.yaml|Cargo\.(toml|lock)|requirements[^/]*\.txt|Gemfile(\.lock)?|pyproject\.toml|composer\.(json|lock))$'
mark api-contract '\.proto$|openapi|swagger|(^|/)api/'
mark ci-config '(^|/)\.github/workflows/|cloudbuild\.ya?ml|\.gitlab-ci|(^|/)Jenkinsfile'
mark infra '\.tf$|(^|/)helm/|(^|/)k8s/|Dockerfile'
