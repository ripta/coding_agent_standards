---
name: land-branch
description: |
  Land a branch, or the branch up to a given commit, into the mainline through
  PRs, without touching the user's branch. Snapshots it onto an agent-owned
  staging branch in a worktree, rebased onto the mainline so work that already
  landed drops out. On a branch divided by snip markers, it lands the oldest
  batch. It splits a large range into batches that land concurrently when they
  are independent, and runs the merge-fix loop on each batch until every one
  merges. Triggers: "land this branch", "land up to <commit>", "ship this
  branch as PRs", "split this branch into PRs and get them merged", "ship the
  next batch". DO NOT trigger on: listing the next chunk without acting (use
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

Every branch this skill creates is yours: the staging branch and every batch branch. Name them with preflight's
`branches.prefix`. Below, `<prefix>` is that prefix, and `<sep>` is its last character. The user's branch and the
mainline are the user's. Read them and fetch them, but never push, reset, or rebase them. See "Branches the Agent Owns"
in `${CLAUDE_SKILL_DIR}/../../rules/git-workflow.md`.

## Step 1: Detect, without asking

No question belongs in this step. A rebase conflict in item 10 is a stop, not a question.

1. Run `pr_watch.py preflight` through `cg_run`, as `merge-fix-loop` describes, with no `--base` yet. When its
   `pr_target.target` is null, ask the **PR target** question from `merge-fix-loop` Step 2 now, save the answer, and
   run preflight again. Every later step needs the remotes it settles. Take
   `<mainline-remote>`, `<push-remote>`, and `<head>` from its `remotes` block, per "Remotes" in `merge-fix-loop`. Run
   `git fetch <mainline-remote>`, so the mainline is current. Also fetch `<push-remote>` when it differs
2. Establish the mainline and the source branch, per "Establishing the Branch Pair" in
   `${CLAUDE_SKILL_DIR}/../../project-management/commit-chunking.md`. Preflight's `base` is the repo's default branch.
   The source is the branch the user named, or the checked-out branch
3. Look for a run file, described in "Run state" below, whose snapshot is on the source branch. When one exists, this
   is a resume. Take the plan, PRs, policy, and deadline from it, report them in one line, and go to Step 5
4. Fix the snapshot. When `$ARGUMENTS` names a commit, the snapshot is that commit, and it must be on the source branch.
   Otherwise it is the source branch's tip, now. Record its full hash. Commits the user adds later are not part of this
   run. Uncommitted changes in the user's checkout are never part of it
5. Find the range: `git merge-base <mainline-remote>/<mainline> <snapshot>`, then
   `git log --reverse --no-merges --format='%h %s' <base>..<snapshot>`. A range with merge commits from the
   mainline is fine, since `--no-merges` leaves them out. A range with other merges needs the user. Report it and stop.
   Stop too when the range is empty. In that stop message, list the local branches that hold work the mainline lacks.
   For each branch from `git for-each-ref refs/heads`, run `git cherry <mainline-remote>/<mainline> <branch>`. Keep the
   branch when any line starts with `+`, and show its count of `+` lines.
   The user's next `/land-branch <branch>` is then obvious
6. When the mainline is not preflight's `base`, run `pr_watch.py preflight --base <mainline>` again
7. Read what the repository says about kinds of change that merge differently. Look in `CONTRIBUTING.md`, the project's
   `CLAUDE.md` or `AGENTS.md`, `CODEOWNERS`, the rulesets and branch protection preflight reported, and the `paths` and
   `paths-ignore` filters in CI workflows. Note each kind that merges with fewer checks or without review, such as docs
   whose CI skips the test job. Only what the repository states counts. When it states nothing, there is no such kind
8. Decide whether stacking is on offer. Stacked PRs need merge commits. All of these must hold:
   - The merge method this run will use is MERGE. Take it from the repository's guidance, else from
     `viewerDefaultMergeMethod`, as `merge-fix-loop` Step 5.3 does. It applies to parents and children alike
   - Preflight's `merge_methods.allowed` includes MERGE
   - Preflight reports no `merge_queue`
   - Preflight's `remotes.fork` is false. A PR's base must be a branch in the base repo, and a fork push never puts one
     there

   Then preflight's `ci_builds_other_bases` sets the recommendation. `yes` recommends stacking. `unknown` offers it
   without a recommendation. `no` does not offer it. Name the failed condition in the report.

   When guidance is silent and the viewer default is not MERGE, stacking would force MERGE. That changes the mainline's
   history shape. Offer it with that stated, and do not recommend it. `deleteBranchOnMerge` is not a condition, since
   Step 5 retargets children before the parent branch is deleted
