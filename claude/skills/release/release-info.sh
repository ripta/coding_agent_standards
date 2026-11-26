#!/usr/bin/env bash
#
# release-info.sh — emit structured data for cutting a git tag release.
#
# Usage: release-info.sh [--component PATH | --list-components]
#
#   (no option)        Release the whole repo. Only unprefixed tags count: vX.Y.Z, vYYYY.M.N, or the
#                      same without the leading "v". Tags that belong to a component are ignored.
#   --component PATH   Release one component of a monorepo. PATH is relative to the repo root, whatever
#                      directory this runs from. Its tags are PATH/vX.Y.Z or PATH/vYYYY.M.N, the Go
#                      module convention, so the tag prefix is always PATH followed by a slash. The
#                      commit count, the log, and the dirty check cover PATH only.
#   --list-components  Print only the @@COMPONENTS section. It skips the dirty check and every other
#                      check, so it works in any tree.
#
# Auto-detects the project's tagging scheme from the latest tag:
#   - month  : vYYYY.M.N  where N is the Nth tag created in that month
#              (e.g. v2026.6.5 is the 5th release of June 2026, NOT a date)
#   - semver : vX.Y.Z      (bump recommendation is left to the caller)
#
# Output is line-oriented with @@SECTION markers; the consuming skill parses it.
# @@COMPONENT, present only with --component, repeats the path.
# @@COMPONENTS lists the component prefixes among the version tags reachable from HEAD, one per line.
# Tag names in @@LATEST_TAG, @@NEXT_TAG and @@NEXT_* carry the component prefix.
# This script never creates or pushes tags — it only reports.

set -euo pipefail

emit() { printf '%s\n' "$1"; }

die() {
  echo "error: $*" >&2
  exit 1
}

component=""
have_component=0
list_only=0

while [ "$#" -gt 0 ]; do
  case "$1" in
    --component)
      [ "$#" -ge 2 ] || die "--component needs a path"
      component="$2"
      have_component=1
      shift 2
      ;;
    --component=*)
      component="${1#--component=}"
      have_component=1
      shift
      ;;
    --list-components)
      list_only=1
      shift
      ;;
    *)
      die "unknown argument: $1"
      ;;
  esac
done

[ "$list_only" -eq 0 ] || [ "$have_component" -eq 0 ] || die "--list-components takes no other option"

# Every path below is relative to the repo root, so git runs from there.
top=$(git rev-parse --show-toplevel 2>/dev/null) || die "not inside a git work tree"
cd "$top"

# Component prefixes among the reachable version tags: apps/api for apps/api/v1.2.3. Tags that are
# not versions, such as docs/v1/notes, do not name a component.
components=$(git tag --merged HEAD -l '*/v[0-9]*' | sed -nE 's#/v[0-9][^/]*$##p' | LC_ALL=C sort -u)

emit_components() {
  if [ "$have_component" -eq 1 ]; then
    emit "@@COMPONENT"
    emit "$component"
  fi
  emit "@@COMPONENTS"
  if [ -n "$components" ]; then
    emit "$components"
  fi
}

if [ "$list_only" -eq 1 ]; then
  emit_components
  emit "@@END"
  exit 0
fi

tag_prefix=""
if [ "$have_component" -eq 1 ]; then
  while [ "${component%/}" != "$component" ]; do
    component="${component%/}"
  done

  # A tag name cannot hold a space, a glob character, "..", or an empty path segment. That also
  # makes the component safe to use as a --match glob below.
  git check-ref-format "refs/tags/${component}/v0" 2>/dev/null \
    || die "component '$component' is not a path that can prefix a tag name"
  git cat-file -e "HEAD:${component}" 2>/dev/null \
    || die "component '$component' not found in HEAD; give a path relative to the repo root"

  tag_prefix="${component}/"
fi

# Runs git with the component as the trailing pathspec, when there is one.
scoped() {
  if [ -n "$component" ]; then
    git "$@" -- "$component"
  else
    git "$@"
  fi
}

if [ -n "$(scoped status --porcelain)" ]; then
  if [ -n "$component" ]; then
    die "working tree is dirty under $component; commit or stash changes first"
  fi
  die "working tree is dirty; commit or stash changes first"
fi

