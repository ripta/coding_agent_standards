---
description: Find the next chunk of unmerged commits to merge into the mainline branch
allowed-tools: Bash(git log:*), Bash(git rev-list:*), Bash(git symbolic-ref:*), Bash(git branch:*), Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/proposals.py locate:*), Read, Glob, Grep
---

Read `${CLAUDE_PLUGIN_ROOT}/project-management/commit-chunking.md` and follow it
to find the next chunk of unmerged commits ready to merge into the mainline
branch. If that file cannot be read, stop and tell the user the standards are
not available. Do not chunk commits from memory.

Read the queue of each component whose paths the commits touch, as that file's
"Finding Each Component's Queue" says. A chunk never mixes components that keep
separate queues.

Output one chunk, not five. Stop after the first complete chunk.

Output only. Do not create branches or PRs, and do not modify the repository.
