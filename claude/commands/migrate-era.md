---
description: Migrate a project's proposals and phases to era 3, after you approve the plan
argument-hint: "[specs dir]"
---

Start by calling the EnterPlanMode tool, before any other action. Skip this
step if the session is already in plan mode.

Migrate this project to era 3 by following
`${CLAUDE_PLUGIN_ROOT}/project-management/migration.md`. The eras and their
markers live in `eras.md`, and the era 3 rules in `proposals.md` and
`plans.md`, all in the same directory. Read all four. If any cannot be read,
stop and tell the user the standards are not available. Do not migrate from
memory.

1. Find the specs directory: the argument when given, else `spec/` or `docs/`.
   It may be a symlink into a separate specs repo. Follow it.

2. Run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/detect_era.py --specs-dir <dir>
   --project-root <project root>`. When it reports era 3, tell the user there
   is nothing to migrate, and stop.

3. Work through the guide's Steps 2 through 7 in plan mode, reading and
   planning only. Ask the user, via AskUserQuestion, every question the guide
   leaves to them: the milestone mapping, disagreements between phases and
   proposals, revisit hooks for deferred proposals, statuses outside the
   vocabulary, and what to retire. Ask them together where you can.

4. Write the plan: every file to create or edit, every proposal's new
   milestones with their statuses, every amendment, the full `queue.md` and
   `history.md`, and everything to retire. Call ExitPlanMode. That approval is the only gate.

5. Apply the plan. Then follow the guide's Step 8, and report what the checks
   say.

6. Summarize the migration as a commit message for each repo it touched,
   following `${CLAUDE_PLUGIN_ROOT}/rules/commit-style.md`. Do not commit on
   behalf of the user.
