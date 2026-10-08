---
name: session-report
description: >-
  Write the current session's findings into a durable, self-contained,
  reproducible report file in the user's reports directory. Triggers: "write
  this up as a report", "write a report of these findings", "save/write this
  to my reports directory", "write the session findings to a
  file". DO NOT trigger on: code documentation, READMEs, commit messages, PR
  descriptions, meeting notes, or reports bound for Slack/Notion/Doc Hub.
model: sonnet
allowed-tools: Read, Write, Edit, Bash, Glob, Grep
---

# Session report

Turn what this session established into a report a stranger can read cold —
and verify, validate, or reproduce months later. The report is a synthesis,
never a transcript.

## 1. Resolve the target directory

Preference file: `~/.config/coding_agent_standards/session-report.json`, shape
`{"default_dir": "/abs/path"}`. It is machine-local state — never edit it into
this skill, never commit it anywhere.

Precedence:
1. A path given in the request → use it for this report only; do NOT update
   the preference file unless the user says to make it the default.
2. Otherwise `default_dir` from the preference file.
3. If the file is missing or `default_dir` doesn't exist on disk, ask the user
   for the directory, verify it exists, then write the preference file
   (create the parent directory if needed).

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
reports still sit there. (zip_specs files reports under
`reports/YYYY/MM/YYYYMMDD-slug.md`, or a directory of that name whose one
top-level `.md`, preferably `README.md`, carries the frontmatter.)

Check for filename collisions; on collision, extend the slug. Never overwrite
an existing report, and never rewrite another session's committed report: if
the work extends or corrects one, write a new report and link back to it.

## 3. Frontmatter and topics

If the README specifies report frontmatter, write it exactly as specified.
(zip_specs: `topics: [slug, ...]`, most relevant first, and `summary: "one
sentence"` stating the conclusion; `title:` only when the report has no H1.)

If the target has a topic or index layer (zip_specs: `topics/<slug>.md`):

- **Tag existing topics.** List the topic pages and draw tags from their
  slugs. Create a new topic page only if none fits, following the README's
  template.
- **Update a topic only when the finding changes its position.** Then edit
  that page's hand-written position section (zip_specs: "Current position",
  plus its `reviewed` date) and nothing else. If the report only adds
  evidence, tagging is enough.
- **Never hand-edit generated content**: generated blocks in topic pages or a
  generated index (zip_specs: the "Reports" block and `index.md`).

If the README names a build or lint command (zip_specs: `tools/wiki/wiki.py
build`, then `tools/wiki/wiki.py check`), run it after writing and fix any
errors in files you wrote or edited. Leave errors in other files alone and mention
them. If the tool only sees git-tracked or staged files, as zip_specs' does,
first stage your new files by explicit path (`git add -- <report> <new topic
page>`). Otherwise the build silently leaves them out and the check passes
without checking them. Staging is not committing.

## 4. What the report must contain

Non-negotiable qualities, in addition to whatever the README specifies:

- **Self-contained.** No assumed session context: expand every codename,
  acronym, and internal system name on first use; absolute dates only (never
  "today"/"last week"); state which environment — cluster, tier, AWS account,
  region — every observation came from.
- **Verifiable.** Every factual claim carries its evidence: the exact command
  or query run (verbatim, copy-pasteable) and the relevant slice of its
  output; file paths with line numbers; URLs to builds, dashboards, tickets,
  PRs; versions and identifiers (image tags, instance IDs, build IDs).
- **Reproducible.** A reader can redo the work: prerequisites (access, tools,
  profiles), query time ranges, and enough of the causal chain that each step
  follows from recorded evidence rather than assertion.
- **Honest about certainty.** Separate confirmed findings from hypotheses from
  open questions — three distinct buckets, never blended.
- **Decision-ready.** If remediation or next steps exist, list the options
  with trade-offs and precedents; record decisions impersonally (what and why
  — never who).
- **Bounded.** A `TL;DR` up top; a `Status` section at the bottom stating
  exactly what was changed versus analysis-only, and what remains open.

Standard skeleton (adapt, don't force): title; date + trigger/context with
links; TL;DR; findings with evidence; causal analysis; remediation options or
next steps; systemic/wider implications if any; status.

## 5. After writing

Report the absolute path of the report and which topic pages were tagged
versus updated (and any created). The target directory is often a git repo;
do not commit or push unless explicitly asked. When asked, commit only the
explicit paths this report touched (the report, a regenerated index, touched
topic pages) with `git commit -- <paths>`, never `git add -A` or
`git commit -a`: other sessions may share the checkout. Follow the target's
commit message conventions.
