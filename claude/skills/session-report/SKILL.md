---
name: session-report
description: >-
  Write the current session's findings into a durable, self-contained,
  reproducible report file in the user's reports directory. Triggers: "write
  this up as a report", "write a report of these findings", "save/write this
  to my reports directory", "write the session findings to a
  file", "update the report", "keep a running report". DO NOT trigger on: code documentation, READMEs, commit messages, PR
  descriptions, meeting notes, or reports bound for Slack/Notion/Doc Hub.
model: sonnet
allowed-tools: Read, Write, Edit, Bash, Glob, Grep
---

# Session report

Turn what this session established into a report a stranger can read cold
and verify, validate, or reproduce months later. The report is a synthesis,
never a transcript.

## 1. Resolve the target directory

Preference file: `~/.config/coding_agent_standards/session-report.json`, shape
`{"default_dir": "/abs/path"}`. It is machine-local state. Never edit it into
this skill, never commit it anywhere.

`default_dir` may be relative, e.g. `./spec/reports`. A relative path resolves
against the current repo's root (`git rev-parse --show-toplevel`), never the
working directory. Outside a git repo, a relative `default_dir` doesn't exist.

The directory may sit behind a symlink into another repo, e.g. `./spec`
linking to a separate specs repo. Git does not follow such a link, so run
every git command on the report in the repo that owns its real path. Find the
real path with `realpath <dir>`, and the owning repo with
`git -C <real path> rev-parse --show-toplevel`. Give that repo paths relative
to its own root.

Precedence:

1. A path given in the request → use it for this report only; do NOT update
   the preference file unless the user says to make it the default.
2. Otherwise `default_dir` from the preference file.
3. If the file is missing or `default_dir` doesn't exist on disk, ask the user
   for the directory and verify it exists. Then write the preference file
   with the Write tool, which creates the parent directory. Bash cannot write
   there. Exception: when `default_dir` is
   relative, use the answer for this report only. Leave the file alone, since
   the relative default still serves other repos.

"Make <path> the default" (with or without a report to write) → validate and
update the preference file.

## 2. Read the target's standards

`README.md` in the target directory is the authority on layout, naming,
report location, frontmatter, and any templates. Read it, plus `CLAUDE.md` if
present (agent rules often live there), before writing and follow them. Use
these fallbacks only when the README says nothing about where reports go:

