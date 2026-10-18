---
description: Own the changes in a domain, and handle change requests from other sessions
argument-hint: "[domain name] [checkout paths and scopes]"
---

Act as the guardian of the domain in $ARGUMENTS by following
`${CLAUDE_PLUGIN_ROOT}/project-management/guardian.md`. Commits follow
`${CLAUDE_PLUGIN_ROOT}/rules/git-workflow.md` and
`${CLAUDE_PLUGIN_ROOT}/rules/commit-style.md`. Read all three. If any cannot be
read, stop and tell the user the standards are not available.

Do not enter plan mode. A guardian edits and commits as requests settle.

1. Work through the guide's Starting section. When $ARGUMENTS gives no domain,
   ask for it via AskUserQuestion.

2. Wait. Each cross-session message is a request. Handle it by the guide's
   Handling a Request section, and keep the ledger current.

3. Between requests, do any work the user gives you in the domain. The guide's
   Rules section still applies.
