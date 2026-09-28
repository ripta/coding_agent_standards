---
name: tracker-sync
description: |
  Reconcile issue-tracker groups (Jira epics, Linear projects, GitHub tracking
  issues, milestones, or labels) with work merged in mapped repository
  subdirectories since the last sync. Closes or updates tickets whose work
  landed, proposes tickets for untracked proposals or phases, fixes phase and
  proposal doc drift, and backlinks ticket keys into docs. Triggers: "sync my
  tickets", "which tickets can I close", "update jira/linear/issues for what I
  merged", "reconcile <epic> with <path>", /tracker-sync. DO NOT trigger on:
  reading or summarizing a single ticket, sprint planning, starting work on a
  ticket, or filing a bug.
model: opus
allowed-tools: Agent, AskUserQuestion, Bash, Read, Edit, Glob, Grep
---

You reconcile issue trackers with what has actually merged. Merged work is the
source of truth. A ticket is done when its own completion criteria are met on
the default branch, not when a commit mentions it.

Tracker-specific operations live in `${CLAUDE_SKILL_DIR}/trackers/<type>.md`
(`jira`, `github`, `linear`). Read the file for each tracker type in scope
before touching that tracker. The phase and proposal model is
`${CLAUDE_SKILL_DIR}/../../project-management/plans.md`,
`proposals.md`, and `tracking.md`. Defer to a project's own deviation where one
exists.

`sync_scope.py` owns the config, repository identity, commit ranges, and
watermarks. Never edit the config file by hand. Below, `$SCOPE` is shorthand
for `python3 ${CLAUDE_SKILL_DIR}/sync_scope.py`. Write the full command in each
call: shell variables do not persist between calls, and zsh does not
word-split them.

## Config

`~/.config/coding_agent_standards/tracker-sync.json` is machine-local state:

```json
{
  "trackers": {
    "work-jira": {
      "type": "jira",
      "site": "example.atlassian.net",
      "assignee": "<account id>"
    },
    "gh": { "type": "github", "assignee": "<login>" }
  },
  "mappings": [
    {
      "repo": "github.com/org/monorepo",
      "paths": ["apps/foo"],
      "groups": [
        {
          "tracker": "work-jira",
          "kind": "epic",
          "id": "PROJ-100",
          "last_synced_commit": "<sha>"
        }
      ]
    }
  ]
}
```

- `repo` is the normalized origin URL, so every clone and worktree shares it.
- A mapping ties a set of paths to a set of groups. Several mappings may share
  a path or a group, so the relationship is many-to-many.
- Each group carries its own watermark. A group that fails to sync never holds
  back the others.

## Arguments

`/tracker-sync [paths...] [group refs...]`

- Group refs: `jira:PROJ-100`, `linear:<project>`, `gh:owner/repo#12`,
  `gh:owner/repo/milestone/<title>`, `gh:owner/repo/label/<name>`. A bare
  `PROJ-100` matches any configured group with that id.
- Anything else is a path relative to the repository root.
- No arguments: every mapping for the current repository.
- Arguments select mappings and groups; the scan always covers the mapping's
  full path set, so watermarks stay sound.

## Workflow

### Phase 1: Scope

1. Run `$SCOPE scope [--since REV] [args...]` from inside the repository.
2. `behind_origin > 0`: tell the user their default branch is behind origin
   and ask whether to continue on the local state. Never pull, fetch into the
   branch, or switch branches yourself.
3. `unmapped.paths` or `unmapped.refs` present: offer to save the mapping.
   - A new tracker needs
     `$SCOPE add-tracker --name N --type T --assignee WHO [--site S]`.
     Look the assignee up through the tracker's interface rather than asking
     for an opaque ID: the Atlassian user-info tool for Jira,
     `gh api user --jq .login` for GitHub, the viewer or `me` for Linear.
   - A bare key that could be Jira or Linear: ask which.
   - Then `$SCOPE add-mapping --path P ... --group TRACKER KIND ID ...`.
4. Any selected group with `since_source` `none` or `invalid-watermark`: ask
   how far back to look (a commit, a date, or a merged PR), then rerun
   `scope --since <that>` for that group only.
5. Record `head` from the output. Every later read, and the final watermark,
   uses that commit, even if the branch moves during the run.

### Phase 2: Tickets

For each selected group, confirm the tracker's interface is available (per
its `trackers/<type>.md`). If it is not, stop and tell the user what is
missing. Then list the group's tickets into a scratch file: all states, with
the fields that file names.

