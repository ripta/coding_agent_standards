---
name: promote-proposal
description: |
  Promote an accepted proposal (PROJ-NNN) to a new implementation phase.
  Spec-only: creates the phase document and updates the phase index, the proposal,
  and the proposal index. No code planning or implementation.
  Invoked as `/promote-proposal PROJ-NNN`.
model: sonnet
allowed-tools: AskUserQuestion, Read, Write, Edit, Glob, Grep, Bash
---

You promote one proposal to a new implementation phase. This is spec-only. You do not plan code, scan the codebase, or
implement anything. Your only artifacts are phase documents, the phase index, the proposal, and the proposal index.

The phase model lives in `${CLAUDE_SKILL_DIR}/../../project-management/plans.md`. Metadata, status vocabularies, and
milestone references live in `${CLAUDE_SKILL_DIR}/../../project-management/tracking.md`. The proposal format lives in
`${CLAUDE_SKILL_DIR}/../../project-management/proposals.md`. All three are bundled alongside this skill. They are the
only source for the formats, and this skill does not carry its own copy. Always defer to a project-specific deviation
when one exists.

## Inputs

The skill's argument is a proposal identifier such as `PROJ-033`. If it is missing or malformed, ask for it with
AskUserQuestion, on its own, before anything else. Nothing below can be detected without it.

## Workflow

### Step 1: Load the standards

Read `plans.md`, `tracking.md`, and `proposals.md` from `${CLAUDE_SKILL_DIR}/../../project-management/`. If any cannot
be read, stop and tell the user this skill is installed without its standards. Do not promote from memory.

Then check the project for deviations. Look in its `CLAUDE.md`, `AGENTS.md`, and any local planning doc. Read one or two
existing phase documents. A real phase document beats the template, so match the headings and prose style the project
uses. If a project convention conflicts with the standard, follow the project.

### Step 2: Locate and validate, without asking

Do all of this before any question.

1. **Directories.** Find the proposals and phases directories (`spec/proposals/` and `spec/phases/`, or the `docs/`
   equivalents). Either may be a symlink into a separate specs repo. Follow it.
2. **Indexes.** Each directory's index is `index.md` or `README.md`. Use whichever exists. If both exist, use the one
   whose table lists the proposals or phases. Never hard-code either name.
3. **Proposal.** Find `<ID>-*.md` in the proposals directory. If none exists, tell the user and stop. Read it and
   capture the title from the `# PROJ-NNN: Title` heading, `**Status:**`, `**Tradeoffs:**` if present, Dependencies,
   Summary, Motivation, Design Decisions (Settled), Design Decisions (Open), Milestones, any acceptance criteria, and
   the Decision Log.
4. **Validate.** Stop and report the failed check if any of these is true:
   - The proposal's `**Status:**` is anything other than `accepted`. The valid values are in `tracking.md` "Status
     Vocabularies".
   - The proposal's row in the proposal index shows a status other than `accepted`.
   - Design Decisions (Open) contains any item. An empty or absent section is fine. Route the user to
     `proposal-reviewer`.
   - The proposal ID already appears in the phase index. Name the phase or phases that hold it.
5. **Phase state.** Read the phase index. Record the highest phase number, every `IN PROGRESS` phase, and every
   `PLANNED` phase. Note any status outside the standard vocabulary (such as `SUPERSEDED` or `CANCELLED`). Treat those
   rows as fixed, like `COMPLETE` ones.
6. **Mode feasibility.** Work out which promotion modes (Step 3) are possible:
   - Append is always possible.
   - Next-after-in-progress and preempt need an `IN PROGRESS` phase. Each also needs every phase numbered above the
     insertion point to be `PLANNED`, because only `PLANNED` phases may be renumbered. If any other row sits above it,
     the mode is impossible.
7. **Dependencies.** Map each `PROJ-NNN` in the proposal's Dependencies to the phase or phases whose Proposal column
   names it. A proposal split across several phases maps to all of them. A dependency with no phase yet cannot be
   written as `Phase X`. Hold it for Step 3.
8. **Milestones and criteria.** Note whether the proposal has a Milestones section. Note whether each acceptance
   criterion it states can be traced to exactly one proposal milestone. Note any Settled decision that defers a
   question to a named proposal milestone.

Report what you found in a few lines before asking anything.

### Step 3: Ask once, up front

Make a single AskUserQuestion call. Every question the promotion needs goes in that one call. Skip any question the
request or Step 2 already answered.

