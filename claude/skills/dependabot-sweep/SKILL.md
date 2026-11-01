---
name: dependabot-sweep
description: |
  Sweep a GitHub owner's open dependabot PRs across all its repositories.
  Verifies each PR really is dependabot's, sorts them into buckets, and drives
  each one to merged or to a reported dead end. Triggers: "scan my repos for
  PRs awaiting review", "sift through dependabot PRs", "merge the dependabot
  backlog". DO NOT trigger on: one PR you want merged (use merge-fix-loop), one
  CI failure (use debug-ci), or landing a local branch (use land-branch).
argument-hint: "[owner] [budget, e.g. 4h]"
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, AskUserQuestion, Agent, Skill, mcp__cg__cg_run, mcp__cg__cg_wait
---

You clear an owner's dependabot backlog. You verify first, then act. You merge what is safe, fix what needs a small
change, and report what needs a person.

This skill is the coordinator. It reuses `${CLAUDE_SKILL_DIR}/../merge-fix-loop/SKILL.md` to land any fix PR you open.
Read that file now. Its branch ownership, waiting rules, and stopping rules apply here too.

## Scripts

`${CLAUDE_SKILL_DIR}/../../scripts/dependabot_sweep.py` does the deterministic parts and prints JSON:

- `dependabot_sweep.py inventory --owner O --out FILE` lists the owner's open PRs, grouped by author, with each repo's
  fork, archived, last-push, auto-merge, and merge-method tags
- `dependabot_sweep.py provenance --repo O/N --pr N` checks that dependabot opened the PR and wrote every commit
- `dependabot_sweep.py classify --inventory FILE --out FILE` runs the provenance check on every dependabot PR and sorts
  each into a bucket
- `dependabot_sweep.py fork --repo O/N` reports whether a fork has commits of its own, and its dependabot settings
- `dependabot_sweep.py updates --repo O/N` lists dependabot's update jobs
- `dependabot_sweep.py last-comment --repo O/N --pr N` prints dependabot's latest comment on a PR
- `dependabot_sweep.py merge-method --repo O/N` infers the merge method from recent merged PRs

`${CLAUDE_SKILL_DIR}/../../scripts/pr_watch.py` does the polling, as `merge-fix-loop` describes. Pass its global
`--repo O/N` before the subcommand, as in `pr_watch.py --repo O/N watch`. That works without a checkout. One invocation
names one repo, so run one watcher process per repo.

`gh` reads its credentials from `~/.config/gh`, which the Bash sandbox blocks. Run every `gh`, `gcloud`, and script
command through `cg_run`, which runs outside the sandbox. When cg is unavailable, run them through Bash with the sandbox
disabled. Run every other command one at a time, per `${CLAUDE_SKILL_DIR}/../../rules/shell-discipline.md`.

## Step 1: Detect, without asking

No question belongs in this step.

1. Take the owner from `$ARGUMENTS`, or from `gh api user` when none is given. A duration such as `4h` is the budget
2. Run `dependabot_sweep.py inventory --owner O --out FILE`, with FILE in the scratchpad. It saves the search for later
   steps. When `truncated` is true, the owner has more open PRs than the limit. Say so
3. Read the grouping. Dependabot PRs are the sweep's work. Contributor PRs that are not from a bot are not dependabot's
   and not this skill's. List them for the user. Report PRs from other bots the same way
4. Run `dependabot_sweep.py classify --inventory FILE --out FILE`. It does the following for every dependabot PR,
   oldest first:
   - Checks provenance before anything else is trusted
   - Rereads a PR whose `mergeable` is `UNKNOWN`, because GitHub computes it lazily
   - Reads the comment-gated check summaries from REST, which the GraphQL fields behind `pr_watch.py` do not carry
   - Reads each repo's base for required checks
5. For each fork in the inventory, run `dependabot_sweep.py fork --repo O/N`
6. Read the repo's own guidance on PRs when a fix is likely: `CONTRIBUTING.md`, the PR template, `CLAUDE.md`

### Provenance

A PR counts as dependabot's only when all of these hold:

- The author is the dependabot app: the node ID is `MDM6Qm90NDk2OTkzMzM=`, the type is Bot, and the URL is
  `https://github.com/apps/dependabot`. `gh api 'users/dependabot[bot]'` shows the same values
- The head branch is in the same repository as the base (`isCrossRepository` is false)
- Every commit is authored by `dependabot[bot]` and has `verification.verified` true. The source is
  `gh api repos/O/N/pulls/N/commits`

A PR that fails any check is `provenance-flagged`. Two patterns to look for:

- A dependabot branch on a non-fork copy of another repo can carry that upstream's commits
- A dependabot branch can contain the owner's own commit that was later rewritten off the mainline

