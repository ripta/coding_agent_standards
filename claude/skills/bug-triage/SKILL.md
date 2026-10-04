---
name: bug-triage
description: |
  Verify the oldest open bug in the project's bugs directory. Reproduce it against
  the current build, then close it if fixed, offer to fix it if simple, or offer to
  open a proposal if complex. Reconciles the bug index when a bug file is already
  closed. Works one bug per run.
model: sonnet
allowed-tools: Read, Edit, Write, Bash, Grep, Glob, AskUserQuestion
---

You verify and triage one bug per invocation, starting from the oldest open one. Work a single bug, take the matching
action, then report and stop.

Bug reports are files named `YYYYMMDD-short-name.md`, where the date is when the bug was first observed. Each carries a
status line, and the directory carries an index table with one row per bug. The project's own bug index or README
describes its format. Read that first and follow it over anything here.

## Step 1: Detect, without asking

Do all of this before any question.

1. **Bugs directory.** Check `spec/bugs/`, `docs/bugs/`, and `bugs/`. It may be a symlink into a separate specs repo.
   Follow it. If none exists, tell the user and stop.
2. **Bug index.** It is `index.md` or `README.md`, by the same rule as the "Index File Name" section of
   `${CLAUDE_SKILL_DIR}/../../project-management/tracking.md`. If both exist, stop and tell the user to consolidate
   them first. Read the index and any format notes it carries.
3. **Build and test commands.** Read the project's `CLAUDE.md`, `AGENTS.md`, and `Makefile`. Find how to build the
   project, how to run one test or one suite, and how to regenerate golden files if the project has them.
4. **Test layout.** List the test directories and note how a regression test is shaped here, such as a test function
   in a `_test` file, or an input file with golden sidecars.
5. **Proposals.** Find the proposals directory, its index, and the project's proposal prefix, as the `new-proposal`
   skill does. You need these only if a bug turns out to need a proposal.
6. **Shell tools.** Note whether the `cg_run` and `cg_run_many` MCP tools are available.

If the build command cannot be found, ask for it with AskUserQuestion before Step 3. That is the only question this
step may raise.

## Step 2: Select the oldest genuinely-open bug

1. From the index table, collect every row whose Status is `open`. Sort them oldest first by the `YYYYMMDD` filename
   prefix.
2. Walk the candidates oldest first. Open each bug file and read its own status line. The format drifts across files,
   so handle all of these:
   - `Status:` and `**Status:**`, in any casing, such as `fixed`, `Fixed`, or `Resolved`.
   - Trailing annotations, such as `fixed 2026-05-25` or a reference to the work that fixed it.
   - Compound forms, such as `Resolved (for X), Open (for Y)`. Treat it as open if any part is open.
   - `accepted` means a fix was chosen but not yet implemented. It is still open.
3. **The index can be stale.** If a candidate's file already reads as closed (`fixed`, `resolved`, or
   `not-reproducible`) while the index says `open`, update the index row to match the file. Note the reconciliation
   and keep walking. This is bookkeeping, not the run's work.
4. **Skip recently-triaged bugs.** A `Triaged:` line in any formatting, such as `**Triaged:** 2026-07-16 (...)`, records
   an earlier run that ended inconclusive. If its date is within the last month, skip the bug, note the skip, and keep
   walking. An older date no longer shields the bug.
5. The first candidate that is open in its file and not shielded is the bug you work. If none remain, report that and
   stop.

## Step 3: Verify whether it still reproduces

1. Read the whole bug file: the observed behavior, the repro, the files involved, any workaround, and any chosen or
   possible fix.
2. **Look for an existing regression test first.** Search the test directories for one that exercises this bug. Grep
   for the repro's distinctive input, the error string, or the bug's short name. If such a test exists, run just that
   test against the current build. A passing regression test is strong evidence the bug is fixed.
