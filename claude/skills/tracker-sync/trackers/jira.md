# Jira

Group kind: `epic`. The group `id` is the epic key (`CI-3718`). The tracker
entry carries `site` (`example.atlassian.net`) and `assignee` (an Atlassian
account ID, not an email or display name).

## Interfaces

Prefer the Atlassian MCP server when one is connected. Its tool names end in
`searchJiraIssuesUsingJql`, `getJiraIssue`, `addCommentToJiraIssue`,
`editJiraIssue`, `getTransitionsForJiraIssue`, `transitionJiraIssue`, and
`createJiraIssue`. The server prefix varies by machine, so find the tools by
those suffixes. The MCP tools take a `cloudId`, and the `site` value works there.

A CLI (`jira`, `acli`) also works for comments, transitions, and assignment,
if one is installed and authenticated. Do not write descriptions through a
CLI; common Jira CLIs mangle markdown on the way in. Use the MCP for
description edits.

Every MCP write echoes the whole issue back. Keep writes in the Apply
subagent so those echoes stay out of the main context.

## Operations

- **List group:** JQL `project = <PROJ> AND parent = <EPIC> ORDER BY key ASC`,
  where `<PROJ>` is the epic key's prefix. Always include the project clause;
  some sites reject JQL without one. Older company-managed projects link epics
  through `"Epic Link" = <EPIC>`. Fall back to it when `parent` returns nothing.
  Request only `summary`, `status`, `assignee`, `updated`, and `description`,
  in markdown, and save the result to the scratch directory. It is large.
- **Read ticket:** `getJiraIssue` with markdown content and the fields you
  need. Include `comment` only when the verdict depends on the discussion.
- **Comment:** markdown body with real newlines, never escaped `\n`.
- **Edit description:** read the current description, apply the change, and
  write the whole description back. The field takes markdown.
- **Close:** list transitions, pick the one whose target status is in the Done
  category (usually named `Closed`, `Done`, or `Resolved`), and pass
  `fields: {"resolution": {"name": "<resolution>"}}`. The resolution defaults
  to `Done`; use `Won't Do` or `Duplicate` only when the approved action says so.
  If the transition screen rejects the resolution field, retry without it and
  report that.
- **Assign:** `editJiraIssue` with `assignee: {"accountId": "<assignee>"}`.
- **Create in group:** `createJiraIssue` in the epic's project with
  `parent: {"key": "<EPIC>"}` and the project's standard issue type (read the
  project's issue-type metadata when unsure; never guess a type name).

## Ticket references

Commit messages and docs cite Jira tickets by bare key (`CI-9398`). Proposal
and ADR identifiers share that shape (`IRA-042`), so a key only counts as a
ticket reference when it appears in the group's listing.
