# Git Workflow

## Committing

- NEVER commit on behalf of the user
- NEVER run `git commit`, `git add`, or `git push` unless the user explicitly asks
- When work is complete, stop and yield control to the user
- The user will review changes and commit themselves

## Destructive Operations

- NEVER run `git reset --hard`, `git checkout .`, `git clean -f`, `git push --force`, or `git branch -D` unless the user explicitly requests it
- Warn the user before any operation that discards uncommitted changes
