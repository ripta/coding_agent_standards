---
name: merge-fix-loop
description: |
  Drive a branch to merged. Pushes an agent-owned branch, opens a PR, enables
  auto-merge, then loops: waits on CI, triages and fixes failures, triages and
  answers review comments, until the PR merges or the time budget runs out.
  Triggers: "merge-fix loop", "get this PR merged", "babysit this PR",
  "push this and keep fixing until it merges". DO NOT trigger on: a one-off CI
  diagnosis (use debug-ci), writing a PR description only (use pr-description),
  or splitting a long branch into several PRs (use land-branch, which calls
  this skill per batch).
argument-hint: "[PR number | branch] [budget, e.g. 3h]"
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, AskUserQuestion, Agent, Skill, mcp__cg__cg_run, mcp__cg__cg_wait
---

You take one pull request from a branch to merged, and stay with it until it merges. You fix what CI and reviewers
find. You do not wander: every change you push answers a failing check or a review comment on this PR.

`land-branch` runs this loop for each of its batches. When it does, it passes the PR, the worktree, the review policy,
and the budget, so skip any question below that it already answered.

## Branch ownership

You work only on a branch you own. That rule is what lets this loop push without asking each time.

- You own a branch this skill or `land-branch` created in this run, or one recorded in this loop's state file. Every
  other branch is the user's. See "Branches the Agent Owns" in
  `${CLAUDE_SKILL_DIR}/../../rules/git-workflow.md`.
- On a branch you own, you may commit, push, merge the base in, and delete the branch once its PR merged.
- Never push to, reset, rebase, or delete a branch you do not own. That includes the user's checked-out branch and
  the base branch.
- Never force-push, not even your own branch. Resolve conflicts by merging the base into the branch, so every push
  fast-forwards. A reviewer's comments then stay attached to the commits they reviewed.

When the target is the user's branch, you do not push it. Create your own branch at the same commit, in its own
worktree, and run the loop there. See Step 3.

## Scripts

`${CLAUDE_SKILL_DIR}/../../scripts/pr_watch.py` does the polling and the GitHub API calls. Use it rather than writing a
poll loop by hand. Its subcommands print JSON:

- `pr_watch.py preflight --base BRANCH` reports gh access, merge settings, required checks and reviews, the CI systems
  the checkout configures, and a `needs` list of what is missing
- `pr_watch.py snapshot --pr N` prints the PR's state, checks, merge state, and unresolved thread count
- `pr_watch.py watch --pr N --state FILE --timeout SECONDS` waits and prints one JSON line per new event
- `pr_watch.py failures --pr N` lists failing checks, with the Actions run and job, or the Cloud Build build and region
- `pr_watch.py threads --pr N` lists unresolved review threads with every comment
- `pr_watch.py reply --thread ID --body-file FILE` replies in a review thread
- `pr_watch.py comment --pr N --body-file FILE` posts a conversation comment
- `pr_watch.py resolve --thread ID` resolves a review thread

`gh` reads its credentials from `~/.config/gh`, which the Bash sandbox blocks. Run every `gh` and `pr_watch.py` command
through `cg_run`, which runs outside the sandbox. Run them from the PR's worktree, so `gh` finds the repository. When
cg is unavailable, run them through Bash with the sandbox disabled.

`reply` and `comment` add a marker to every body they post. `watch` skips comments that carry it, so the loop's own
replies never wake it. The replies come from the user's `gh` identity, so do not filter comments by author. Always post
through these subcommands, never through `gh pr comment` directly.

## Waiting

Never sit idle with no deadline. Waiting has three limits, nested:

1. **The budget.** A wall-clock deadline for the whole loop, set in Step 2. Record it in the state file as an absolute
   time, so a resumed loop keeps it.
2. **One wait.** Each `watch` call gets `--timeout` set to the smaller of 1800 seconds and the budget left.
3. **The tool call.** Run `watch` through `cg_run` with `wait_timeout_ms` about 60 seconds above the script's timeout.
   If cg returns `timed_out`, resume it with `cg_wait`, and do not start a second watcher.

`watch` defaults to `--until event`. It exits after the first poll that finds anything to act on, so one tool call is
one wake-up. Act on every event it printed, push once, then arm the next wait. Its events are:

- `check-failed`: a check failed on the current head. It arrives before slower checks finish, so a fix can start early
- `checks-done`: every check on the head finished, with the passed and failed lists
- `no-checks`: the head commit has had no check at all for `--appear-timeout` seconds
- `comment`, `review`: someone else commented, or submitted a review with a body or with changes requested
- `conflict`: the PR no longer merges cleanly into its base
- `merged`, `closed`: the PR is done, one way or the other
- `timeout`: this wait ended with nothing new. Re-arm while budget remains
- `error`: `gh` failed three polls in a row. Read the message before deciding anything

