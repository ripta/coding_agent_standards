---
name: land-branch
description: |
  Land a branch, or the branch up to a given commit, into the mainline through
  PRs, without touching the user's branch. Snapshots it onto an agent-owned
  staging branch in a worktree, splits a large range into batches that land
  concurrently when they are independent, and runs the merge-fix loop on each
  batch until every one merges. Triggers: "land this branch", "land up to
  <commit>", "ship this branch as PRs", "split this branch into PRs and get
  them merged". DO NOT trigger on: listing the next chunk without acting (use
  next-pr), or driving one existing PR to merged (use merge-fix-loop).
argument-hint: "[branch | commit] [budget, e.g. 6h]"
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, AskUserQuestion, Agent, Skill, mcp__cg__cg_run, mcp__cg__cg_wait
---

You land a range of commits in the mainline. The user keeps working on their branch while you do. You work on your own
staging branch and your own PR branches, so nothing you do moves the user's branch.

This skill is the coordinator. It plans the batches, opens their PRs, and watches all of them at once. It applies
`${CLAUDE_SKILL_DIR}/../merge-fix-loop/SKILL.md` to each PR. Read that file now. Its branch ownership, scripts,
waiting rules, triage, and stopping rules all apply here.

## Branch ownership

Every branch this skill creates is yours: the staging branch and every batch branch. Name them under `agent/`. The
user's branch and the mainline are the user's. Read them and fetch them, but never push, reset, or rebase them. See
"Branches the Agent Owns" in `${CLAUDE_SKILL_DIR}/../../rules/git-workflow.md`.

## Step 1: Detect, without asking

No question belongs in this step.

1. Establish the mainline and the source branch, per "Establishing the Branch Pair" in
   `${CLAUDE_SKILL_DIR}/../../project-management/commit-chunking.md`. The source is the branch the user named, or the
   checked-out branch. Run `git fetch origin` first, so the mainline is current
2. Look for a run file, described in "Run state" below, whose snapshot is on the source branch. When one exists, this
   is a resume. Take the plan, PRs, policy, and deadline from it, report them in one line, and go to Step 5
3. Fix the snapshot. When `$ARGUMENTS` names a commit, the snapshot is that commit, and it must be on the source branch.
   Otherwise it is the source branch's tip, now. Record its full hash. Commits the user adds later are not part of this
   run. Uncommitted changes in the user's checkout are never part of it
4. Find the range: `git merge-base origin/<mainline> <snapshot>`, then
   `git log --reverse --no-merges --format='%h %s' <base>..<snapshot>`. A range with merge commits from the
   mainline is fine, since `--no-merges` leaves them out. A range with other merges needs the user. Report it and stop.
   Stop too when the range is empty. In that stop message, list the local branches that hold work the mainline lacks.
   For each branch from `git for-each-ref refs/heads`, run `git cherry origin/<mainline> <branch>`. Keep the branch
   when any line starts with `+`, and show its count of `+` lines. The user's next `/land-branch <branch>` is then
   obvious
5. Run `pr_watch.py preflight --base <mainline>` through `cg_run`, as `merge-fix-loop` describes
6. Read what the repository says about kinds of change that merge differently. Look in `CONTRIBUTING.md`, the project's
   `CLAUDE.md` or `AGENTS.md`, `CODEOWNERS`, the rulesets and branch protection preflight reported, and the `paths` and
   `paths-ignore` filters in CI workflows. Note each kind that merges with fewer checks or without review, such as docs
   whose CI skips the test job. Only what the repository states counts. When it states nothing, there is no such kind
7. Decide whether stacking is on offer. Stacked PRs need merge commits. All of these must hold:
   - The merge method this run will use is MERGE. Take it from the repository's guidance, else from
     `viewerDefaultMergeMethod`, as `merge-fix-loop` Step 5.3 does. It applies to parents and children alike
   - Preflight's `merge_methods.allowed` includes MERGE
   - Preflight reports no `merge_queue`

   Then preflight's `ci_builds_other_bases` sets the recommendation. `yes` recommends stacking. `unknown` offers it
   without a recommendation. `no` does not offer it. Name the failed condition in the report.

   When guidance is silent and the viewer default is not MERGE, stacking would force MERGE. That changes the mainline's
   history shape. Offer it with that stated, and do not recommend it. `deleteBranchOnMerge` is not a condition, since
   Step 5 retargets children before the parent branch is deleted
8. Do the rest of `merge-fix-loop` Step 1: the local check command, and who reviews here

## Step 2: Plan the batches

1. Group the range into streams. A stream is a run of commits that depend on each other. Two commits are in one stream
   when one touches lines the other changed, or uses something the other adds, such as a function, a config key, or a
   migration. Commits that share neither land independently, so they go in separate streams. When you cannot tell,
   put them in one stream
2. Within each stream, keep the commits in their original order. Cut the stream into batches with the boundary
   heuristics in `commit-chunking.md`. One queue row of work is one batch. Its "never reorder" constraint holds
   inside a stream. Splitting the range into streams is this skill's own step, and its "Output only" scope belongs to
   `next-pr`, not to this skill