- **Confirm and mode.** "Promote `PROJ-NNN: <title>` to a new phase, and how?" Always ask. Creating a proposal is not
  promoting it, and `plans.md` requires an explicit request. Offer each mode Step 2 found possible, plus a "Do not
  promote" option. Name the impossible modes and say why. When nothing is in progress, say that append is the only
  mode. When several phases are `IN PROGRESS`, offer a separate preempt option for each.
  - **(a) Append.** The new phase is `max_phase + 1`. No other phase changes.
  - **(b) Next-after-in-progress.** The new phase goes right after the highest `IN PROGRESS` phase. Every `PLANNED`
    phase above it moves up by one.
  - **(c) Preempt with split.** The chosen `IN PROGRESS` phase keeps only its `DONE` milestones and becomes `COMPLETE`.
    The promoted proposal becomes the next phase. The preempted phase's remaining milestones move to a continuation
    phase after the promoted one. Every `PLANNED` phase above the preempted phase moves up by two.
- **Deployed.** For each mapped dependency phase, ask whether this phase needs it running in production. `plans.md`
  says only the user can confirm a deployment. Ask in one multi-select question.
- **Unscheduled dependencies.** If a dependency proposal has no phase, ask whether to proceed. The phase's Dependencies
  line cannot name a proposal.
- **Missing milestones.** If the proposal has no Milestones section, or a criterion cannot be traced to one milestone,
  ask whether to write a placeholder or stop so the user can fix the proposal. Never invent milestones or criteria.

Four questions is the cap. A question whose answer depends on the mode, such as the continuation subtitle, is not
asked here. Propose a default for it in the Step 4 layout instead.

### Step 4: Compute the layout and confirm

Compute the following from the chosen mode:

- The new phase number, and a slug in the style of existing filenames, such as
  `phase-22-multi-round-trip-approval.md`.
- Each `(old → new)` renumber. Only `PLANNED` phases move.
- For mode (c): the preempted phase's kept milestones (`DONE` only). The continuation phase's milestones, renumbered
  from `.1`. A continuation title, `<Original Title> — <Subtitle>`, with a proposed subtitle the user may change.
- For mode (c): every milestone that will move but is `IN PROGRESS` or has a ticked criterion. Surface each one. The
  user decides whether its partial work counts as a kept `DONE` milestone or restarts in the continuation phase.
- Whether a large proposal should span more than one phase. Split only along proposal milestone boundaries.

Show the user the full plan: every file to create, rename, or edit, every new phase number, and every renumber. This is
the one approval gate. For mode (c), it is also where the user may add rework milestones for the continuation phase.
Take only the rework rows the user supplies. Do not write until the user approves.

### Step 5: Renumber `PLANNED` phases, highest first

Skip this step in mode (a). Otherwise work from the highest number downward, so no step collides with an existing
file. For each `(old → new)`:

1. Rename the file, keeping the slug. When the phases directory is in a git work tree, run `git mv` from inside that
   tree, since a symlinked specs directory belongs to a different repo. Otherwise use `mv`.
2. Update the `# Phase N: ...` heading.
3. Update every milestone number in the Milestones table, such as `22.1` → `23.1`.
4. Update every `### Phase N.M` heading under Acceptance Criteria.
5. Update the phase's row in the phase index, and its Pending Phases entry.

Then grep the phases directory for each old number. Update every `**Dependencies:**` line and every prose reference that
named a renumbered phase. Do this once, after all renames, mapping old to new in a single pass, so a reference is never
renumbered twice.

### Step 6: Mode (c): split the preempted phase

1. In the preempted phase document, keep only the `DONE` milestone rows. Keep only their `### Phase N.M` acceptance
   sections. Set `**Status:**` to `COMPLETE`. Leave the title, Goal, Problem Statement, and Design Decisions alone. Do
   not add a "Part N" decorator.
2. Update its phase index row to `COMPLETE`, with progress `kept/kept`, such as `1/1`. Remove it from Pending Phases if
   it is listed there.
3. Create the continuation phase document from the same skeleton as Step 7. It implements the same proposal.
   - Copy the Goal, Problem Statement, and Design Decisions from the preempted phase.
   - Move the not-`DONE` milestone rows across, renumbered from `.1`. Keep their Proposal column values. Set every
     moved row to `NOT STARTED`, since the continuation phase is `PLANNED` at `0/N`.
   - Move their acceptance sections across, renumbered to match. Apply the user's Step 4 decision to any ticked
     criterion. Never untick a box silently.
   - Append any rework milestones the user supplied in Step 4.
   - Its Dependencies include the promoted phase.
4. Check every other phase that depended on the preempted phase. Ask the user at the end, in the report, whether it
   now depends on the continuation instead. Do not rewrite it yourself.

### Step 7: Write the promoted phase document

Write `<phases dir>/phase-<N>-<slug>.md` in the "Phase Document Format" from `plans.md`. Fill it from the proposal as
follows.

