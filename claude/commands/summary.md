---
description: Summarize this conversation's work as a commit message
allowed-tools: Read, Bash(git log:*)
---

Summarize the work done in this conversation in the format of a commit message.

Follow `${CLAUDE_PLUGIN_ROOT}/rules/commit-style.md` for the subject and body
rules, including the forbidden openers. If that file cannot be read, stop and
tell the user the standards are not available.

Use only the conversation for the content. Run `git log` only to read the
repo's commit style, as `commit-style.md` asks. Do not run `git diff` or inspect
uncommitted changes. Do not commit.

Emit raw markdown.
