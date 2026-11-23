# `find_base_remote` takes a lone fork remote as the base repo

**Status:** fixed 2026-11-23

**Validation:** reproduced before the fix. `scope` in a checkout whose only remote is a fork, with gh naming that fork,
reported the fork's key as the base repo.

**Fixed:** 2026-11-23. A fork's PR target, saved in `~/.config/coding_agent_standards/pr-targets.json`, now
settles the base. `find_base_remote` asks gh whether a lone remote is a fork. With no saved target and no
`gh repo set-default`, it stops with what to choose, and tracker-sync asks. A lone fork saved as `parent` stops with
the `git remote add upstream` command. `test_lone_fork_remote_without_a_target_stops_and_names_both_repos` in
`claude/skills/tracker-sync/test_sync_scope.py` covers it. The sections below describe the bug as it was.

## Observed

In a checkout whose only remote is a fork, tracker-sync treats the fork as the base repo. It keys its mappings by the
fork's URL. It reads merged work from the fork's mainline, which can lag the parent's.

`pr_watch.py preflight` had the same gap. The commit "Hold preflight's remotes when gh falls back to a lone fork
remote" fixed preflight only.

## Cause

`find_base_remote` in `claude/scripts/base_remote.py` returns the only remote when the checkout has one. It never asks
gh, so it never learns that the remote is a fork. `base_remote` in `claude/skills/tracker-sync/sync_scope.py` calls it.

## Repro

1. Clone a fork, so `origin` is the only remote. Do not run `gh repo set-default`.
2. Call `find_base_remote` on the checkout.

Expected: an answer that says the base repo is the parent, which no remote holds. Actual: `origin`.

## Fix

Design call. Options:

- Look up whether the lone remote is a fork, and fail with the `git remote add upstream` command when it is, unless
  `gh repo set-default` chose the fork. This matches preflight. It costs a gh call in the one-remote case.
- Keep the lone-remote answer, and have tracker-sync warn when its mapping's URL is a fork.