- **Title.** The proposal title.
- **`**Goal:**`.** One sentence from the proposal Summary.
- **`**Status:**`.** `PLANNED`.
- **`**Complexity:**`.** `LOW`, `MEDIUM`, or `HIGH`, judged from the milestone count and the proposal's Risks.
- **`**Dependencies:**`.** The mapped phases from Step 2, as `Phase X`. Add `(deployed)` only where the user said so in
  Step 3. Write `None` when there are none. Never write a proposal ID here.
- **`**Tradeoffs:**`.** Copy it from the proposal when present, since a phase inherits it. Otherwise omit the line.
- **Scope.** `Implements: PROJ-NNN.` When the proposal spans several phases, name the milestones this phase covers,
  such as `Implements: PROJ-NNN M1–M3.`
- **Problem Statement.** Condense the proposal's Motivation. Keep it user-facing.
- **Design Decisions.** Point at the proposal's Design Decisions (Settled) rather than restating them. Name the few
  decisions that shape the milestones.
- **Milestones.** One row per proposal milestone, in order. The Milestone column is `N.1`, `N.2`, and so on. These are
  phase-local and do not inherit the proposal's numbers. The Proposal column names the source as `PROJ-NNN M1`. Every
  Status is `NOT STARTED`. When a Settled decision defers a question to a proposal milestone, the implementing row or
  its criteria must name that question.
- **Acceptance Criteria.** One `### Phase N.M` section per milestone. Place each proposal criterion under the milestone
  it traces to. Write each criterion as a checkbox. If the user chose placeholders in Step 3, write one placeholder line
  in that section saying the criteria are still to be defined.
- **Tracking Artifacts.** `plans.md` requires every phase document to list the artifacts it updates. Use this shape,
  with the real paths:

  ```markdown
  ## Tracking Artifacts

  These are updated as the phase progresses.

  - This phase document: milestone statuses, then the phase status.
  - `<phases dir>/<index>`: the status row, the progress count, and the Pending Phases section.
  - `<proposals dir>/PROJ-NNN-<slug>.md`: status flips to `implemented` when the phase completes.
  - `<proposals dir>/<index>`: the PROJ-NNN status column.
  ```

  Add a line for any other proposal whose Impacts section names this one.

Do not add Implementation, Files to Modify, or Changes Required sections. Do not pre-fill implementation detail that
the proposal does not contain.

### Step 8: Update the phase index

Insert a row for each new phase in numeric order:

```text
| <N> | PROJ-NNN | <Phase Title> | PLANNED | 0/<milestone count> |
```

Add each new phase to the Pending Phases section. Create the section if the index lacks it. Match the existing entry
format, such as `- Phase N: Title (PROJ-NNN)`. Pending Phases may be ordered by priority rather than by number. In
modes (b) and (c), put the promoted phase first, then the continuation phase. In mode (a), put it last.

If the user proceeded past an unscheduled dependency in Step 3, record it in the promoted phase's Pending Phases entry,
such as `(waits on PROJ-NNN, not yet scheduled)`. `tracking.md` puts scheduling consequences in the phase index.

### Step 9: Update the proposal and the proposal index

In the proposal:

- Change `**Status:** accepted` to `**Status:** scheduled`.
- Set `**Updated:**` to today's date.
- Add a Decision Log entry: `- YYYY-MM-DD: Promoted to Phase N.` Name every phase when the proposal spans several.
  `tracking.md` allows a Decision Log to name a phase, because the entry records history.

In the proposal index, change the proposal's Status column from `accepted` to `scheduled`.

### Step 10: Report

Summarize:

- The proposal promoted, and the mode chosen.
- Each new phase, with its number, title, and file.
- Each renumber, as `old → new`.
- For mode (c): the preempted phase's kept milestone count, and the continuation phase.
- Every file created, renamed, or edited.
- The status flip, `accepted → scheduled`, in the proposal and the proposal index.
- Anything left for the user, such as placeholder criteria or phases that depended on a preempted phase.

## Rules

- Spec-only. No code reads, no Agent sub-tasks for codebase exploration, and no planning beyond what the proposal
  contains.
- Never invent milestones or acceptance criteria. If the proposal lacks them, ask.
- Detect before asking, then ask once. The layout confirmation in Step 4 is the only later checkpoint. Write nothing
  before the user approves it.
- Never renumber a phase that is not `PLANNED`. If a mode would require it, that mode is unavailable.
- Renumber highest-first. Rewrite cross-references in one pass after all renames.
- Use `git mv` for renames inside a git work tree, so history follows the file.
- Treat any non-`accepted` proposal status as a hard stop. Do not change it to make promotion possible.
- Treat any open design question as a hard stop, and route the user to `proposal-reviewer`.
- Phase dependencies name phases, never proposals. Only the user decides `(deployed)`.
- Use the status values from `tracking.md`. Phases are `PLANNED`, `IN PROGRESS`, or `COMPLETE`. Milestones are
  `NOT STARTED`, `IN PROGRESS`, or `DONE`.