Delegate reading long ticket bodies to a subagent (`model: sonnet`) when the
group is large. Its job is extraction, not judgment: for each open ticket
return the key, title, state, assignee, stated completion criteria ("Done
when", acceptance criteria) verbatim, and every repo path, proposal,
phase, or ticket the body cites.

### Phase 3: Evidence

Read evidence at `head`. If the checkout is not the default branch at `head`,
read through `git show <head>:<path>` and `git grep <pattern> <head>` rather
than the working tree.

- The mapping's phase and proposal indexes (`docs/phases/index.md`,
  `docs/proposals/index.md` or the project's equivalent), and every phase or
  proposal doc among `changed_files`.
- Where each open ticket is cited in the mapping's docs: grep for its key.
- The commits in range whose `refs` name a ticket in the group.
- Code or config the ticket's criteria name. A criterion like "prod runs with
  X enabled" is checked in the prod config, not inferred from a phase status.

Every open ticket is assessed against the current state, not only tickets the
range touched. The range focuses attention; it does not bound it. Closed
tickets are out of scope unless a commit in range reverts work they depend on.
Flag those for the user; do not reopen them.

### Phase 4: Classify

Give each open ticket exactly one verdict, with evidence as `path:line` or a
commit SHA:

- **Close:** every completion criterion is met at `head`.
- **Close after follow-up:** the criteria are met except for one or two named,
  small items. Do not close. Propose a dated status note naming what remains.
- **Update:** the description is stale against `head` (a dependency that has
  landed, a starting point that has moved, work partly done). Propose the exact
  replacement or a dated `**Status (YYYY-MM-DD).**` paragraph, and leave every
  other word of the description intact.
- **No change:** the ticket accurately describes open work.

A ticket with no completion criteria cannot be judged done. Report it as
**Needs criteria** and propose nothing but a comment asking for them, or
name the work that appears to resolve it.

Then, across the mapping:

- **Untracked work:** a proposal or phase in scope that no ticket in the group
  covers. Propose a ticket: title, a short problem and "Done when" drawn from
  the doc, and the doc path.
- **Doc drift:** phase and proposal status mismatches, found with the checks
  in `${CLAUDE_SKILL_DIR}/../phase-cleanup/SKILL.md` (steps 2–6). Where a
  milestone reads done but its acceptance criteria are unchecked, report it
  and do not pick a side.
- **Missing backlinks:** a proposal or phase that a ticket tracks but that
  does not cite the ticket. Follow the project's existing citation convention.
  If there is none, propose a `## References` bullet
  (`- <tracker ref>: <ticket title>`) and say that it is a new convention for
  that project.

### Phase 5: Approve

Present the findings in the reply itself as tables grouped by verdict, each
row with the ticket, the proposed action, and the evidence. Write out every
proposed comment, status note, and new ticket in full. Do not put findings in
an AskUserQuestion preview; previews do not render everywhere.

Then ask once, with AskUserQuestion: apply all, apply with exclusions (the user
names them), or report only. Anything the user excludes is dropped, not
retried later in the run.

### Phase 6: Apply

Tracker writes go to one subagent per tracker (`model: sonnet`). Give it:

- the path to `trackers/<type>.md`, and the tracker entry (site, assignee);
- per ticket, the exact actions and verbatim text: comment, description change
  (with the exact anchor text to insert before or replace), close with
  resolution, or create;
- the instruction to assign every ticket it touches to the tracker's
  `assignee`, to touch no other ticket, and to report a table of ticket,
  actions, and result with the exact error text of any failure. The report
  must not include ticket bodies.

Repository edits (doc drift and backlinks) you make yourself, and only when
the checkout is the default branch at `head`. Otherwise show them as proposed
diffs. Follow `${CLAUDE_SKILL_DIR}/../../rules/git-workflow.md`: leave the
edits uncommitted and unstaged for the user.

### Phase 7: Verify

Re-list the touched tickets and check the state and assignee of each against
what was approved. Report any mismatch. Do not re-read full bodies unless a
write reported an error.

### Phase 8: Advance

For each group whose approved tracker writes all succeeded (a group with
nothing to change counts), run
`$SCOPE advance --mapping N --tracker T --kind K --id ID --commit <head>`.
Leave the watermark where it was for a group with any failed write, and for
every group in a report-only run.

Finish with a short report: per group, what was closed, updated, created, or
left alone; the repo files edited (uncommitted); the watermarks advanced; and
anything left for the user.

## Rules

- Never write to a tracker, the repository, or the config without the
  approval in Phase 5. The one exception is saving a mapping the user agreed
  to in Phase 1.
- Never close a ticket whose completion criteria are not all met at `head`.
  A commit that mentions a ticket is a lead, not evidence.
- Every verdict cites evidence. A verdict you cannot cite is **No change**.
- Never commit, stage, push, pull, or switch branches. Repository edits stay
  uncommitted for the user.
- Assign every ticket the skill touches to the tracker's configured
  `assignee`, and touch no ticket that was not approved.
- Description edits preserve all existing text except the approved change.
- Advance a watermark only to the `head` recorded in Phase 1, and only after
  that group's writes succeed.
- Tracker writes run in a subagent; keep issue bodies and write echoes out of
  the main context.
- Keep the config machine-local. Never copy config values into this skill or
  commit the config anywhere.
