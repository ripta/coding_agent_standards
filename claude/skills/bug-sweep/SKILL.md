---
name: bug-sweep
description: |
  Triage every open bug in the project's bugs directory, one after another,
  without stopping to ask. Runs bug-triage on each bug once. Closes the fixed
  ones, fixes and commits the ones with a small fix and no design calls, and
  records an estimate on the ones that need design. Explicit-only: it commits
  on the user's behalf once the user approves the run.
argument-hint: "[build command]"
disable-model-invocation: true
allowed-tools: Read, Edit, Write, Bash, Grep, Glob, AskUserQuestion, Agent, mcp__cg__cg_run, mcp__cg__cg_run_many
---

You run `bug-triage` over every open bug, one bug at a time, until the list is done. Read
`${CLAUDE_SKILL_DIR}/../bug-triage/SKILL.md` now. Its bug format, its selection rules, and its definitions of the
outcomes, sizes, and trivial decisions apply here. Its "Unattended outcomes" section is the contract between the two
skills.

This skill is the coordinator. Subagents triage and fix. You check their work, commit it, and roll back what fails.

## What the user authorizes by approving the run

Approving the run in Step 4 is the user's explicit authorization for this run only. It relaxes these rules:

- The rule against committing on the user's behalf, in `${CLAUDE_SKILL_DIR}/../../rules/git-workflow.md`. Commit each
  bug's result as Step 5 describes, in the code repo and in the specs repo.
- The rule to confirm before moving on, in `${CLAUDE_SKILL_DIR}/../../rules/work-discipline.md`. Do not pause between
  bugs.
- The rule to ask before deciding, in `${CLAUDE_SKILL_DIR}/../../rules/decision-making.md`, for one kind of decision
  only: a design call that `bug-triage` judged trivial and the critic in Step 5 did not dispute. Every other design call
  is left to the user. Such a bug is skipped.
- The rule to leave unfinished work in the tree. Stash a failed fix by path, and list every stash in the final report.

Nothing else is relaxed. Never push, never open a PR, and never run a destructive git operation. Commit on the branch
that is checked out. Never create or switch branches. Never commit an edit this run did not make.

## Step 1: Detect, without asking

1. Do `bug-triage` Step 1: the bugs directory, its index, the build and test commands, the test layout, and the shell
   tools. Stop where it stops.
2. Find which repo holds the bugs directory. When it is a symlink into a separate specs repo, bug files commit there,
   and code commits in the project's repo. Read each repo's commit style, per
   `${CLAUDE_SKILL_DIR}/../../rules/commit-style.md`.
3. Run `git status` in each repo. Note every file that is already changed. The run never edits or commits those. When
   the bug index is one of them, stop and tell the user. Every outcome edits the index.

## Step 2: Snapshot the list

1. Walk the index as `bug-triage` Step 2 does, but keep every bug it would select instead of stopping at the first.
   Skip the ones its `Triaged:` rule shields.
2. Note each stale index row it would reconcile. Edit nothing yet. Step 4 shows them, and the run fixes them only once
   approved.
3. Write the list, oldest first, to `bug-sweep-run.md` in the session's scratchpad. One line per bug: its path and an
   empty outcome. Update the line after each bug, so the run survives compaction.

This list is the whole run. Each bug on it is visited once. Step 3 may add to it before approval, for a red baseline.
A bug filed during the run is not added. It waits for the next run. That is what makes the run end: a skipped or failed
bug stays open, but the run never picks it again.

## Step 3: Record the baseline

Build the project, then run the full suite. Keep the result. It is the baseline every later check compares against.

A red baseline is a bug, and fixing bugs is what the run is for. Do not stop for it. Work it first:

1. Match each failure to a bug on the list. A bug matches when its repro or its observed behavior names the failing
   test, the failing target, or the error. A bug the `Triaged:` rule shielded rejoins the list when it matches. A
   failure in the suite outranks the shield.
2. A failure that no listed bug covers gets a new bug file, drafted now and filed once the run is approved. Draft it
   per "Bugs" in `${CLAUDE_SKILL_DIR}/../../project-management/tracking.md`, with the failing command as its repro.
3. Move the matched bugs and the drafted ones to the front of the list, in date order. They run before every other
   bug, since a fix to one of the others cannot be judged while the suite is red.

After each of these bugs, run the full suite again and take the result as the new baseline. A red bug that ends in
anything but a landed fix leaves its failing tests in the baseline. Record them as the known-red tests in the run file.
From then on a check passes when the suite fails only those tests. A fix may never add a failure.

A build that fails is worked the same way. When its bug ends without a fix, nothing after it can be checked. Stop the
run there.

## Step 4: Approve the run

Ask once, in one AskUserQuestion call. Show the list, the stale index rows, the build and test commands, and the repos
commits will go to. When the baseline is red, show each failure and the bug that covers it, drafted ones included. Say
what approving authorizes, in a sentence for each rule above. When Step 1 found no build command and none was passed,
ask for it in the same call.

The options are `Start the sweep` and `Cancel`. Nothing after this step asks. A cancel leaves the tree as the run found
it.

Once approved, reconcile the stale rows as `bug-triage` Step 2 does. Commit them by themselves, before any bug's work.
Then file each drafted bug, with its index row, in a commit of its own.

## Step 5: Work each bug

Work the list oldest first. Run one subagent at a time, in the foreground. Two subagents in one checkout would write
over each other's edits.

