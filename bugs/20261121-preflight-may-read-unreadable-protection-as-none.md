# `pr_watch.py preflight` may report a non-admin's unreadable classic protection as no protection

**Status:** open

**Validation:** not confirmed. Found by reading the code during a design review. Confirming it needs an authenticated
`gh` call, as a user without admin rights, against a repo with classic branch protection.

## Observed

Suspected: for a user without admin rights on the base repo, `preflight` may report no classic protection and an empty
`protection_unreadable` list. Callers then treat the base as having no required checks from classic protection.
`merge-fix-loop` and `land-branch` would wait on the wrong set of checks.

## Cause

`claude/scripts/pr_watch.py` lines 879-885 read `repos/{slug}/branches/{base}/protection`. A 404 or `Not Found` error
counts as "no classic protection", and any other error is recorded as unreadable. If GitHub answers a signed-in
non-admin with 404 rather than 403, "not readable" and "not protected" become the same answer.

`dependabot_sweep.base_protection` at `claude/scripts/dependabot_sweep.py` lines 275-279 uses the same 404 test.

## Repro

1. As a user with write but not admin rights, pick a repo whose default branch has classic protection with required
   status checks.
2. Run `gh api repos/<owner>/<repo>/branches/<base>/protection`, and note the status code.
3. Run `python3 claude/scripts/pr_watch.py preflight --repo <owner>/<repo>`.

Expected: `protection` holds the required checks, or `protection_unreadable` names branch protection. Actual, if the
bug holds: step 2 returns 404, and `protection` lacks the classic required checks with nothing marked unreadable.

## Fix

`GET repos/{slug}/branches/{base}` returns `protection.required_status_checks` without admin rights. Reading the
required checks from it would remove the dependence on `/protection` for that field. Design call: whether `preflight`
switches to the branch endpoint for required checks, or keeps `/protection` and also reads the branch endpoint to tell
"none" from "hidden".