9. Do the rest of `merge-fix-loop` Step 1: the local check command, and who reviews here
10. Stage the snapshot and rebase it. A branch landed before still holds the commits that landed, since landing copies
    them and leaves the user's branch alone. The rebase drops them, so every run plans against today's mainline. Create
    the staging branch and its worktree at the snapshot:
    `git worktree add --no-track -b <prefix>stage<sep><topic> .claude/worktrees/stage-<topic> <snapshot>`. It is never
    pushed. Record `git rev-parse <mainline-remote>/<mainline>` as `onto`. Then run `git rebase <onto>` in that
    worktree. Git skips each commit the mainline already has, and drops each one that becomes empty because it landed
    with edits. It keeps commits that were empty to begin with, such as snip markers. On a conflict, never resolve a
    file wholesale with `--ours` or `--theirs`:
    - First check whether the mainline already has the commit in edited form: `git log <onto> -F --grep=<subject>`,
      or cherry-pick it onto `<onto>` in a throwaway detached worktree. An empty pick means its content already
      landed. When it has, show the conflicting hunk beside the mainline's version, and stop. Ask the user whether to
      run `git rebase --skip`
    - Regenerate a generated file, such as a lockfile, with the project's own tool. Never merge one by hand
    - Stop on any other conflict. Show it, and ask the user. `git rebase --abort` returns the staging branch to the
      snapshot
11. Run the clobber guard. List the files the rebased range touches with `git diff --name-only <onto>..HEAD`. For each
    one, every difference in `git diff <snapshot> HEAD -- <file>` must also show in
    `git diff $(git merge-base <snapshot> <onto>) <onto> -- <file>`, because it came from the mainline. Stop on any
    difference that did not, and show it to the user
12. Pick the batch. A snip marker is an empty commit, its tree equal to its parent's, whose subject starts with
    `8< --- snip ---`. The markers in `<onto>..HEAD` cut it into segments: before the first marker, between markers,
    and after the last one. Drop the segments with no commits, such as one whose work all landed. When no commit is
    left outside the markers, the work has landed. Stop and say so, and list the branches with unlanded work as item 5
    does, ignoring snips. The segments make a drop of redundant snips unneeded on the staging branch.

    When `$ARGUMENTS` named a commit, or the range has no marker, the batch tip is `HEAD`. Otherwise it is the marker
    that closes the oldest segment. When no marker closes it, the batch tip is `HEAD`, and that segment may still be in
    progress. From here on, the range is `<onto>..<batch tip>`, and its markers are its excluded commits

## Step 2: Plan the batches

Find the snips before grouping anything. Run
`${CLAUDE_SKILL_DIR}/../../scripts/snips.py list --base <onto> --tip <batch tip>`. Every `snips` hash goes in the plan's
`exclude` array and in no batch, including when the range lands as one PR. Each snip still marks a batch boundary for
item 2. Show each `not_empty` commit to the user in Step 3. It is not a snip, so it stays in its batch.

1. Group the range into streams. A stream is a run of commits that depend on each other. Two commits are in one stream
   when one touches lines the other changed, or uses something the other adds, such as a function, a config key, or a
   migration. Commits that share neither land independently, so they go in separate streams. When you cannot tell,
   put them in one stream
2. Within each stream, keep the commits in their original order. Cut the stream into batches with the boundary
   heuristics in `commit-chunking.md`. A snip is a hard boundary there, so no batch holds commits from both sides of a
   snip. One queue row of work is one batch. Its "never reorder" constraint holds inside a stream. Splitting the range
   into streams is this skill's own step, and its "Output only" scope belongs to `next-pr`, not to this skill
3. A batch after the first in a stream lands behind the batch before it. Record that in its `after` list. A batch in a
   kind the repository fast-tracks may land ahead of others, but only when its stream allows it
4. A range that forms one batch is the small case. Land it as one PR. Everything below still applies
5. Write the plan to the scratchpad as JSON. `${CLAUDE_SKILL_DIR}/../../scripts/batch_plan.py` defines the format in its
   docstring. `base` is `onto` and `tip` is the batch tip
6. Run `batch_plan.py verify --plan <file>`. It proves two things in a throwaway worktree. Each batch applies on the
   base plus only the batches it is `after`. Every batch applied in order rebuilds the snapshot's tree exactly
7. When a batch does not apply, it depends on something its `after` list lacks. Add the dependency, or merge it into
   that stream. When the tree does not match, or `missing` or `extra` is not empty, the plan lost or added work. Fix the
   plan and verify again. Never ask the user to approve a plan that fails verification
