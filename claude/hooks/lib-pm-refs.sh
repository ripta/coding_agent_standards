#!/bin/bash
# Shared by block-pm-references.sh and audit-pm-refs.sh, so the hook that
# denies a write and the hook that audits the tree match the same text.
# Source it; do not run it.
#
# pm_refs_pattern prints an ERE that matches a project-management reference:
# an ADR-N, PROJ-N, or bug-N ID, or a phase or milestone number. Each argument
# adds a proposal prefix, so `pm_refs_pattern MOSK` also matches MOSK-N.
# Arguments that are not plain alphanumeric prefixes are ignored, so a typo
# cannot turn into a broken regex.
#
# Phase and milestone numbers match only in decimal form (word, space or
# hyphen, then 4.2) or with at least two digits (12). A comment that numbers
# the steps of an algorithm as "phase 1" or "phase 2b" stays legal.
#
# Every alternative is anchored on a non-word character instead of \b, which
# macOS grep does not support reliably. So "debug-2" does not match as bug-2.
# The match can therefore start with that one character; pm_refs_trim drops it.

pm_refs_pattern() {
  local ids='ADR|PROJ'
  local prefix
  for prefix in "$@"; do
    if [[ "$prefix" =~ ^[A-Za-z][A-Za-z0-9]*$ ]]; then
      ids="$ids|$prefix"
    fi
  done

  local b='(^|[^A-Za-z0-9_])'
  local p="${b}($ids)-[0-9]+"
  p="$p|${b}[Bb]ug-[0-9]+"
  p="$p|${b}[Pp]hase[- ][0-9]+\.[0-9]+|${b}[Pp]hase[- ][0-9]{2,}"
  p="$p|${b}[Mm]ilestone[- ][0-9]+\.[0-9]+|${b}[Mm]ilestone[- ][0-9]{2,}"
  printf '%s' "$p"
}

pm_refs_trim() {
  printf '%s' "$1" | sed -E 's/^[^A-Za-z0-9_]//'
}
