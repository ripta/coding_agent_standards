---
description: (alpha) Sweep every memory directory, retier, expire, promote, and triage memories, and report rule churn
argument-hint: "[standards or specs repo paths for the churn report]"
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/memory.py:*), Read, Edit, Write, Glob, Grep, AskUserQuestion, ListAgents, SendMessage
---

This command is alpha. The user runs it by hand, about once a week, while the memory lifecycle is on trial.

Read `${CLAUDE_PLUGIN_ROOT}/rules/memory.md` first. It defines the rubric, the tiers, the instances, the thresholds,
and the format. If it cannot be read, stop and tell the user the standards are not available. Do not sweep from
memory.

Run every script as `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/memory.py`. Its docstring describes each subcommand's
output.

## 1. Report

Run `memory.py sweep`. Read the summary, then each directory's memories and problems.

## 2. Bookkeeping without asking

For each memory with `ready_pattern`, run `memory.py retier <file> pattern`. List each one in the final report. Change
nothing else without asking.

## 3. Questions

Ask through AskUserQuestion, up to four independent questions per call. Run the rounds back to back. Each question
names the memory, its directory's project, and its lesson in one line.

- **expired**: keep it, which records a `confirmation (memory-sweep)` instance, or trash it
- **ready_promote**: quote its instance lines. Offer to promote it to its `Home`, to hold it with a reason, to narrow
  its scope, or to trash it
- **contradicted**: show the contradiction and the scope as narrowed in-session. Offer to keep it or trash it
- **problems**: offer the fix for each problem that has one answer, such as an index line that names the wrong tier

Promote by writing the lesson into the home doc, in that doc's voice, then trash the memory. Ask for the target repo's
path when it is not the current repo. Then follow `${CLAUDE_PLUGIN_ROOT}/rules/guardian-requests.md` for another repo,
and `${CLAUDE_PLUGIN_ROOT}/rules/disclosure.md` for a repo of wider visibility. During the trial, a home in a shared
product repo is never written. Hold the memory instead, with the reason `trial: shared repo`.

Hold by adding `Promotion: held <today> -- <reason>` after the `Scope` line.

Trash only with `memory.py trash <file>`, never `rm`. It moves the file to a dated trash directory and drops its index
line.

## 4. Legacy triage

Triage one directory of `legacy` memories per sweep. Pick the directory with the most legacy memories, unless the
user names another in the arguments or an answer. Memories marked `untiered_new` go first. They were written since the
rule took effect, so each one is a miss to report.

Build one table: file, `type`, `suggested_tier`, a rubric home, a one-line scope, and whether it is a `HARD RULE`. A
home outside memory makes the memory a promotion candidate. Show the table in your reply, then ask for approval of the
whole table, with the rows to change. Apply the approved rows by adding the `Tier`, `Home`, and `Scope` lines and the
index prefix. Add no instances, since its expiry clock starts at `modified`.

## 5. Rule churn

Run `memory.py churn --repo <path>` for each repo in the arguments. With none, use the standards checkout when the
current repo is one, and otherwise ask for its path once.

For each section in the output, classify each commit's edit to it, from `git -C <repo> show <sha> -- <file>`:

- **narrowing**: clarifies or tightens the rule
- **exception**: adds a special case or carve-out
- **reversal**: removes or inverts earlier text. Find when the removed text was added with
  `git -C <repo> log -S '<removed line>' --format='%h %ad' --date=short -- <file>`
- **restructure**: moves or rewords without changing meaning

Skip a commit already in `~/.local/state/coding_agent_standards/rule-churn.jsonl`. Append one line per new
classification there: `{"date", "repo", "file", "section", "sha", "class"}`.

Report a section with two or more exceptions in the log as a candidate to rewrite as a principle with examples. Report
one with two or more reversals as an open question for the user. Never edit a rule here.

## 6. Finish

Run `memory.py sweep --record` once every answer is applied. It saves today as the last sweep, and logs the summary for
the trial review.

The final report lists, in this order:

1. What was retiered, promoted, held, kept, and trashed, by file and directory
2. The legacy rows migrated, and the directory triaged
3. Instance counts, and the `untiered_new` count with what it suggests
4. Churn candidates, with each section's classifications
5. Directories whose project path no longer exists, and indexes near the load cap
