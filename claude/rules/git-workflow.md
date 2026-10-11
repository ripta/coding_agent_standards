# Git Workflow

## Committing

- Do not run `git commit`, `git add`, or `git push` unless the user explicitly asks.
  The user reviews every change and commits it themselves, so when work is complete,
  stop and yield control
- Exception: when a commit you made breaks `commit-style.md` and has not been pushed, reword it without asking. Keep
  its tree, author, and date unchanged. This never covers pushed commits or other people's commits
- When committing, name the paths in the commit itself: `git commit -- <paths>`. Staging by path and then running a
  bare `git commit` also commits whatever else is staged. Another session sharing the checkout may have staged its own
  files. Never use `git add -A`, `git add .`, or `git commit -a`

## Destructive Operations

- Do not run `git reset --hard`, `git checkout .`, `git clean -f`, `git push --force`, or `git branch -D` unless the
  user explicitly requests it
- Warn the user before any operation that discards uncommitted changes
