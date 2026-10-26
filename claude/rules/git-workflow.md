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
- On an agent-owned branch, the agent may commit, push, and merge the base in without asking, within the task that
  created it
- Never force-push, even an agent-owned branch. Merge the base in instead of rebasing, so every push fast-forwards
- Once the branch's PR has merged, or its work is confirmed on the target, delete it with `git branch -D`. A squash
  merge stops `git branch -d` from seeing the work, so the merge record is the evidence. Delete the remote branch too
- Never push to, reset, rebase, or delete a user's branch. `git fetch` is fine. `git pull` into a user's branch is not

## Destructive Operations

- Do not run `git reset --hard`, `git checkout .`, `git clean -f`, `git push --force`, or `git branch -D` unless the
  user explicitly requests it. The exception is `git branch -D` on a merged agent-owned branch, per "Branches the Agent
  Owns"
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