Every brief that names `bug-triage` gives the absolute path of its directory. It also says that `${CLAUDE_SKILL_DIR}` in
that file means that directory, since a subagent reads the file raw.

1. **Triage.** Run `git status` in each repo and keep the output. Start a fresh `general-purpose` agent with model
   `sonnet`. Tell it to read `bug-triage/SKILL.md` and run it as `unattended <bug file> <build command>`. Tell it to
   report any other bug it finds instead of filing it.
2. **Check the edits.** Run `git status` in each repo again. Compare it with the output kept before the agent started.
   Every file that changed since then must be in the agent's report. Check that the bug file's status line and the
   index row agree. When anything else changed, stop the run. Report the stray files, and leave them in place.
3. **Act on the outcome.**
   - `closed`, `needs-design`, `inconclusive`: commit the bug file, and the index when it changed.
   - `already-closed`: the index was right after all, or another session closed the bug mid-run. Note it and move on.
   - `blocked`: stop the run.
   - `fix-candidate`: commit the bug file with its estimate. When the bug file already has a `## Sweep Attempts` entry,
     an earlier sweep failed to fix it. Treat it as `needs-design`, and name that attempt in the final report. A person
     decides whether to try again. Otherwise go to step 4.
4. **Check the estimate.** Start a `design-critic` agent. Give it the bug file with its estimate, the decisions the
   triage agent judged trivial with its reasons, and the files the fix would touch. Give it the definition of trivial
   and non-trivial from `bug-triage` Step 4. Ask it to find any decision that is non-trivial, missing, or more than a
   medium fix. Do not tell it what verdict you expect.
   - When it finds one, add it to the bug's `Estimate:` line by name. The bug is now `needs-design`. Commit the bug
     file.
   - When it finds none, go to step 5.
5. **Fix.** Run `git status` in each repo and keep the output. Start a second fresh `general-purpose` agent with model
   `sonnet`. Tell it to read `bug-triage/SKILL.md` and run it as `unattended fix <bug file> <build command>`. Do not
   resume the triage agent. Give it the triage report in its brief instead, and the known-red tests when there are any.
   Ask it to name the regression test and the files of the fix apart from the test.
6. **Check the fix.** Do step 2's check again, against the output kept in step 5. Then act on its report:
   - `fixed`: confirm the regression test yourself. Stash the fix's files apart from the test, by path, with
     `git stash push -m "bug-sweep check: <bug file name>" -- <paths>`. Run the regression test. It must fail. Then run
     `git stash pop`. When the test passes without the fix, treat the report as `test-did-not-fail`. Then run the full
     suite yourself. When it fails no test outside the known-red ones, commit. When the bug file is in the same repo as
     the code, commit the fix, its test, the bug file, and the index together. When the bugs are in a specs repo, commit
     the fix and its test in the code repo, then the bug file and the index in the specs repo. The fix commit's body
     says what the bug was and how it showed, per `${CLAUDE_SKILL_DIR}/../../rules/found-bugs.md`. When the suite fails,
     treat the report as `suite-failed`.
   - `test-did-not-fail` or `suite-failed`: roll it back, as step 7 says.
7. **Roll back a failed fix.** Stash every file the fix agent changed, by path, with
   `git stash push --include-untracked -m "bug-sweep: <bug file name>" -- <paths>`. The bug file and the index stay out
   of the stash, since they hold the triage estimate. When the fix agent set the bug's status or its index row to
   `fixed`, edit both back to `open`. Then append a `## Sweep Attempts` entry to the bug file: today's date, the report,
   each failing test, and the stash's name. Add no `Triaged:` line. Commit the bug file. Run the full suite again. When
   it does not match the baseline, stop the run.
8. **Record it.** Write the outcome and any commit subject to the run file.

A bug that a subagent reported is not on the list. File it after the bug in hand, per
`${CLAUDE_SKILL_DIR}/../../rules/found-bugs.md`. It waits for the next run.

## Stopping early

Stop the whole run on any of these:

- The build breaks.
- A commit is refused.
- A rollback leaves the suite off its baseline.
- A `git stash pop` does not apply cleanly.
- An agent edits a file it did not report.
- A subagent ends without an outcome word.

Finish the bug in hand only if that is safe. Then report as Step 6 says, and name the reason the run stopped.

## Step 6: Report

Keep it short. Give one line per bug: its file, its outcome, and its commit subject or stash name. Then list:

- Every design call the run decided, with the triage agent's reason and the critic's verdict. These are the decisions
  the user did not see. `decision-making.md` requires that the user see each one.
- Each `needs-design` bug with the decisions its estimate names. These are the bugs to take to `/bug-triage`.
- Each stash, and the bug it belongs to.
- Each known-red test, and the bug that holds it.
- Each bug filed during the run.
- Why the run stopped, when it stopped early.

## Rules

- The snapshot is the run. Never add a bug to it after approval, and never visit a bug twice. Step 3's drafted bugs
  join it before approval.
- Never shield a skipped bug with a `Triaged:` line. `bug-triage` writes one only for `inconclusive`. The user's next
  interactive run must still find the rest.
- A fix lands only with a regression test that failed before it, a full suite that fails no test outside the known-red
  ones, and a critic that found no non-trivial decision.
- This skill runs only when the user types `/bug-sweep`. Its frontmatter sets `disable-model-invocation: true`, so an
  autonomous run elsewhere cannot start it. Do not remove that field.