Keep the state file at `~/.local/state/coding_agent_standards/merge-fix-loop/<owner>-<repo>-<number>.json`. Use the
session scratchpad when that directory cannot be written. The file records what was already reported, so a re-armed or
resumed watch never repeats an event. Record the deadline, the branch, and the worktree path in a second file beside
it, named with a `.loop.json` suffix in place of `.json`.

## Step 1: Detect, without asking

No question belongs in this step.

1. Resolve the target from `$ARGUMENTS`:
   - A PR number: read it with `pr_watch.py snapshot --pr N`. Its head branch is the branch
   - A branch name, or nothing: use the named branch, or the checked-out branch. Look for an open PR with
     `gh pr list --head <branch> --state open --json number,url`
   - A duration such as `3h` or `90m` is the budget
2. Look for this PR's `.loop.json` file. When it exists, this is a resume. Take the branch, worktree, policy, and
   deadline from it, report them in one line, and go to Step 6
3. Decide whether you own the branch, per "Branch ownership"
4. Run `pr_watch.py preflight --base <base>`. Read every entry in `needs`
5. Read the repository's own guidance on PRs: `CONTRIBUTING.md`, the PR template, and the project's `CLAUDE.md` or
   `AGENTS.md`. Note what it says about review, merge method, and checks
6. Find the local check command. Prefer `make ci` when the Makefile has it, since CI runs the same target. Otherwise
   use the project's documented test and lint commands
7. Learn who reviews here. Run `gh pr list --state merged --limit 10 --json number,reviews,comments` and note bot
   reviewers and how soon reviews landed. A repo whose PRs get a bot review within minutes is worth waiting for

## Step 2: Ask once, up front

Put every question this run needs into one AskUserQuestion call. Skip any that the arguments, a resume, or
`land-branch` already answered.

- **Review policy**, always, in this order:
  1. "Bots autonomous, humans gated" (recommended): fix, reply to, and resolve bot threads on your own. For a human's
     comment, draft the fix and the reply, and show both to the user before pushing, replying, or resolving
  2. "Everyone autonomous": triage, fix, reply to, and resolve every thread, human or bot
  3. "Fix only, never resolve": push fixes and reply with what changed, but leave every thread for its reviewer to
     resolve. When the base requires resolved threads, this leaves auto-merge waiting on a person
- **Budget**, unless given. Offer 2 hours, 4 hours (recommended), and 8 hours. A repo whose reviews usually take a day
  is a reason to suggest a shorter budget and a re-entry, not a longer wait
- **Credentials**, for each `needs` entry the user must fix. For example, Cloud Build logs need `gcloud auth login`,
  which the user runs as `! gcloud auth login`. Ask before the loop starts, not when the first failure needs the logs
- **No CI**, only when preflight found no CI system and the base requires no checks. Offer: merge once local checks pass
  and any required review is in; wait for a review, then merge; or open the PR and stop

Report what detection settled in a line or two, beside the question.

## Step 3: Prepare the branch

1. When you do not own the branch, make one you do. Name it `agent/<topic>`, where the topic is a short kebab-case
   name for the change. Create it in its own worktree at the target commit:
   `git worktree add -b agent/<topic> .claude/worktrees/<topic> <commit>`. The user's branch is left as it was
2. Work only in that worktree from here on. Never touch the user's checkout
3. Run the local check command. When it fails, fix the cause and commit before pushing. Do not open a PR that fails
   locally. A failure that is already on the base is not this PR's to fix. Note it for the PR description
4. Push with `git push -u origin <branch>`

## Step 4: Open the PR

When a PR is already open, skip to Step 5.

1. Write the title and body by following `${CLAUDE_SKILL_DIR}/../../commands/pr-description.md`, against the base. Write
   the body to a file in the scratchpad
2. Run `gh pr create --base <base> --head <branch> --title <title> --body-file <file>`
3. Write the `.loop.json` file: PR number, branch, worktree, base, review policy, and deadline

## Step 5: Confirm the checks, then turn on merging

1. Wait for the first checks: `pr_watch.py watch --pr N --state FILE --timeout T --until checks`. A head that reports no
   check within `--appear-timeout` prints `no-checks`
2. On `no-checks`, compare against preflight's required checks. When the base requires checks that never appeared, the
   CI did not trigger. Report it to the user and stop. When nothing is required, follow the user's "No CI" answer
3. When checks exist, turn on merging:
   - When the repo allows auto-merge, run `gh pr merge N --auto --<method>`. Use the method the repository's guidance
     names. Otherwise use preflight's `viewerDefaultMergeMethod`, provided the repo allows it
   - When the repo does not allow auto-merge, merge with `gh pr merge N --<method>` yourself, only once
     `pr_watch.py snapshot` shows `merge_state` `CLEAN`
4. Never merge past a failing required check, a missing required review, or a hold the repository's guidance names

