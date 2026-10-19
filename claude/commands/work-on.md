---
description: Plan and implement a proposal milestone
argument-hint: <PROJ-NNN> [M<n>] [--review-loop]
model: opusplan
---

Start by calling the EnterPlanMode tool, before any other action. Skip this
step if the session is already in plan mode.

Once in plan mode, work on the proposal milestone in $ARGUMENTS by following
these steps.

The queue and the rules for working a milestone live in
`${CLAUDE_PLUGIN_ROOT}/project-management/plans.md`. The milestone format,
status values, and amendment rules live in
`${CLAUDE_PLUGIN_ROOT}/project-management/proposals.md`. Read both. Always
defer to a project-specific deviation when one exists.

`${CLAUDE_PLUGIN_ROOT}/scripts/proposals.py` reads the queue and the
proposals. Run it with `python3`, and pass `--proposals-dir` the proposals
directory from step 1. Use it rather than parsing the files by hand.

Whenever a choice comes up, in the plan or during implementation, build the
options by the "Choosing Options" section of
`${CLAUDE_PLUGIN_ROOT}/rules/decision-making.md`. Apply an override only when
the user stated one this session, or the proposal carries a `**Tradeoffs:**`
field.

1. Locate the proposals directory. Check the common locations:
   `spec/proposals/`, `docs/proposals/`. It holds `queue.md`. When it sits in
   a symlinked specs repo, find that repo with
   `git -C <proposals dir> rev-parse --show-toplevel`. Proposal edits are
   reviewed there. Run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/detect_era.py
   --specs-dir <specs dir>`. If it reports an era other than 3, the project
   has not finished migrating to era 3. Stop and tell the user to migrate
   first, with `/migrate-era`.

2. Parse the argument. `PROJ-NNN M3` names one milestone. A bare `PROJ-NNN`
   means its next unfinished milestone in queue order. A `--review-loop` flag
   changes only step 12.

3. Run `proposals.py row PROJ-NNN [M3]`. It finds the queue row that names the
   milestone and reports whether it is ready. Stop and tell the user when:
   - The milestone is in no queue row. It is not scheduled. Schedule it only
     when the user asks, per `plans.md` "Scheduling a Proposal"
   - The milestone is already `DONE` or `DROPPED`
   - The proposal is not `accepted`. Do this even when the user asked for the
     work directly. Flag the conflict and ask before going further
   - An earlier row of the proposal, or an earlier milestone in this row, is
     unfinished. Name it
   - A dependency is not met. Name each one with its state and reason. A
     `blocked` one needs the user, and a `Replaced by` hint names what to wait
     on instead. A `confirm` one is a `(deployed)` dependency: ask the user
     whether it runs in production

4. Read the proposal. Its Design Decisions carry the design. The milestone's
   bullets are its checks. Read the design documents and ADRs it cites.

5. Explore the codebase to understand the files and patterns relevant to the
   milestone. Use Explore agents for this.

6. Write a plan covering:
   - Context: what problem the milestone solves and why
   - Files to modify or create
   - Implementation approach, referencing existing code and patterns to reuse
   - Completeness: the root cause the milestone addresses, and whether the
     approach fixes it fully. Picking an approach is a choice, even when only
     one seems obvious. If a more complete approach exists, name what this one
     leaves undone. Then ask the user to choose before you call ExitPlanMode.
     Count any investment the touched code needs, as defined in
     `decision-making.md`
   - A breakdown into smaller tasks, where that makes implementation easier and
     debugging simpler
   - Verification: how to test the changes (specific make targets, test files)
   - Proposal updates: the milestone status, the As built block, and any
     amendment the plan already expects

7. Once the user approves the plan, set the milestone's status to
   `IN PROGRESS`.

8. Implement it.

9. Update the proposal, per `plans.md` "Working a Milestone":
   - Set the milestone's status to `DONE`, and write its As built block by the
     rules in `proposals.md` "As Built"
   - Amend any decision or milestone text the work changed, narrowed, or
     corrected, per `proposals.md` "Amending a Proposal". Never leave the
     divergence only in the Decision Log
   - Do not write `implemented` yet. Step 12 does that after the review passes

10. Run `proposals.py check`. Fix every finding on this proposal.

11. Run `proposals.py freeze`. Its hunks with origin `row` are edits this work
    made, and uncommitted edits count as this work's own. Undo each one the
    freeze does not allow. The exception is a correction of fact: when the
    proposal's `corrections_logged` is above zero, leave its text hunks for the
    reviewer to judge in step 12. Leave a hunk with origin `other` or
    `unknown` alone, and name it to the user in your response.

12. Review the change with the `reviewer` agent, named
    `coding-standards:reviewer` when installed as a plugin. Tell it the
    proposal milestone, the proposal file, and the specs repo when it differs
    from the code repo. Its proposal edits are the specs repo's working-tree
    diff. The agent reviews the working-tree diff and does not edit code. In
    the same message, spawn the `adr-impact` agent
    (`coding-standards:adr-impact`) on the working-tree diff, and tell the
    reviewer it runs beside it. When `adr-impact` is not available, skip it and
    do not tell the reviewer. This review is the end of the run, so ask the
    reviewer for an ADR review too. Address what they report:
    - Fix comment-craft, style, and plan-conformance findings directly. The
      exception is a shortcut the plan did not approve. Confirm it in the code
      first, then fix it the way the plan specified.
    - Apply `CONFIRMED` correctness and security findings.
    - Verify a `PLAUSIBLE` finding before acting on it. Trace the failure it
      describes. Fix it only if the trace confirms it.
    - Amend the proposal for every amendment finding, as in step 9.
    - Never act on a finding whose disposition is `user`. Report it to the
      user. It concerns an edit this work did not make.
    - Treat an ADR conflict like a correctness finding of the same verdict.
      When honoring the ADR would change the approved plan, stop and ask the
      user. Mention an `ADVISORY` conflict in your response. It never blocks.
    - Check each uncovered decision `adr-impact` reports against the bar in
      the "What Earns an ADR" section of
      `${CLAUDE_PLUGIN_ROOT}/project-management/design.md`. Record each that
      passes as `Undecided` in the originating proposal's Decision Log, per
      its "Recording ADR Candidates" section. Skip one the log already holds.
      Mention them once, in your final response, per its "Listing ADR
      Candidates" section, and name the proposal file as changed. Do not write an ADR unless the user asks
    - Push back in your response on any finding you disagree with, and say
      why. Do not apply a finding blindly.

    Re-run the project's checks only when the fixes changed code. A
    comment-only change may skip the tests, but still run the formatter.

    Review is a single pass by default. If `$ARGUMENTS` includes
    `--review-loop`, send the same reviewer a follow-up after applying fixes.
    When the fixes touched an ADR conflict, also run a fresh `adr-impact`.
    Repeat until neither reports actionable findings.

    Once the review passes, finish the proposal:
    - When `row` reported this as the proposal's last unfinished milestone, set
      the proposal to `implemented` and update the proposal index
    - When it was the last milestone in its row, move the row above every
      unfinished row in `queue.md`
    - Run `proposals.py check` once more

13. Summarize the work as a commit message, following
    `${CLAUDE_PLUGIN_ROOT}/rules/commit-style.md`. Emit raw markdown. Use only
    the conversation; do not run `git diff`. Before emitting it, check the
    message against `commit-style.md`, including Forbidden Openers. When the
    specs live in a separate repo, say that the proposal edits there need
    their own commit. Do not commit on behalf of the user.