8. Snip commits are in the plan's `exclude` array, never in a batch. See the start of this step. Only a commit with no
   change of its own belongs in `exclude`. Never put a non-empty commit there, and never drop an empty commit that is
   not a snip unless the user marked it. `verify` reports the accepted ones under `excluded`. It lists an entry that is
   not empty, or not on the range, under `exclude_errors`, and the plan then fails. An empty commit not in `exclude`
   still counts as `missing`

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
- **The snip batches.** Say how many commits the rebase dropped because they had already landed. When the batch tip
  is not a marker, say the batch has no closing marker, so its last commits may still be in progress. List each later
  segment with its commits. When a later segment is closed by a marker, offer to widen the run to every closed
  segment. Widening moves the batch tip to the last closing marker, then Steps 2 and 3 run again on the wider range. A
  trailing segment with no closing marker joins only when the user asks for it through "Other"
- **Review policy**, in the order `merge-fix-loop` Step 2 gives. One answer covers every batch
- **Budget** for the whole run, not per batch. Offer 4 hours, 8 hours (recommended for more than two batches), and 12
  hours
- **Credentials** for each preflight `needs` entry the user must fix

Report what detection settled in a line or two. Approving the plan authorizes every branch, push, PR, and merge it
names. It also authorizes the fix PRs that `merge-fix-loop` opens for a failure the mainline already has, when that
failure blocks a batch. See its "A failure the base already has". It authorizes nothing else.

## Step 4: Record the run

Once the user approves, record the run. The staging branch from Step 1 holds the rebased snapshot steady while the
user's branch moves. Its batch tip is the reference the final check compares against.

A serial run records itself with `${CLAUDE_SKILL_DIR}/../../scripts/land_batch.py`. Save preflight's output and the
verified plan to files in the scratchpad. Then run, through `cg_run`:

```sh
python3 land_batch.py init --plan <plan> --preflight <preflight> --snapshot <snapshot> --onto <onto> \
  --batch-tip <batch tip> --mainline <mainline> --merge-method <method> --topic <topic> \
  --worktrees .claude/worktrees --staging-branch <prefix>stage<sep><topic> --staging-worktree <staging worktree> \
  --check-command '<local check command>' --review-policy <policy> --deadline <ISO 8601 time>
```

The merge method is the one Step 1 item 8 settled. The script's docstring defines the run file. `init` prints the run
file's path and the watch state file's path. From then on, only `land_batch.py` writes the run file. A run that stacks
keeps its run file by hand instead. See "Run state".

To change the local check command mid-run, run `land_batch.py set-check-command --run <run> --check-command '<cmd>'`.
Never run `init` again for it. The next `open` of each open batch reruns the checks under the new command.

## Step 5: Land the batches

A serial batch is ready when every batch in its `after` list has merged. A stacked batch is ready once its parent's
branch is pushed. A serial run lands each batch through `land_batch.py`, as below. A run that stacks lands each batch by
hand, as "By hand" describes.

Run every `land_batch.py` command through `cg_run` from the user's checkout. Each prints one JSON object. Exit 0 means
the step is done. Exit 3 is a `stop` for you to act on. The worktree, branch, and PR stay in place. Re-run the same
command once you have acted, and it picks up from the live state. Exit 2 is a git or gh command that failed. Read its
`error`.

For each ready serial batch:

1. Write its PR title and body to files in the scratchpad. The title comes from the plan. Write the body from that
   batch's own diff, by following `${CLAUDE_SKILL_DIR}/../../commands/pr-description.md`. Name the batches it lands
   after. Pass `<mainline-remote>/<mainline>` as its base
2. Run `land_batch.py open --run <run> --batch <name> --title-file <file> --body-file <file>`. Set the cg wait above
   the local checks' usual duration. It fetches the remotes and creates the batch branch from
   `<mainline-remote>/<mainline>` in its own worktree. Then it cherry-picks the batch's commits, runs the local checks,
   pushes to `<push-remote>`, opens the PR against the mainline, and writes the PR's `merge-fix-loop` `.loop.json`.
   `land_batch.py status --run <run>` lists the ready batches

Then watch every open batch PR with one watcher: `pr_watch.py watch --pr N --pr M --state FILE --timeout T`, one
`--pr` per open PR, and the run's watch state file. Re-arm it after every step below. Act on each event as
`merge-fix-loop` Step 6 describes, in that batch's worktree, with these additions:

- **`checks-done`.** Run `land_batch.py merge --run <run> --batch <name>`, whatever failed. It turns on merging only
  when the PR's base is the mainline, its head is the one `open` pushed, and every check finished with no required
  check failed. Handle each check in its `failed_not_required` list, or in a `checks-failed` stop, as `merge-fix-loop`
  "A check failed" says
- **`merged`.** Run `land_batch.py finish --run <run> --batch <name>`. It removes the worktree, the local branch, and
  the pushed branch, and deletes the PR's state files. Its `ready` list names the batches to `open` next
- **Any change to a batch branch.** A fix for a failed check or a review comment, and a rebase after a conflict, all
  start in the batch's worktree. Commit or rebase there, then re-run `open`. It reruns the local checks on the new head
  and pushes it, with a lease pinned to the head it last pushed when a rebase rewrote the branch. Never push a batch
  branch by hand in a serial run. The run file would not know the new head, and `merge` refuses a head it did not push

Act on each `stop` by its name:

- `cherry-pick-conflict` means the mainline moved under the plan. Resolve it in the worktree when the resolution is
  mechanical, and finish with `git cherry-pick --continue`. When it needs a judgement, show the user both sides, and
  keep landing the other batches. A pick that came out empty already landed. Show it to the user. Skip it only with
  their answer, then re-run `open` with `--picked`
- `cherry-pick-in-progress` means a pick is still unfinished in the worktree. Finish it as above
- `pick-count-mismatch` means the worktree holds a different number of picked commits than the batch. Compare them
  with the plan. Re-run `open` with `--picked` only when every commit is there or the user agreed to skip one
- `branch-without-worktree` means the batch branch exists with no worktree. Show the user, and land that batch by hand
- `worktree-without-run-record` means the batch's worktree exists, but the run file never recorded creating it, as after
  a second `init`. Use `set-check-command` instead of a second `init` next time. Show the user, with `git cherry`
  comparing the batch branch to the source branch. Remove the worktree and the batch branch only with their answer, then
  re-run `open`
- `local-checks-failed` names a log. Classify the failure as `merge-fix-loop` "A check failed" says, and fix it as above
- `checks-failed` names required checks that failed. Fix them as above. `merge` runs again on the next `checks-done`
- `checks-pending` and `not-clean` wait for the next event. `no-checks` follows `merge-fix-loop` Step 5.2
- `not-ready`, `not-merged`, `not-open`, and `batch-done` mean the command came too early or too late. Check `status`
- `pr-closed` means the PR closed without merging, and the batch is now stopped. Follow `merge-fix-loop` "The PR closed
  without merging". The batches after it cannot start
- `head-moved` and `base-not-mainline` mean someone else changed the PR. Stop that batch and tell the user
- `open-prs-on-branch` means a PR is based on the batch's branch. Report it before anything deletes the branch

### By hand

A run that stacks lands each ready batch with these steps:

1. Run `git fetch <mainline-remote>`
2. Create the batch branch in its own worktree. A serial batch starts from the current mainline:
   `git worktree add --no-track -b <prefix><topic><sep><batch> .claude/worktrees/<topic>-<batch> <mainline-remote>/<mainline>`.
   A stacked batch starts from its parent's tip, `<push-remote>/<prefix><topic><sep><parent>`, also with `--no-track`
3. Cherry-pick the batch's commits in order. A batch whose `after` batches merged, or whose parent branch it started
   from, already has their work, so it cherry-picks only its own commits. A conflict here is handled as
   `cherry-pick-conflict` above
4. Run `merge-fix-loop` Steps 3 through 5 for the batch: local checks, push, PR, confirm checks, turn on merging. The PR
   title and body come as step 1 of the serial steps says. Pass `merge_into`, the mainline. Each batch's `merge_into`
   lives in that PR's `merge-fix-loop` `.loop.json`. The run file does not copy it. Open a stacked batch's PR with
   `--base` set to the parent's branch. Never turn on merging for a stacked batch. The `merge_into` gate refuses it
   while the base is the parent branch

Watch with one watcher and the run's watch state file, as above. When a batch merges, clean it up as `merge-fix-loop`
"The PR merged" describes, then start every batch it made ready.

### Stacked batches

The rules here add to `merge-fix-loop`. They apply only to a run that stacked.

- **A parent merged.** Before anything deletes the parent's remote branch, which is `merge-fix-loop` "The PR merged"
  step 3, retarget every open child. Read the child's `baseRefName`. When it is not the mainline, run
  `gh pr edit N --base <mainline>`. GitHub may have retargeted it already, so the edit is safe to repeat. A retarget
  changes no SHA, so no `checks-done` fires again. Run `pr_watch.py snapshot` on the child to read its checks