## Step 6: Loop until merged

Arm `pr_watch.py watch --pr N --state FILE --timeout T`, act on what it reports, and arm it again. After every push,
check that auto-merge is still on with `pr_watch.py snapshot`, and turn it on again if a push or a conflict turned it
off.

### A check failed

1. Run `pr_watch.py failures --pr N`, and read the logs:
   - GitHub Actions: `gh run view <run> --log-failed --job <job>`, through `cg_run`. The captured stdout is the log
   - Cloud Build: follow `${CLAUDE_SKILL_DIR}/../debug-ci/SKILL.md` from its Step 4 to download and analyze the log.
     Skip its plan-mode step. This loop fixes the failure directly
   - Anything else: read the check's details URL. When it needs a login you lack, tell the user and keep handling the
     other events
2. Classify the failure from the log, not from the check's name:
   - **Caused by this PR.** Reproduce it locally with the matching target. Fix the cause. When it is a bug, write the
     regression test first and watch it fail, per `${CLAUDE_SKILL_DIR}/../../rules/work-discipline.md`. Never suppress a
     lint, skip a test, or loosen an assertion to go green
   - **Already failing on the base.** Check the same check on the base's latest commit. When it fails there too, it is
     not this PR's. Tell the user, and do not fix it here unless the user says so
   - **Flaky.** Only with evidence: the same test passes on a rerun with no change, or the log shows a known transient
     such as a registry timeout. Rerun once with `gh run rerun <run> --failed`. A second failure is not flaky
   - **Infrastructure or permissions.** A missing secret, quota, or credential. Report it to the user. Do not work
     around it
3. Commit each fix in the worktree with a message that follows the repository's commit style. Run the local check
   command, then push

### A review comment or review arrived

Triage each comment before changing anything:

- **Valid, and in this PR's scope.** Fix it, commit, and push. Reply with what changed and the commit hash, then resolve
  the thread when the policy allows
- **Valid, but outside this PR's scope.** Do not widen the PR. Reply that it is out of scope and say where it belongs,
  such as a follow-up issue. Leave the thread for its reviewer
- **Incorrect.** Reply with the reason and the evidence, such as the line that already handles the case. Resolve it only
  when the policy lets you resolve that author's threads
- **A question.** Answer it. When the answer shows the code is unclear, clarify the code too
- **Outdated.** The thread points at code a later push changed. Check whether the concern still holds, then treat it as
  above

Under "Bots autonomous, humans gated", a human's comment waits for the user. Show the comment, your triage, the drafted
fix, and the drafted reply in one message, then wait. Keep handling bot comments and CI while you wait. Under "Fix only,
never resolve", never resolve a thread.

Handle every comment from one wake-up together. Push once, then post the replies, so each reply can name the commit.
Write each reply to a file in the scratchpad and post it with `pr_watch.py reply`. Answer a conversation comment or a
review body with `pr_watch.py comment`.

### The PR conflicts with its base

In the worktree, run `git fetch origin`, then `git merge origin/<base>`. Resolve the conflicts. When a resolution needs
a judgement about what either side meant, show the user both sides before committing it. Run the local checks and push.

### The PR merged

1. Remove the worktree with `git worktree remove <path>`
2. Delete the local branch. GitHub reports the PR merged, so the work is on the base even when a squash merge stops
   `git branch -d` from seeing it. Use `git branch -D <branch>` for a branch you own
3. Delete the remote branch with `git push origin --delete <branch>`, unless the repository already deletes merged
   branches
4. Delete the `.loop.json` file and the state file

### The PR closed without merging

Stop. Report who closed it, and any comment that says why. Leave the branch and the worktree in place.

## Stopping

Stop and report when any of these happens:

- The budget runs out
- The same check fails on three heads in a row after your fixes. Your fixes are not converging
- A failure needs a credential, a permission, or a decision you do not have
- Every remaining blocker is a person: a required review not given, or a human thread waiting under the policy

Leave the worktree, the branch, and both state files in place. The report names the PR URL and its merge state. It
lists the pending checks, the unresolved threads with their authors, and every fix pushed. It ends with the re-entry
command, `/merge-fix-loop <number>`, which resumes from the state files.

## Rules

- Every push is to a branch you own, and fast-forwards
- Every change you push answers a failing check or a review comment on this PR. Note anything else you notice for the
  report instead
- Do the fix work yourself, or delegate it to a subagent that returns before you arm the next wait. Never hand a
  background subagent its own watcher or Monitor. Claude Code can drop the second report of a background subagent that
  still has background work running, and the loop then stalls with nothing left to wake it
- Run `gh`, `gcloud`, and `pr_watch.py` through `cg_run`. Run every other command one at a time, per
  `${CLAUDE_SKILL_DIR}/../../rules/shell-discipline.md`