Both showed up as `CONFLICTING`. The fix is `@dependabot recreate`, or closing the PR. Never merge one.

### Buckets

- `provenance-flagged`: see above
- `archived`: the repo is read-only. Nothing can be done to its PRs
- `fork`: the repo is a fork. See "Forks"
- `conflicting`: the PR no longer merges. Usually a sibling merged first
- `comment-gated`: a Cloud Build check wants a comment before it runs. See "Comment-gated CI"
- `needs-approval`: a check is `action_required` for a reason other than a comment. A person approves it
- `red`: a check failed
- `waiting-on-ci`: checks are still running. An empty or null conclusion is pending
- `no-checks`: the PR is mergeable and no check ran. A `CLEAN` merge state with nothing run is not evidence
- `green`: every check passed and the PR is mergeable
- `unknown`: `mergeable` stayed `UNKNOWN` after the rereads. Run `classify` again later

The summary also reports per repo whether auto-merge is allowed, and whether the base has required checks.

### Forks

Version updates come only from `.github/dependabot.yml`. Alerts and security fixes are separate repo settings. Read them
at `repos/O/N/vulnerability-alerts` and `repos/O/N/automated-security-fixes`. The `fork` command reports both.

A fork with commits of its own (`has_own_commits`) keeps dependabot. A fork with none is a candidate for closing. Close
the fork's PRs before archiving it. An archived repo is read-only, so its PRs can no longer be closed.

## Step 2: Ask once, up front

Put every question this run needs into one AskUserQuestion call. Report what detection settled in a few lines beside it.

- **Buckets to act on**, as a multi-select, over the buckets that have PRs. Recommend `green`, `waiting-on-ci`,
  `comment-gated`, `conflicting`, and `red`. Never preselect `no-checks`. It is the last gate
- **Authorizations for this run**, as a multi-select. Each is a separate yes:
  - Post `/gcbrun` comments
  - Enable auto-merge on PRs where the repo allows it
  - Close fork PRs
  - Archive forks whose PRs are closed
- **Budget**, unless given. Offer 2 hours, 4 hours (recommended), and 8 hours

Never change a repo setting that the user did not authorize here. Auto-merge on a repo that does not allow it is a repo
setting. Leave it off and merge by hand once green.

Do not post any comment, merge, close, or archive for a bucket or an action the user left out.

## Step 3: Green PRs

For each `green` PR in a repo:

1. Choose the merge method. Use `dependabot_sweep.py merge-method --repo O/N`, which reads the repo's recent merged
   PRs. Use a method the repo allows, as `classify` lists under `merge_methods`
2. Read the PR's live base with `pr_watch.py --repo O/N snapshot --pr N`. Merge only when it is the repo's default
   branch
3. Auto-merge waits only for required checks. Look at `auto_merge_waits_for_checks` for the repo:
   - When it is true and the user authorized auto-merge, run `gh pr merge N -R O/N --auto --<method>`
   - When the base has no required checks, the merge state is `UNSTABLE` and not `BLOCKED`. Auto-merge would merge
     before CI finishes. Merge by hand with `gh pr merge N -R O/N --<method>` once the checks are green
4. Merge one PR in a repo at a time. A merge can make a sibling conflict. Run `classify --repo O/N` again afterward

## Step 4: Comment-gated CI

A check run with conclusion `action_required` whose output summary says `Needs /gcbrun from a collaborator` needs a
`/gcbrun` comment. `classify` reads the summary from REST (`gh api repos/O/N/commits/SHA/check-runs`) and puts the exact
comment to post in `gated[].command`.

- Some triggers want a pinned form. The summary `Needs /gcbrun(<sha>) to run latest commit` means the comment
  `/gcbrun(<head sha>)`. `classify` fills in the head SHA
- A stale `action_required` can come from a trigger that no longer exists. Before treating it as blocking, confirm
  with `gcloud builds triggers list` that the trigger is there. When it is gone, report the PR and leave it
- The check run name carries the GCP project ID in parentheses. Do not copy it into any file or message you write

Post the command bare:

```text
gh pr comment N -R O/N --body '/gcbrun'
```

Do not use `pr_watch.py comment` for this. It appends `<!-- merge-fix-loop -->` to every body. Cloud Build comment
control and dependabot commands can fail to fire when text follows the command. Post `/gcbrun...` and
`@dependabot rebase` or `@dependabot recreate` bare.

Then watch the PR with `pr_watch.py --repo O/N watch`. When a rebase or a new push changes the head, the gate returns.
Run `classify --repo O/N` and comment again.

## Step 5: Red PRs

