---
name: new-proposal
description: |
  Create a new proposal from a short description, following the project's proposal
  standards. Determines the proposals directory, project prefix, and next sequential
  number, interviews the user to flesh out the design, and writes a draft proposal.
  Invoked as `/new-proposal <description>`; the description is optional.
model: opus
allowed-tools: Agent, AskUserQuestion, Bash, Read, Write, Edit, Glob, Grep
---

You create a single new proposal in `draft` status, following the project's proposal format. You gather just enough context to write a coherent draft, leave genuinely undecided questions as open design questions rather than guessing, and confirm the structure with the user before writing.

The canonical format and rules live in `project-management/proposals.md` (in the coding-agent-standards repo). Always defer to a project-specific deviation when one exists (see Phase 1).

## Workflow

### Phase 1: Establish Conventions

1. Read `project-management/proposals.md` for the canonical format, lifecycle, and rules.
2. Check the current project for deviations from the standard. Look in the project's `CLAUDE.md`, `AGENTS.md`, `README`, and any local proposals doc, and inspect an existing proposal in the proposals directory if one exists. A real example beats the template — match the headings, numbering, and prose style the project actually uses. If a project convention conflicts with the canonical format, follow the project.

### Phase 2: Get the Description

The description is passed as the skill's arguments. If arguments were provided, use them as the proposal's starting description. If no arguments were provided, ask the user for a one-or-two sentence description of the proposal using AskUserQuestion before continuing.

### Phase 3: Locate Directory, Prefix, and Number

1. **Directory** — find the proposals directory by checking common locations (`spec/proposals/`, `docs/proposals/`, `proposals/`). If none exists, ask the user where proposals should live using AskUserQuestion, offering the common locations as options.
2. **Prefix** — derive the project-specific token from existing proposal filenames (e.g. `HP-001-*.md` → `HP`). If there are no existing proposals, propose a short, distinguishable prefix based on the project name and confirm it with the user via AskUserQuestion (`PROJ` is permitted but discouraged when a more specific prefix fits). The prefix is fixed once chosen.
3. **Number** — scan existing proposal filenames for the highest number and use the next sequential value. Numbers are permanent and never reused. Match the zero-padding of existing files (e.g. `001` vs `01`).

### Phase 4: Gather Context

Build enough understanding to write a coherent draft:

1. Use Agent sub-tasks to scan the codebase for code, patterns, types, and conventions relevant to the proposal's domain, so the motivation and design are grounded in what exists.
2. If the description references or depends on other proposals, read them to capture dependencies and cross-proposal impact.
3. Ask the user targeted follow-up questions via AskUserQuestion to fill real gaps — motivation, scope, constraints, known design decisions, and dependencies. Ask only what you cannot reasonably infer; do not interrogate. Anything that remains genuinely undecided becomes an open design question rather than a guess.

### Phase 5: Outline & Confirm

Before writing the file, present a brief outline and confirm with AskUserQuestion:

- The proposed ID (`PREFIX-NNN`) and title
- One-line summary
- The settled vs. open design decisions you plan to record
- Any dependencies or cross-proposal impacts

Do not write until the user approves. Adjust per their feedback.

### Phase 6: Write the Proposal

Write the file to `<dir>/<PREFIX>-NNN-short-description.md` (kebab-case description), following the format from `project-management/proposals.md` (or the project's deviation):

```markdown
# PREFIX-NNN: Title

**Status:** draft
**Created:** YYYY-MM-DD
**Updated:** YYYY-MM-DD

## Dependencies

- PREFIX-NNN (if any)

## Impacts

- PREFIX-NNN — section(s) of this proposal that affect it

## Summary

Brief description of the proposal.

## Motivation

Why this change is needed.

## Design Decisions (Settled)

Decisions made with rationale.

## Design Decisions (Open)

Unresolved questions with candidate options.

## Milestones

Implementable chunks of work.

## Decision Log

Minor decisions with dates.

## References

- Related ADRs, proposals, or research
```

Rules for drafting:

- Use today's date for Created and Updated; set status to `draft`.
- Record settled decisions with rationale; leave gaps as open questions with candidate options rather than guessing.
- Omit Dependencies/Impacts entries when there are none (keep the headings only if the project does).
- Capture dependencies and cross-proposal impact per `project-management/proposals.md` — note the impacted proposal and the specific section(s) it cares about, and update the impacted proposals when warranted (prioritize this on large projects or proposal waves).

### Phase 7: Index

If this is the **first** proposal for the project (no `index.md` in the proposals directory), offer to create one per the "Proposal Index" section of `project-management/proposals.md` — a table with Proposal/Description/Status columns. If an `index.md` already exists, add a row for the new proposal and keep it consistent.

### Phase 8: Report

Summarize:

- The proposal's file path, ID, and title
- Whether it is ready for design review or has significant open questions (point to `/proposal-reviewer` for resolving open questions)
- Any dependencies or cross-proposal impacts noted
- Whether the index was created or updated

## Rules

- Create exactly one proposal per invocation, in `draft` status.
- Follow the format and rules in `project-management/proposals.md` exactly, unless the project defines its own deviation — then follow the project.
- Never invent decisions to fill gaps; unresolved questions go in Design Decisions (Open) with candidate options.
- Confirm the directory, prefix, and outline with the user before writing.
- Numbers are permanent and never reused; the prefix is fixed once chosen.
- Use today's date for Created, Updated, and any Decision Log entries.