3. A batch after the first in a stream lands behind the batch before it. Record that in its `after` list. A batch in a
   kind the repository fast-tracks may land ahead of others, but only when its stream allows it
4. A range that forms one batch is the small case. Land it as one PR. Everything below still applies
5. Write the plan to the scratchpad as JSON. `${CLAUDE_SKILL_DIR}/../../scripts/batch_plan.py` defines the format in its
   docstring. `base` is the merge base and `tip` is the snapshot
6. Run `batch_plan.py verify --plan <file>`. It proves two things in a throwaway worktree. Each batch applies on the
   base plus only the batches it is `after`. Every batch applied in order rebuilds the snapshot's tree exactly
7. When a batch does not apply, it depends on something its `after` list lacks. Add the dependency, or merge it into
   that stream. When the tree does not match, or `missing` or `extra` is not empty, the plan lost or added work. Fix the
   plan and verify again. Never ask the user to approve a plan that fails verification
8. The branch may hold empty marker commits that the user wants left out of PRs and merges, such as one with the subject
   `8< --- snip ---`. List their full hashes in the plan's `exclude` array. Only a commit with no change of its own
   belongs there. Never put a non-empty commit in `exclude`, and never drop one the user did not mark. `verify` reports
   the accepted ones under `excluded`. It lists an entry that is not empty, or not on the range, under
   `exclude_errors`, and the plan then fails. An empty commit not in `exclude` still counts as `missing`

By default a batch that depends on another waits for it to merge, then opens against the mainline. That is a serial
batch.

When Step 1 offered stacking and the user chooses it, a batch may instead stack: its PR opens with the parent batch's
branch as its base. Run `batch_plan.py reduce --plan <file>`, which drops each `after` entry another entry already
reaches.

A batch stacks only when its reduced `after` names exactly one batch and that batch is in its own stream. A batch that
is after a batch in another stream is serial. A batch with two or more reduced parents, such as a diamond, is serial.
Record each batch's `pr_base` in the run file. The plan JSON does not carry it, and `verify` needs no change.

## Step 3: Ask once, up front

Put every question into one AskUserQuestion call. The plan approval is part of it.

- **The plan.** Show each excluded commit with its subject, and say it is left out. Show each batch: its name, its
  commits, what it lands after, and its PR title. Mark which batches open concurrently at the start. Offer to approve
  it, to land the whole range as one PR, or to adjust it through "Other". When stacking is on offer, show the plan both
  ways, stacked and serial, and mark which batches stack on which. Use Step 1's recommendation. When the mainline
  requires up-to-date branches, say that every child rebuilds after its parent merges. Stacking then gains early failure
  detection and early review, not a shorter total time
- **Review policy**, in the order `merge-fix-loop` Step 2 gives. One answer covers every batch
- **Budget** for the whole run, not per batch. Offer 4 hours, 8 hours (recommended for more than two batches), and 12
  hours
- **Credentials** for each preflight `needs` entry the user must fix

Report what detection settled in a line or two. Approving the plan authorizes every branch, push, PR, and merge it
names. It authorizes nothing else.

Once the user approves, write the run file.

## Step 4: Stage the snapshot

Create the staging branch and its worktree at the snapshot:
`git worktree add -b agent/stage/<topic> .claude/worktrees/stage-<topic> <snapshot>`. It is never pushed. It holds the
snapshot steady while the user's branch moves, and it is the reference the final check compares against.

## Step 5: Land the batches

A serial batch is ready when every batch in its `after` list has merged. A stacked batch is ready once its parent's
branch is pushed. For each ready batch:

1. Run `git fetch origin`
2. Create the batch branch in its own worktree. A serial batch starts from the current mainline:
   `git worktree add -b agent/<topic>/<batch> .claude/worktrees/<topic>-<batch> origin/<mainline>`. A stacked batch
   starts from its parent's tip, `origin/agent/<topic>/<parent>`
3. Cherry-pick the batch's commits in order. A batch whose `after` batches merged, or whose parent branch it started
   from, already has their work, so it cherry-picks only its own commits. A conflict here means the mainline moved under
   the plan. Resolve it when the resolution is mechanical. When it needs a judgement, show the user both sides, and keep
   landing the other batches
4. Run `merge-fix-loop` Steps 3 through 5 for the batch: local checks, push, PR, confirm checks, turn on merging. The PR
   title comes from the plan. Write each PR body from that batch's own diff, and name the batches it lands after.
   Every watch uses the run's watch state file, so no event is reported twice. Pass `merge_into`, the mainline. Each
   batch's `merge_into` lives in that PR's `merge-fix-loop` `.loop.json`. The run file does not copy it. Open a
   stacked batch's PR with `--base` set to the parent's branch. Never turn on merging for a stacked batch. The
   `merge_into` gate refuses it while the base is the parent branch

