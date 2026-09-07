---
description: Summarize this conversation's work as a commit message
allowed-tools: Read
---

Summarize the work done in this conversation in the format of a commit message.

Follow `${CLAUDE_PLUGIN_ROOT}/rules/commit-style.md` for the subject and body
rules, including the forbidden openers. If that file cannot be read, stop and
tell the user the standards are not available.

Use only the conversation. Do not run `git diff` or inspect uncommitted changes.
Do not commit.

Emit raw markdown.
