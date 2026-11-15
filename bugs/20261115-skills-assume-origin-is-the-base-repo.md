# Four skills take the base repo from `origin`, which is the fork in a fork checkout

**Status:** open

**Component:** this repo's plugin. The `cloudbuild`, `risk-assessment`, `walkthrough`, and `tracker-sync` skills.

**Validation:** confirmed by reading each code path against a fork checkout's remotes. No skill was run against one.

## Observed

A fork checkout fetches the repo PRs land in from `upstream`, and pushes to the user's fork on `origin`. These skills
read `origin` as the base repo:

1. `cloudbuild` takes the GitHub owner and repo from `git remote get-url origin`, and the default branch from
   `refs/remotes/origin/HEAD`. In a fork checkout it would author triggers for the fork, which builds nothing.
2. `risk-assessment` assesses a PR as `origin/<baseRefName>...<headRefOid>`. That base is the fork's copy of the
   mainline, which can lag the real one. Its fallback `git fetch origin pull/<N>/head` asks the fork for a PR ref that
   only the base repo has.
3. `walkthrough` finds the default branch from `refs/remotes/origin/HEAD`, and builds permalinks from the `origin` URL.
   Its diffs then start from the fork's copy of the mainline. Its links point at the fork, which may not hold the
   commit.
4. `tracker-sync` keys its mappings by the normalized `origin` URL, and reports `behind_origin` against `origin`. A fork
   clone and an upstream clone of one repo then get separate mappings. The behind check compares against the fork.

## Cause

- `claude/skills/cloudbuild/SKILL.md:92` and `:93`
- `claude/skills/risk-assessment/SKILL.md:96` and `:97`
- `claude/skills/walkthrough/SKILL.md:62` and `:141`
- `claude/skills/tracker-sync/SKILL.md:66` and `:89`, and `claude/skills/tracker-sync/sync_scope.py:94` to `:113`

## Repro

In a checkout with `origin` set to a fork and `upstream` set to the base repo, read each step above. Expected: each
skill names the base repo and its mainline. Actual: each names the fork.

## Fix

`pr_watch.py preflight` already reports the base repo's remote as `remotes.mainline`. "Establishing the Branch Pair" in
`claude/project-management/commit-chunking.md` says how to pick the remote by hand. The first three skills can read the
remote the same way, and need no design call.

`tracker-sync` needs one. Its mapping key must stay stable for clones that already saved mappings. The options:

- Key by the base repo's remote, and migrate keys saved under a fork's URL
- Keep the `origin` key, and add the base repo's URL as an alias that finds the same mappings