- **Reuse or rebase.** Reuse the child's passing checks, unless one of these holds. Then rebase the child onto the
  mainline in its worktree with `git rebase <mainline-remote>/<mainline>`, run the local checks, and push with a pinned
  lease as `merge-fix-loop` "The PR conflicts with its base" says:
  - a required check is missing, `ACTION_REQUIRED`, or failing on the head
  - the mainline requires up-to-date branches, so the child is `BEHIND`
  - a parent fix has not reached the child

  A retarget can dismiss approvals, so confirm the review requirement still holds. Then turn on merging per
  `merge-fix-loop` Step 5. The gate passes now, since the base equals `merge_into`
- **Checks that never appear.** CI may not build a PR whose base is a batch branch. A stacked child whose required
  checks never appear, as `no-checks` or by missing names, waits for its parent. It does not stop as `merge-fix-loop`
  Step 5.2 says. After the retarget, the rebase gives it a build against the mainline. That is a serial landing,
  never a worse one. Never close and reopen a PR to start a build. The watcher treats closed as final
- **A parent was pushed to.** Every push to a parent batch must reach each open child. That covers a fix, and a rebase
  of the parent onto the mainline that resolved a conflict. Before the parent's push, note its old head. Then rebase
  each child onto the new parent with `git rebase --onto <push-remote>/<parent> <old parent head>`, run the local
  checks, and push with a pinned lease. Never merge the parent into the child. The child must not merge until that is
  done and its required checks pass on the new head. A conflict that needs a judgement goes to the user, as
  `cherry-pick-conflict` says
- **A parent closed without merging.** Mark its stacked children stopped. Never retarget them, since they carry the
  parent's unmerged commits. Report it to the user

## Step 6: Confirm and clean up

When every batch has merged:

1. Run `git fetch <mainline-remote>`. Compare the batch tip with the mainline over the files the range touched:
   `git diff <batch tip> <mainline-remote>/<mainline> -- <files>`. Every difference must trace to a fix this run pushed
   or to other work merged into the mainline meanwhile. Report anything else as lost work
2. Remove the staging worktree with `git worktree remove`, and delete the staging branch with `git branch -D`. The
   comparison above showed its work landed. Delete the run file, its watch state file, and the files beside them that
   share its name, such as `land_batch.py`'s lock and check logs
3. Tell the user which commits landed: those up to the batch tip. Their branch still holds the originals. Rebasing it
   onto the mainline is their call. A later run on the same branch drops the landed commits in its rebase. List the
   segments left after the batch tip. When any remain, say that the next `land-branch` run on the branch ships the next
   batch. A rebase of their branch can leave its snips next to each other. When you run that rebase at their request,
   drop the redundant snips afterwards, per "Snip Commits" in `git-workflow.md`

## Stopping

Stop under `merge-fix-loop`'s rules, applied to the whole run. Running out of budget stops every batch at once. Leave
every worktree and branch in place, and report each batch: merged, open with its blockers, or not started. End with the
re-entry command, `/land-branch <snapshot>`, which resumes from the run file. A squash merge leaves no trace of the
original commits on the mainline, so the run file is the only record of which batches landed.

Flag each open stacked child. Its base is an unprotected batch branch, so GitHub's Merge button is green. Warn the user
not to merge it by hand, and not to squash its parent.

## Run state

A serial run's file lives at `~/.local/state/coding_agent_standards/land-branch/v3/<owner>-<repo>-<snapshot>.json`,
with the snapshot's short hash. `land_batch.py` writes it and keeps it current. Its docstring defines the format. Never
edit it by hand. Use the session scratchpad when the
directory cannot be written. Pass it to `init` as `--state-dir`.

A run that stacked keeps its run file by hand, in `.../land-branch/v2/` with the same name. Older plugin versions kept
serial runs by hand in `.../land-branch/`. `land_batch.py` refuses both kinds, so land their batches by hand. A
hand-kept file holds the snapshot, `onto`, the batch tip, the verified plan, the review policy, and the deadline. Per
batch, it holds the branch, worktree, PR number, `pr_base`, and whether the retarget is done. It also holds the batch's
status: not started, open, merged, or stopped. Update it whenever a batch changes status.

Resume looks in all three places. Delete the run file in Step 6, after the comparison passes.

On resume, reconcile each batch with its live PR. For a serial run, `land_batch.py status` lists each batch, and
re-running a batch's last command picks it up. When a parent merged while a stacked run was stopped, retarget its
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
