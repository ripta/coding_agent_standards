# Git Workflow

## Committing

- Do not run `git commit`, `git add`, or `git push` unless the user explicitly asks.
  The user reviews every change and commits it themselves, so when work is complete,
  stop and yield control

## Destructive Operations

- Do not run `git reset --hard`, `git checkout .`, `git clean -f`, `git push --force`, or `git branch -D` unless the user explicitly requests it
- Warn the user before any operation that discards uncommitted changes
