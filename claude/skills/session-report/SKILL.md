---
name: session-report
description: >-
  Write the current session's findings into a durable, self-contained,
  reproducible report file in the user's reports directory. Triggers: "write
  this up as a report", "write a report of these findings", "save/write this
  to my reports directory", "write the session findings to a
  file". DO NOT trigger on: code documentation, READMEs, commit messages, PR
  descriptions, meeting notes, or reports bound for Slack/Notion/Doc Hub.
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

`README.md` in the target directory is the authority on layout, naming, and
any templates — read it before writing and follow it. Where it is silent or
absent, fall back to observed convention:

- Standalone session report → `YYYYMMDD-short-slug.md` at the directory root
  (today's date, kebab-case slug naming the subject, not the activity).
- Report belonging to an existing project folder there → that folder's
  `reports/YYYY-MM-DD-short-slug.md`.

Check for filename collisions; on collision, extend the slug — never
overwrite an existing report.

## 3. What the report must contain

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

## 4. After writing

Report the absolute path of the file. The target directory is often a git
repo — do not commit or push unless explicitly asked.