today=$(date +%Y-%m-%d)
year=$(date +%Y)
month=$((10#$(date +%m)))

# The exclude keeps a nested component's tags out, so apps/api does not take apps/api/sub/v9.0.0.
if [ -n "$tag_prefix" ]; then
  latest_tag=$(git describe --tags --abbrev=0 --match "${tag_prefix}v[0-9]*" \
    --exclude "${tag_prefix}*/*" 2>/dev/null) || latest_tag=""
else
  latest_tag=$(git describe --tags --abbrev=0 --match 'v[0-9]*' --match '[0-9]*' \
    --exclude '*/*' 2>/dev/null) || latest_tag=""
fi

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
  emit "$(scoped rev-list HEAD --count)"
  emit_components
  emit "@@GIT_LOG"
  emit "$(scoped log HEAD --format='%s%n%b---')"
  emit "@@END"
  exit 0
fi

commit_count=$(scoped rev-list "${latest_tag}..HEAD" --count)
if [ "$commit_count" -eq 0 ]; then
  if [ -n "$component" ]; then
    die "no commits under $component since ${latest_tag}; nothing to release"
  fi
  die "no commits since ${latest_tag}; nothing to release"
fi
git_log=$(scoped log "${latest_tag}..HEAD" --format='%s%n%b---')

# Preserve a leading "v" prefix if the project uses one.
prefix=""
core="${latest_tag#"$tag_prefix"}"
if [ "${core:0:1}" = "v" ]; then
  prefix="v"
  core="${core#v}"
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
    IFS='.' read -r ty tm ts <<< "${tag#"${tag_prefix}${prefix}"}"
    [[ "$ty" =~ ^[0-9]+$ && "$tm" =~ ^[0-9]+$ && "$ts" =~ ^[0-9]+$ ]] || continue
    if [ "$((10#$ty))" -eq "$year" ] && [ "$((10#$tm))" -eq "$month" ]; then
      s=$((10#$ts))
      if [ "$s" -ge "$highest_serial" ]; then
        highest_serial=$s
        ref_tag="$tag"
      fi
    fi
  done < <(git tag -l "${tag_prefix}${prefix}${year}.*")

  # Detect zero-padding from a representative tag (this month's, else the latest
  # tag overall). A segment is "padded" when a single-digit value is written
  # with a leading zero. Default to no padding when ambiguous, since some
  # tooling rejects zero-padded segments.
  padded="false"
  detect_from="${ref_tag:-$latest_tag}"
  IFS='.' read -r _dy dm ds <<< "${detect_from#"${tag_prefix}${prefix}"}"
  if { [ "${#dm}" -eq 2 ] && [ "$((10#$dm))" -lt 10 ]; } \
     || { [ -n "${ds:-}" ] && [ "${#ds}" -eq 2 ] && [ "$((10#$ds))" -lt 10 ]; }; then
    padded="true"
  fi

  next_serial=$((highest_serial + 1))
  if [ "$padded" = "true" ]; then
    next_tag=$(printf "%s%s%s.%02d.%02d" "$tag_prefix" "$prefix" "$year" "$month" "$next_serial")
  else
    next_tag=$(printf "%s%s%s.%d.%d" "$tag_prefix" "$prefix" "$year" "$month" "$next_serial")
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
  emit_components
  emit "@@GIT_LOG"
  emit "$git_log"
  emit "@@END"
  exit 0
fi

# --- Semver scheme -----------------------------------------------------------
IFS='.' read -r maj min pat <<< "$core"
pat="${pat%%-*}"   # drop prerelease suffix, e.g. 1.2.3-rc1
pat="${pat%%+*}"   # drop build metadata, e.g. 1.2.3+build
for part in "$maj" "${min:-0}" "${pat:-0}"; do
  [[ "$part" =~ ^[0-9]+$ ]] \
    || die "latest tag ${latest_tag} is not a version; expected ${tag_prefix}[v]MAJOR.MINOR.PATCH"
done
maj=$((10#${maj:-0}))
min=$((10#${min:-0}))
pat=$((10#${pat:-0}))

emit "@@SCHEME"
emit "semver"
emit "@@LATEST_TAG"
emit "$latest_tag"
emit "@@NEXT_MAJOR"
emit "${tag_prefix}${prefix}$((maj + 1)).0.0"
emit "@@NEXT_MINOR"
emit "${tag_prefix}${prefix}${maj}.$((min + 1)).0"
emit "@@NEXT_PATCH"
emit "${tag_prefix}${prefix}${maj}.${min}.$((pat + 1))"
emit "@@TODAY"
emit "$today"
emit "@@COMMIT_COUNT"
emit "$commit_count"
emit_components
emit "@@GIT_LOG"
emit "$git_log"
emit "@@END"
