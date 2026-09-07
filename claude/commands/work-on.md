---
description: Plan and implement a phase milestone
argument-hint: <phase>[.<milestone>]
---

Your first action MUST be to call the EnterPlanMode tool. Do not do anything
else until you have entered plan mode. Skip this step if the session is already
in plan mode.

Once in plan mode, work on phase milestone $ARGUMENTS by following these steps.

The phase model lives in `${CLAUDE_PLUGIN_ROOT}/project-management/plans.md`.
Read it for the milestone conventions, status values, and artifact sync rules.
Always defer to a project-specific deviation when one exists.

1. Locate the phases directory. Check the common locations: `spec/phases/`,
   `docs/phases/`, `phases/`. Read its `index.md`.

2. Parse the argument. `PHASE.MILESTONE` (e.g., `207.3`) names one milestone. A
   bare `PHASE` (e.g., `207`) means the next incomplete milestone in that phase.

3. Check the phase status in the index. Stop and tell the user if the phase is
   already COMPLETE.

4. Read the phase document itself, `phase-N-*.md` in the same directory. The
   index carries only the summary table. Milestone descriptions and acceptance
   criteria live in the phase document.

5. Select the milestone. If the argument named one, stop and tell the user when
   its status is already DONE. If the argument gave only a phase number, take
   the first milestone in the table that is not DONE.

6. Read the proposal named in the phase's Scope section. `PROJ-199` means read
   `PROJ-199-*.md` in the project's proposals directory, usually
   `spec/proposals/` or `docs/proposals/`. This carries the design context for
   the work.

7. Check the proposal's status field. Only `accepted` or `scheduled` proposals
   may be implemented. Stop and tell the user for any other status. Do this even
   when the user asked for the work directly. Flag the conflict and ask before
   going further.

8. Explore the codebase to understand the files and patterns relevant to the
   milestone. Use Explore agents for this.

9. Write a plan covering:
   - Context: what problem the milestone solves and why
   - Files to modify or create
   - Implementation approach, referencing existing code and patterns to reuse
   - A breakdown into smaller tasks, where that makes implementation easier and
     debugging simpler
   - Verification: how to test the changes (specific make targets, test files)
   - Artifact sync: the phase document and phase index updates that land with
     the milestone

10. Implement once the user approves the plan.

11. Update the phase document and the phase index. Tick the milestone's
    acceptance criteria and set its status to DONE.

12. Review the change with the `reviewer` agent, named
    `coding-standards:reviewer` when installed as a plugin. Tell it the phase
    milestone and the proposal milestone it implements. Apply the fixes it
    reports; the agent reviews the working-tree diff and does not edit code.

13. Summarize the work as a commit message, following
    `${CLAUDE_PLUGIN_ROOT}/rules/commit-style.md`. Emit raw markdown. Use only
    the conversation; do not run `git diff`. Do not commit on behalf of the
    user.