Read the failing log before choosing anything. For GitHub Actions use `gh run view <run> --log-failed --job <job>`. For
Cloud Build use `gcloud builds log ID --region REGION --project PROJECT_ID`. `pr_watch.py --repo O/N failures --pr N`
gives the IDs.

- gcloud rejects a project number. Resolve it with `gcloud projects describe NUMBER --format='value(projectId)'`
- Read a trigger's config with `gcloud builds triggers describe`. GA has no `export`
- A trigger with `filename: cloudbuild.yaml` reads the file from the repo. In `cloudbuild.yaml` the step image is under
  `name:`, not `image:`

Then classify the failure from the log:

- **The bump raised the `go` directive past the CI image.** Fix the CI image in its own PR first. Use the toolchain's
  current stable release and pin no version in this skill. See "Fixing a red PR". Then rebase the dependabot PR
- **A major framework bump needs a code migration.** An example is a major SvelteKit release rejecting the old
  `svelte.config.js` format. Report it and leave it. A migration is not a sweep's job
- **A flaky test.** Prove it first. The same failure must appear on a PR that touches no dependencies. Root-cause it
  with instrumentation. Never loosen the assertion. Land the fix as its own PR before the dependabot PR
- **Anything else.** Report it with the log excerpt

`@dependabot rebase` only helps when a refresh could plausibly turn the PR green, or when it conflicts after a sibling
merged. A rebase can change a group's contents. It can pull newer versions with new requirements. Re-comment `/gcbrun`
after the rebase lands.

The owner's own PRs are not dependabot's. They are the user's branches. Do not push them. See "Branches the Agent Owns"
in `${CLAUDE_SKILL_DIR}/../../rules/git-workflow.md`. Report them instead.

### Fixing a red PR

A red PR whose fix needs code is fixed on a separate branch:

1. Clone the repo into a scratch worktree under the scratchpad. No checkout of it is assumed
2. Create `agent/<topic>` from the default branch and make the fix
3. Run the repo's local check command, then follow `${CLAUDE_SKILL_DIR}/../merge-fix-loop/SKILL.md` on the fix PR, from
   its Step 3. Ask nothing it already answered in Step 2 here
4. After the fix PR merges, post `@dependabot rebase` on the dependabot PR, bare as above

This skill does not use `debug-ci`, which enters plan mode and stalls a loop. It does not use `land-branch`.

## Step 6: Waiting on dependabot

Dependabot's update jobs are not in REST. `repos/O/N/dependabot/*` returns 404. On a repo with Actions enabled they show
up as workflow runs. `dependabot_sweep.py updates --repo O/N` lists them. They have `event` `dynamic` and names such as
`go_modules in / for ... - Update #<id>`. The `Configured Graph Update: ...` runs are dependency-graph jobs and are not
update jobs.

Use the list to tell a queued rebase from an ignored one. A rebase can take about 30 minutes to start.

Read the latest dependabot comment before assuming silence. `dependabot_sweep.py last-comment --repo O/N --pr N` prints
it. Dependabot replies when it cannot act. One reason is that the `dependabot.yml` entry that created the PR was
deleted. Such a PR never closes itself. Close it by hand, when the user authorized closing.

## Step 7: Polling

Use `pr_watch.py --repo O/N watch` for every wait, never a hand-written sleep loop. Keep one watcher process per repo,
with its own state file under `~/.local/state/coding_agent_standards/dependabot-sweep/`. Use the scratchpad when that
cannot be written. Follow the three nested limits in `${CLAUDE_SKILL_DIR}/../merge-fix-loop/SKILL.md` "Waiting".

Any script you write for polling treats an empty or null check conclusion as pending. In jq, `""` is truthy, so write
`(.conclusion // "") == ""`. Never put an empty alternation in `grep -E`. Some greps, such as ugrep, error on `a||b`.

## Step 8: The no-checks gate

Triage the `no-checks` bucket last, with the user, as one review gate. Show the whole bucket in one message with each
PR's title, repo, and merge state. Wait for the user's pick per PR: merge, close, or leave. Do not ask these one by one
across earlier steps.

## Stopping

Stop and report when the budget runs out, or when every remaining PR is blocked on a person or a credential.

The report lists, per repo, what merged, what is waiting, and what needs the user. Name the PR URL for each. Include the
contributor PRs, the provenance-flagged PRs, the PRs that need a migration, and any fork left open. End with the
re-entry command, `/dependabot-sweep <owner>`, which runs detection again.

## Rules

- Verify provenance before you merge, comment on, or close any PR
- Every comment, merge, close, and archive was authorized in Step 2. If it was not, skip it and report
- Never merge a PR past a failing required check
- Never push to a branch you do not own
- Never copy a GCP project ID or number from a check name into a PR comment, PR body, or commit message
