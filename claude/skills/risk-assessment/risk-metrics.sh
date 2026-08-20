#!/usr/bin/env bash
# Deterministic git metrics for the risk-assessment skill.
#
# Usage: risk-metrics.sh [BASE [HEAD]]
#   (no args)   working tree (staged + unstaged + untracked) vs HEAD
#   BASE        working tree vs BASE
#   BASE HEAD   BASE...HEAD (merge-base diff)
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

TEST_PATTERN='_test\.|\.test\.|\.spec\.|(^|/)tests?/|(^|/)testdata/'

numstat() {
  git diff --numstat "$DIFF_SPEC" --
  if [[ "$INCLUDE_UNTRACKED" == 1 ]]; then
    git ls-files --others --exclude-standard | while IFS= read -r f; do
      printf '%s\t0\t%s\n' "$(wc -l <"$f" | tr -d ' ')" "$f"
    done
  fi
}

FILES="$(numstat | cut -f3-)"

echo "## target"
echo "$LABEL"

echo
echo "## files (added, deleted, path; '-' = binary)"
numstat

echo
echo "## summary"
numstat | awk -v test_pat="$TEST_PATTERN" '
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
while IFS= read -r f; do
  [[ -z "$f" ]] && continue
  n="$(git log --since='12 months ago' -i -E --grep='fix|bug|regress' --pretty=%h -- "$f" | wc -l | tr -d ' ')"
  printf '%s\t%s\n' "$n" "$f"
done <<<"$FILES" | sort -rn

echo
echo "## ownership (last commit date, distinct authors in 24 months, path)"
while IFS= read -r f; do
  [[ -z "$f" ]] && continue
  last="$(git log -1 --format=%as -- "$f")"
  [[ -z "$last" ]] && last="never (new file)"
  authors="$(git log --since='24 months ago' --format=%ae -- "$f" | sort -u | wc -l | tr -d ' ')"
  printf '%s\t%s\t%s\n' "$last" "$authors" "$f"
done <<<"$FILES"

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
