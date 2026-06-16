#!/usr/bin/env bash
#
# release-info.sh — emit structured data for cutting a git tag release.
#
# Auto-detects the project's tagging scheme from the latest tag:
#   - month  : vYYYY.M.N  where N is the Nth tag created in that month
#              (e.g. v2026.6.5 is the 5th release of June 2026, NOT a date)
#   - semver : vX.Y.Z      (bump recommendation is left to the caller)
#
# Output is line-oriented with @@SECTION markers; the consuming skill parses it.
# This script never creates or pushes tags — it only reports.

set -euo pipefail

emit() { printf '%s\n' "$1"; }

if [ -n "$(git status --porcelain)" ]; then
  echo "error: working tree is dirty; commit or stash changes first" >&2
  exit 1
fi

today=$(date +%Y-%m-%d)
year=$(date +%Y)
month=$((10#$(date +%m)))

latest_tag=$(git describe --tags --abbrev=0 2>/dev/null) || latest_tag=""

# --- No tags yet: caller decides scheme and first tag ------------------------
if [ -z "$latest_tag" ]; then
  emit "@@NO_TAGS"
  emit "true"
  emit "@@TODAY"
  emit "$today"
  emit "@@YEAR"
  emit "$year"
  emit "@@MONTH"
  emit "$month"
  emit "@@COMMIT_COUNT"
  emit "$(git rev-list HEAD --count)"
  emit "@@GIT_LOG"
  emit "$(git log HEAD --format='%s%n%b---')"
  emit "@@END"
  exit 0
fi

commit_count=$(git rev-list "${latest_tag}..HEAD" --count)
if [ "$commit_count" -eq 0 ]; then
  echo "error: no commits since ${latest_tag}; nothing to release" >&2
  exit 1
fi
git_log=$(git log "${latest_tag}..HEAD" --format='%s%n%b---')

# Preserve a leading "v" prefix if the project uses one.
prefix=""
core="$latest_tag"
if [ "${latest_tag:0:1}" = "v" ]; then
  prefix="v"
  core="${latest_tag#v}"
fi

# Scheme heuristic: a first component that looks like a calendar year (>=2000)
# means the month-based scheme; anything else is treated as semver.
first="${core%%.*}"
scheme="semver"
if [[ "$first" =~ ^[0-9]+$ ]] && [ "$first" -ge 2000 ]; then
  scheme="month"
fi

# --- Month-based scheme ------------------------------------------------------
if [ "$scheme" = "month" ]; then
  highest_serial=0
  ref_tag=""
  while IFS= read -r tag; do
    [ -z "$tag" ] && continue
    IFS='.' read -r ty tm ts <<< "${tag#"$prefix"}"
    [[ "$ty" =~ ^[0-9]+$ && "$tm" =~ ^[0-9]+$ && "$ts" =~ ^[0-9]+$ ]] || continue
    if [ "$((10#$ty))" -eq "$year" ] && [ "$((10#$tm))" -eq "$month" ]; then
      s=$((10#$ts))
      if [ "$s" -ge "$highest_serial" ]; then
        highest_serial=$s
        ref_tag="$tag"
      fi
    fi
  done < <(git tag -l "${prefix}${year}.*")

  # Detect zero-padding from a representative tag (this month's, else the latest
  # tag overall). A segment is "padded" when a single-digit value is written
  # with a leading zero. Default to no padding when ambiguous, since some
  # tooling rejects zero-padded segments.
  padded="false"
  detect_from="${ref_tag:-$latest_tag}"
  IFS='.' read -r _dy dm ds <<< "${detect_from#"$prefix"}"
  if { [ "${#dm}" -eq 2 ] && [ "$((10#$dm))" -lt 10 ]; } \
     || { [ -n "${ds:-}" ] && [ "${#ds}" -eq 2 ] && [ "$((10#$ds))" -lt 10 ]; }; then
    padded="true"
  fi

  next_serial=$((highest_serial + 1))
  if [ "$padded" = "true" ]; then
    next_tag=$(printf "%s%s.%02d.%02d" "$prefix" "$year" "$month" "$next_serial")
  else
    next_tag=$(printf "%s%s.%d.%d" "$prefix" "$year" "$month" "$next_serial")
  fi

  emit "@@SCHEME"
  emit "month"
  emit "@@LATEST_TAG"
  emit "$latest_tag"
  emit "@@PADDED"
  emit "$padded"
  emit "@@NEXT_TAG"
  emit "$next_tag"
  emit "@@TODAY"
  emit "$today"
  emit "@@COMMIT_COUNT"
  emit "$commit_count"
  emit "@@GIT_LOG"
  emit "$git_log"
  emit "@@END"
  exit 0
fi

# --- Semver scheme -----------------------------------------------------------
IFS='.' read -r maj min pat <<< "$core"
pat="${pat%%-*}"   # drop prerelease suffix, e.g. 1.2.3-rc1
pat="${pat%%+*}"   # drop build metadata, e.g. 1.2.3+build
maj=$((10#${maj:-0}))
min=$((10#${min:-0}))
pat=$((10#${pat:-0}))

emit "@@SCHEME"
emit "semver"
emit "@@LATEST_TAG"
emit "$latest_tag"
emit "@@NEXT_MAJOR"
emit "${prefix}$((maj + 1)).0.0"
emit "@@NEXT_MINOR"
emit "${prefix}${maj}.$((min + 1)).0"
emit "@@NEXT_PATCH"
emit "${prefix}${maj}.${min}.$((pat + 1))"
emit "@@TODAY"
emit "$today"
emit "@@COMMIT_COUNT"
emit "$commit_count"
emit "@@GIT_LOG"
emit "$git_log"
emit "@@END"
