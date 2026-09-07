---
description: Find the next chunk of unmerged commits to merge into the mainline branch
allowed-tools: Bash(git log:*), Bash(git symbolic-ref:*), Bash(git branch:*), Read, Glob, Grep
---

Read `${CLAUDE_PLUGIN_ROOT}/project-management/commit-chunking.md` and follow it
to find the next chunk of unmerged commits ready to merge into the mainline
branch. If that file cannot be read, stop and tell the user the standards are
not available. Do not chunk commits from memory.

Output one chunk, not five. Stop after the first complete chunk.

Output only. Do not create branches or PRs, and do not modify the repository.
