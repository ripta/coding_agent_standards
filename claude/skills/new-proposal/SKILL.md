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

You create a single new proposal in `draft` status, following the project's proposal format. You gather just enough
context to write a coherent draft, leave genuinely undecided questions as open design questions rather than guessing,
and confirm the structure with the user before writing.

The canonical format and rules live in `${CLAUDE_SKILL_DIR}/../../project-management/proposals.md`, bundled alongside
this skill. That file is the only source for the format; this skill does not carry its own copy. Always defer to a
project-specific deviation when one exists (see Step 1).

## Workflow

### Step 1: Establish Conventions

1. Read `${CLAUDE_SKILL_DIR}/../../project-management/proposals.md` for the canonical format, lifecycle, and rules. If
   that file cannot be read, stop and tell the user this skill is installed without its standards; do not draft a
   proposal from memory.
2. Check the current project for deviations from the standard. Look in the project's `CLAUDE.md`, `AGENTS.md`, `README`,
   and any local proposals doc, and inspect an existing proposal in the proposals directory if one exists. A real
   example beats the template — match the headings, numbering, and prose style the project actually uses. If a project
   convention conflicts with the canonical format, follow the project.

### Step 2: Get the Description

The description is passed as the skill's arguments. If arguments were provided, use them as the proposal's starting
description and move on.

If no arguments were provided, ask for a one-or-two sentence description using AskUserQuestion, on its own, before
anything else. The description is a prerequisite, not a question: nothing below can be detected without knowing the
subject. Every other question waits for the single call in Step 4.

### Step 3: Detect, without asking

Do all of this before any question. Most answers are already on disk.

1. **Directory** — find the proposals directory by checking common locations (`spec/proposals/`, `docs/proposals/`,
   `proposals/`).
2. **Prefix** — derive the project-specific token from existing proposal filenames (e.g. `HP-001-*.md` → `HP`). The
   prefix is fixed once chosen.
3. **Number** — scan existing proposal filenames for the highest number and use the next sequential value. Numbers are
   permanent and never reused. Match the zero-padding of existing files (e.g. `001` vs `01`).
4. **Index** — note whether the proposals directory already has an index, `index.md` or `README.md`. If it has both,
   stop and tell the user to consolidate them first, per the "Index File Name" section of
   `${CLAUDE_SKILL_DIR}/../../project-management/tracking.md`.
5. **Codebase** — use Agent sub-tasks to scan for code, patterns, types, and conventions relevant to the proposal's
   domain, so the motivation and design are grounded in what exists.
6. **Related proposals** — if the description references or depends on other proposals, read them to capture
   dependencies and cross-proposal impact.

Report what you found in a few lines before asking anything.

### Step 4: Ask once, up front

Make a single AskUserQuestion call. Every question the proposal needs goes in that one call, before you draft anything.
Do not ask, draft, then ask again.

Skip any question the request or Step 3 already answered. If detection answered everything, ask nothing and go straight
to the outline.

Ask only from this set:

- **Directory.** Only when no proposals directory exists. Offer the common locations as options.
- **Prefix.** Only when there are no existing proposals to derive it from. Propose a short, distinguishable prefix based
  on the project name (`PROJ` is permitted but discouraged when a more specific prefix fits).
- **Index.** Only when this is the first proposal and no index exists. Ask whether to create one.
- **Gaps.** The targeted follow-ups that fill real holes — motivation, scope, constraints, known design decisions,
  dependencies. Ask only what you cannot reasonably infer; do not interrogate.

Anything still undecided after this call becomes an open design question, not a guess. Four questions is the cap. When
the gaps exceed what fits, ask the ones that most shape the design and record the rest as open questions.

### Step 5: Outline & Confirm

This is the one approval gate. Before writing the file, present a brief outline and confirm with AskUserQuestion:

- The proposed ID (`PREFIX-NNN`) and title
- One-line summary
- The settled vs. open design decisions you plan to record
- Any dependencies or cross-proposal impacts

Do not write until the user approves. Adjust per their feedback.

### Step 6: Write the Proposal

Write the file to `<dir>/<PREFIX>-NNN-short-description.md` (kebab-case description), following the "Proposal Document
Format" section of the canonical standard read in Step 1, or the project's deviation where one exists.

Rules for drafting:

- Use today's date for Created and Updated; set status to `draft`.
- Record settled decisions with rationale; leave gaps as open questions with candidate options rather than guessing.
- Populate the Risks section per the standard's "Risks" section: each risk carries a likelihood, an impact, and a
  mitigation or explicit acceptance. Flag one-way-door decisions (migrations, published contracts, wire formats) as
  risks. "None identified" requires a stated reason.
- Omit Dependencies/Impacts entries when there are none (keep the headings only if the project does).
- Number milestones as plain ordinals from 1. They carry no status column; execution status lives in the phase that
  implements them.
- Capture dependencies and cross-proposal impact per `${CLAUDE_SKILL_DIR}/../../project-management/proposals.md` — note
  the impacted proposal and the specific section(s) it cares about, and update the impacted proposals when warranted
  (prioritize this on large projects or proposal waves).

### Step 7: Index

If an index already exists, add a row for the new proposal and keep it consistent.

If this is the **first** proposal for the project, act on the index answer from Step 4. Create the index per the
"Proposal Index" section of `${CLAUDE_SKILL_DIR}/../../project-management/proposals.md` — a table with
Proposal/Description/Status columns. Do not ask again here.

### Step 8: Report

Summarize:

- The proposal's file path, ID, and title
- Whether it is ready for design review or has significant open questions (point to `/proposal-reviewer` for resolving
  open questions)
- Any dependencies or cross-proposal impacts noted
- Whether the index was created or updated

## Rules

- Create exactly one proposal per invocation, in `draft` status.
- Follow the format and rules in `${CLAUDE_SKILL_DIR}/../../project-management/proposals.md` exactly, unless the project
  defines its own deviation — then follow the project.
- Never invent decisions to fill gaps; unresolved questions go in Design Decisions (Open) with candidate options.
- Detect before asking, then ask once. Directory, prefix, index, and design gaps share a single AskUserQuestion call in
  Step 4. The outline in Step 5 is the only later checkpoint.
- Numbers are permanent and never reused; the prefix is fixed once chosen.
- Use today's date for Created, Updated, and any Decision Log entries.