- Standalone session report → `YYYYMMDD-short-slug.md` at the directory root
  (today's date, kebab-case slug naming the subject, not the activity).
- Report belonging to an existing project folder there → that folder's
  `reports/YYYY-MM-DD-short-slug.md`.

If the README gives a location, the root fallback is wrong even when older
reports still sit there.

When the README points at the wiki standard, also read
`${CLAUDE_PLUGIN_ROOT}/knowledge/wiki.md`. Follow it for report naming,
frontmatter, and the report-writing sequence. Repo-specific rules stay in
that README.

When creating a report, check for filename collisions; on collision, extend
the slug. Never overwrite an existing report. Amending one this session owns
is not overwriting it; see below.

A report belongs to the work that created it. A long-running session may keep
one running report and update it as the work goes on. Whether it is committed
does not matter.

Every report records the session that owns it, in an HTML comment on the line
after the frontmatter, or after the title when there is no frontmatter:
`<!-- session-report owner: <id> -->`. An HTML report puts it in `<head>`.

The ID is `CLAUDE_CODE_SESSION_ID`. Read it with
`printenv CLAUDE_CODE_SESSION_ID`. When it is empty, leave the line out.

Amend a report only in these cases:

- Its owner line names this session's ID.
- The user names the report and asks to continue it, such as after `/clear`
  started a new session.
- This session continues the same work, such as a `/work-queue` run resumed in
  a new session.

In the last two cases, add this session's ID to the owner line, separated by a
space. Never amend a report on the strength of memory alone. Compaction can
blur which file this session wrote.

Re-read the report right before each edit and change it in place, never
rewrite it from memory. An update revises the report so it still reads as one
synthesis: the verdict, findings, and `Status` describe where the work stands
now. Do not append a dated log of updates.

If the report changed since you last read it, and you did not make the
change, another session may be writing it. Stop and ask the user.

When the work only extends or corrects someone else's report, write a new report and link back to it. If the README's
frontmatter can name earlier reports, such as a wiki's `follows` and
`corrects`, name them there too.

## 3. Frontmatter and topics

If the README specifies report frontmatter, write it exactly as specified.
The wiki standard's frontmatter is one example.

If the target has a topic or index layer, such as a wiki's `topics/<slug>.md`:

- **Tag existing topics.** List the topic pages and draw tags from their
  slugs. Create a new topic page only if none fits, following the README's
  template.
- **Update a topic only when the finding changes its position.** Then edit
  that page's hand-written position section, such as a wiki's "Current
  position" and its `reviewed` date, and nothing else. If the report only adds
  evidence, tagging is enough.
- **Never hand-edit generated content**: generated blocks in topic pages,
  reports, or a generated index, such as a wiki's "Reports" block, its
  later-reports block, and `index.md`. When the build rewrites an earlier
  report's generated block, commit that report with yours.

If the README names a build or lint command, such as a wiki's `bin/wiki
build` then `bin/wiki check`, run it after writing and fix any errors in files
you wrote or edited. Leave errors in other files alone and mention them. If
the tool only sees git-tracked or staged files, as the wiki tool does,
first stage your new files by explicit path in the owning repo (section 1):
`git -C <owning repo> add -- <report> <new topic page>`. Otherwise the build
silently leaves them out and the check passes without checking them. Staging
is not committing.

## 4. What the report must contain

Non-negotiable qualities, in addition to whatever the README specifies:

- **Self-contained.** No assumed session context: expand every codename,
  acronym, and internal system name on first use; absolute dates only (never
  "today"/"last week"); state which environment—cluster, tier, AWS account,
  region—every observation came from.
- **Verifiable.** Every factual claim carries its evidence: the exact command
  or query run (verbatim, copy-pasteable) and the relevant slice of its
  output; file paths with line numbers; URLs to builds, dashboards, tickets,
  PRs; versions and identifiers (image tags, instance IDs, build IDs).
- **Referenced in full.** Every ticket, PR, and commit carries its full URL,
  not a bare key or "the PR". A source reference outside the report's own repo
  is pinned to a commit, with line numbers, so it still points at the same
  lines after the file moves on.
- **Numbers carry their scope.** Every figure says what it covers: a time
  window, a lifetime total, or a share of a named whole. Never add or compare
  figures from different scopes. When a number will not reconcile with the
  others, fix it or cut it.
- **Reproducible.** A reader can redo the work: prerequisites (access, tools,
  profiles), query time ranges, and enough of the causal chain that each step
  follows from recorded evidence rather than assertion. List the
  prerequisites. Give each step one command and its output, and never merge
  several steps into one block.
- **Honest about certainty.** Separate confirmed findings from hypotheses from
  open questions. They are three distinct buckets, never blended.
- **Decision-ready.** If remediation or next steps exist, list the options
  with trade-offs and precedents; record decisions impersonally (what and why,
  never who).
- **Bounded.** The verdict or summary leads, above any detail, in one or two
  sentences. When the findings fall into categories, list them there, each
  with its status. A `Status` section at the bottom states exactly what was
  changed versus analysis-only, and what remains open.

Standard skeleton (adapt, don't force): title; date + trigger/context with
links; verdict or summary; findings with evidence; causal analysis;
remediation options or next steps; systemic/wider implications if any;
status.

Diagrams follow `${CLAUDE_PLUGIN_ROOT}/practices/diagrams.md`. Draw the causal
analysis of an incident as an events and causal factors chart, in a `mermaid`
fence. Charts of data follow the `data-visualization` skill.

When the report also gets an HTML rendering, read
`${CLAUDE_SKILL_DIR}/html-reports.md` before writing it.

## 5. After writing

Commit the report by default. Invoking this skill is the user's explicit ask
to commit, as `git-workflow.md` requires. A caller with its own commit rules
for reports, such as `/work-queue`, follows those instead. Skip the commit
only in these cases:

- The user says not to commit, in the request or earlier in the session.
- The report's real path is not inside a git repo.
- The owning repo's own rules, such as its `CLAUDE.md` or `AGENTS.md`, forbid
  agent commits. A project's rules override this default.

Commit only the explicit paths this report touched: the report, a regenerated
index, and touched topic pages. Commit them in the owning repo (section 1),
with `git -C <owning repo> commit -- <paths>`. Never use `git add -A` or
`git commit -a`. Other sessions may share the checkout, and the path form
leaves their staged files alone. Follow the owning repo's commit message
conventions. When a hook rejects the commit, report why. Never bypass it with
`--no-verify`.

Do not push unless explicitly asked. A commit grant is not a push grant.

A running report commits every update, so each revision stays durable. When
the user says report-update commits clutter the history, offer two other
cadences. One commits only when the report is done. The other folds the
updates into one commit at the end. Folding rewrites local commits, so it
needs the user's ask. Never switch cadence on your own.

Report the absolute path of the report and which topic pages were tagged
versus updated, and any created. Name the commit by subject and the repo it
landed in. When the commit was skipped, say which case skipped it.
