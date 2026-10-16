---
description: Write a PR title and description for the changes on this branch
argument-hint: "[base-ref]"
allowed-tools: Read, Bash(git log:*), Bash(git diff:*), Bash(git merge-base:*), Bash(git symbolic-ref:*), Bash(git branch:*), Bash(git rev-parse:*)
---

Write a PR title and description for the changes on the current branch.

Compare against `$ARGUMENTS` when given. Otherwise use the mainline branch from
`git symbolic-ref refs/remotes/origin/HEAD`, falling back to `main` or `master`.
Diff from the merge base, not the tip of the base branch.

Read `${CLAUDE_PLUGIN_ROOT}/rules/pr-style.md` for the description and
`${CLAUDE_PLUGIN_ROOT}/rules/commit-style.md` for the title. Treat the title as a
commit subject. If either file cannot be read, stop and tell the user the
standards are not available.

Read both the commit log and the diff. Describe what the branch changes and why.
Do not repeat commit messages or list commits. Several commits often make one
change, so collapse them. Keep it concise.

Do not create the PR, push, or modify the repository.

Emit the title on its own line, then the description, as raw markdown.
