# Git Workflow

## Committing

- Do not run `git commit`, `git add`, or `git push` unless the user explicitly asks.
  The user reviews every change and commits it themselves, so when work is complete,
  stop and yield control
- A project's own instructions may authorize committing without being asked. That grant overrides the bullet above,
  per `precedence.md`. It covers commits only, never pushes
- Asking for work whose purpose is to push, such as landing a branch through PRs, is the explicit ask. It covers
  pushes to agent-owned branches only. See "Branches the Agent Owns"
- Exception: when a commit you made breaks `commit-style.md` and has not been pushed, reword it without asking. Keep
  its tree, author, and date unchanged. This never covers pushed commits or other people's commits
- When committing, name the paths in the commit itself: `git commit -- <paths>`. Staging by path and then running a
  bare `git commit` also commits whatever else is staged. Another session sharing the checkout may have staged its own
  files. Never use `git add -A`, `git add .`, or `git commit -a`
- When committing is allowed, check `git status` before reporting work done. Commit every file your own work left, or
  add an ignore line for a generated artifact such as `__pycache__/`. Leave files you did not make alone. Another
  session sharing the checkout may still be working on them

## Branches the Agent Owns

A branch the agent created for its own work is agent-owned. Examples are a worktree's branch, a staging branch, and a PR
branch a skill opened. Name such branches under `agent/`, unless the project names them otherwise. Every other branch
is the user's, including the checked-out branch and the mainline.

- When the user asks for work that needs a branch, such as landing a PR, the agent creates its own. It never pushes the
  user's branch to do that work
- On an agent-owned branch, the agent may commit, push, and rebase onto the base without asking, within the task that
  created it
- Bring a branch up to date by rebasing it onto its base. Never merge the base into a branch. Merges run one way only:
  the branch into the base
- Create an agent-owned branch with `--no-track`, such as `git worktree add --no-track -b <branch> <path> <start>`.
  A branch started from a remote-tracking ref otherwise tracks that ref
- Push an agent-owned branch by full refspec: `git push -u origin refs/heads/<branch>:refs/heads/<branch>`. A short
  name is not safe. Under `push.default=upstream`, it pushes to the branch's upstream. That upstream can be the mainline
  or a parent branch
- Push a rebased agent-owned branch with
  `git push --force-with-lease=<branch>:<sha> origin refs/heads/<branch>:refs/heads/<branch>`. The `<sha>` is the remote
  head the rebase started from. A bare `--force-with-lease` checks against the remote-tracking ref, and any `git fetch`
  moves that ref. It can then overwrite a push the agent never saw. Never use a bare `--force`
- Once the branch's PR has merged, or its work is confirmed on the target, delete it with `git branch -D`. A squash
  merge stops `git branch -d` from seeing the work, so the merge record is the evidence. Delete the remote branch too
- Never push to, reset, rebase, or delete a user's branch. `git fetch` is fine. `git pull` into a user's branch is not

## Snip Commits

A snip commit marks the end of a run of work that is ready to land. Its subject starts with `8< --- snip ---`, and it
has no change of its own: its tree equals its parent's tree. A commit with such a subject and a change is not a snip.
Flag it to the user, and never drop it.

- Leave snips out of everything that lands. They never go into a PR, a merge, a chunk, or a batch
- A snip is redundant when the commit right before it is also a snip. Only the first snip of such a run marks anything.
  A snip with other commits before it is not redundant. Neither is a snip sitting directly on the base
- Each snip ends a chunk of work. Choosing the next chunk or batch to land starts from the snips. See
  `project-management/commit-chunking.md`
- A rebase can put snips next to each other, when the work between them already landed. After any rebase you run,
  drop the redundant snips right after it, in the same task. This does not grant a rebase. A user's branch is rebased
  only when the user asks
- `scripts/snips.py` in the plugin does both. `list --base <base>` reports the snips, the redundant ones, and any
  commit with the snip subject that is not empty. `drop --base <base> --redundant` drops the redundant snips from the
  checked-out branch, and `--all` drops every snip. `<base>` must be an ancestor of HEAD, such as the commit the rebase
  just moved onto. A drop leaves the tip's tree unchanged. When it reports `tree_matches` false, stop and tell the user.
  `drop` refuses a range with merge commits

## Destructive Operations

- Do not run `git reset --hard`, `git checkout .`, `git clean -f`, `git push --force`, or `git branch -D` unless the
  user explicitly requests it. The exceptions are `git branch -D` on a merged agent-owned branch, and a pinned
  `--force-with-lease` push of a rebased agent-owned branch. Both are in "Branches the Agent Owns"
- Warn the user before any operation that discards uncommitted changes

## Worktrees

- Commit inside a worktree by path, the same as in the main checkout
- Integrate a worktree's branch before removing the worktree. Confirm it with `git branch --merged <target>`
- Remove a worktree with plain `git worktree remove`, and its branch with `git branch -d`. Both refuse when work would
  be lost. Never add `--force`, and never use `-D`, unless the user explicitly requests it or "Branches the Agent Owns"
  allows it
- A branch integrated by cherry-pick is not merged, so `git branch --merged` omits it and `git branch -d` refuses it.
  Confirm it with `git cherry <target> <branch>` instead. When every commit shows `-`, its work is on the target. Clean
  up without asking: remove the worktree with plain `git worktree remove`, then delete the branch with `git branch -D`.
  A commit that shows `+` is not on the target, so keep the branch and tell the user
- At an exit prompt, choose to keep a worktree that still holds work. Removing it deletes that work along with the
  directory and branch