Then watch every open batch PR with one watcher: `pr_watch.py watch --pr N --pr M --state FILE --timeout T`, one
`--pr` per open PR, and the run's watch state file. Act on each event as `merge-fix-loop` Step 6 describes, in that
batch's worktree. When a batch merges, clean it up as that step describes, then start every batch it made ready.

### Stacked batches

The rules here add to `merge-fix-loop`. They apply only to a run that stacked.

- **A parent merged.** Before anything deletes the parent's remote branch, which is `merge-fix-loop` "The PR merged"
  step 3, retarget every open child. Read the child's `baseRefName`. When it is not the mainline, run
  `gh pr edit N --base <mainline>`. GitHub may have retargeted it already, so the edit is safe to repeat. A retarget
  changes no SHA, so no `checks-done` fires again. Run `pr_watch.py snapshot` on the child to read its checks
- **Reuse or merge up.** Reuse the child's passing checks, unless one of these holds. Then merge the mainline into the
  child's worktree with `git merge origin/<mainline>`, run the local checks, and push:
  - a required check is missing, `ACTION_REQUIRED`, or failing on the head
  - the mainline requires up-to-date branches, so the child is `BEHIND`
  - a parent fix has not reached the child

  A retarget can dismiss approvals, so confirm the review requirement still holds. Then turn on merging per
  `merge-fix-loop` Step 5. The gate passes now, since the base equals `merge_into`
- **Checks that never appear.** CI may not build a PR whose base is a batch branch. A stacked child whose required
  checks never appear, as `no-checks` or by missing names, waits for its parent. It does not stop as `merge-fix-loop`
  Step 5.2 says. After the retarget, the merge-up gives it a build against the mainline. That is a serial landing,
  never a worse one. Never close and reopen a PR to start a build. The watcher treats closed as final
- **A parent was pushed to.** Every push to a parent batch must reach each open child. That covers a fix, and a merge
  of the mainline that resolved a conflict. Merge the parent branch into the child, never rebase or force-push, run
  the local checks, and push. The child must not merge until that is done and its required checks pass on the new
  head. A conflict that needs a judgement goes to the user, as in Step 5.3
- **A parent closed without merging.** Mark its stacked children stopped. Never retarget them, since they carry the
  parent's unmerged commits. Report it to the user

## Step 6: Confirm and clean up

When every batch has merged:

1. Run `git fetch origin`. Compare the snapshot with the mainline over the files the range touched:
   `git diff <snapshot> origin/<mainline> -- <files>`. Every difference must trace to a fix this run pushed or to other
   work merged into the mainline meanwhile. Report anything else as lost work
2. Remove the staging worktree with `git worktree remove`, and delete the staging branch with `git branch -D`. The
   comparison above showed its work landed. Delete the run file and its watch state file
3. Tell the user their branch's commits up to the snapshot have landed. Their branch still holds the originals.
   Rebasing it onto the mainline is their call

## Stopping

Stop under `merge-fix-loop`'s rules, applied to the whole run. Running out of budget stops every batch at once. Leave
every worktree and branch in place, and report each batch: merged, open with its blockers, or not started. End with the
re-entry command, `/land-branch <snapshot>`, which resumes from the run file. A squash merge leaves no trace of the
original commits on the mainline, so the run file is the only record of which batches landed.

Flag each open stacked child. Its base is an unprotected batch branch, so GitHub's Merge button is green. Warn the user
not to merge it by hand, and not to squash its parent.

## Run state

Keep the run file at `~/.local/state/coding_agent_standards/land-branch/<owner>-<repo>-<snapshot>.json`, with the
snapshot's short hash. A run that stacked keeps it in `.../land-branch/v2/` with the same name, so an older plugin
version starts fresh instead of misreading it. Resume looks in both places. Use the session scratchpad when the
directory cannot be written.

The file holds the snapshot, the verified plan, the review policy, and the deadline. Per batch, it holds the branch,
worktree, PR number, `pr_base`, and whether the retarget is done. It also holds the batch's status: not started, open,
merged, or stopped. Update it whenever a batch changes status. Delete it in Step 6, after the comparison passes.

On resume, reconcile each batch with its live PR. When a parent merged while the run was stopped, retarget its
children before deleting anything.

Each open PR also has `merge-fix-loop`'s state files. Use one watch state file for the run, beside the run file, with a
`.watch.json` suffix in place of `.json`, in the same directory.

## Rules

- Never push the staging branch. Never push to the user's branch or the mainline
- This session owns all watching. Delegate fix work only to subagents that return before the next wait, and name the
  batch's worktree in the brief. `merge-fix-loop`'s Rules say why a background subagent must not run its own watcher
- Every batch PR targets the mainline, or its parent batch's branch when the plan stacks it. Stacking needs merge
  commits. This skill does not stack in squash or rebase repositories
- When the plan and the code disagree after landing starts, such as a batch needing a commit from a stream it is not
  after, stop that batch and tell the user. Do not reshuffle commits between open PRs