3. Build the project.
4. Reproduce the bug best-effort, using the exact snippet, commands, and flags from the report.
5. Shell discipline:
   - When `cg_run` is available, run commands through it. It captures stdout and stderr separately, so you never need
     redirection such as `>` or `2>&1`.
   - Run each command as its own call. Do not chain commands with `&&`, `||`, or `;`.
   - Follow any stricter rule the project's hooks enforce.
6. Classify the outcome:
   - **FIXED.** It no longer reproduces, and the behavior is now correct.
   - **STILL A BUG.** It reproduces deterministically.
   - **INCONCLUSIVE.** It is flaky, race-dependent, slow, or environment-specific, and did not reproduce
     deterministically. Never close an inconclusive bug as fixed.

## Step 4: Act on the outcome

The questions here come after verification, because they depend on its outcome. Each outcome asks at most once, in a
single AskUserQuestion call.

### FIXED: close it

1. Set the file's status to `fixed` with today's date, such as `**Status:** fixed 2026-05-25`. Add or fill a `Fixed:`
   line with the date.
2. Identify what fixed it, best-effort. Scan `git log`, the phase index, and the proposal index for the responsible
   change. Record a commit hash and subject only if you can identify it confidently. Do not guess.
3. Set the index row's Status to `fixed`.

### STILL A BUG: judge the size

A fix is **simple** when it is localized, clear, and easy to validate. The bug often already documents a chosen fix. A
fix is **complex** when it carries downstream changes, touches many files, or is hard to validate.

- **Simple: offer to fix it now.** If the bug lists several possible fixes but no chosen one, ask which approach in
  the same AskUserQuestion call. Never pick one yourself. If the user accepts:
  1. Write the regression test first, in the suite and shape the project uses. Run it and confirm it fails for the
     reason the bug describes. A test that passes before the fix does not cover the bug.
  2. Implement the fix, following the chosen approach.
  3. Run the formatter, then the regression test, then the full test suite. Regenerate golden files only through the
     project's update target.
  4. Close the bug: status `fixed` with today's date, and a short fix note naming the files changed and the observable
     behavior change. Set the index row to `fixed`.
- **Complex: offer to open a proposal.** If the user accepts:
  1. Create a `draft` proposal following `${CLAUDE_SKILL_DIR}/../../project-management/proposals.md`. Use the next
     sequential number and the project's prefix. Carry the bug's research into its Motivation and Design Decisions.
  2. Add the proposal to the proposal index.
  3. Set the bug's status to `proposed` and link the proposal, so later runs skip it. Set the index row to `proposed`.

### INCONCLUSIVE: do not close

Report what you tried and why reproduction was inconclusive. Treat the difficulty as added complexity. Offer two
options in one AskUserQuestion call: open a proposal (then mark the bug `proposed`), or append Investigation Notes to
the bug file recording what was tried. Do not leave the bug silently untouched, and do not close it.

With either choice, add or update a `Triaged:` line next to the status with today's date, such as
`**Triaged:** 2026-07-16 (not reproducible; see investigation notes)`. The bug stays open, but the next month of
runs skips it.

## Step 5: Report

Summarize concisely:

- Which bug was selected, and any index rows reconciled or bugs skipped along the way.
- The verification outcome, and how you reached it: what you built and ran.
- The action taken: closed as fixed, fix offered and its result, proposal opened, or inconclusive.

## Rules

- One bug per run. After acting on the selected bug, stop.
- Step 4 asks after verification on purpose, because what to offer depends on the outcome. This is an exception to
  the ask-once flow in `skills/README.md`. Step 1 asks only for a build command it cannot find.
- Never commit, stage, or push. Stop and let the user commit.
- Do not make a design decision on a fix alone. Ask whenever the approach is ambiguous.
- A fix always lands with a regression test that failed before it.
- Keep bug, phase, milestone, and proposal IDs out of source code, comments, and diagnostic strings, per
  `${CLAUDE_SKILL_DIR}/../../rules/work-discipline.md`. They belong in bug files, proposals, and commit messages.
