---
name: idea-intake
description: |
  Take one or more feature ideas and sort each one. Marks an idea as an
  existing feature, a planned proposal, or already captured in the ideas file.
  Otherwise researches its feasibility lightly and writes it to the ideas file,
  or asks the user when it needs clarification. Invoked as `/idea-intake
  <ideas>`. Triggers: "capture these ideas", "add this to the ideas file".
  DO NOT trigger on: a question about whether a feature exists, writing a
  proposal (use new-proposal), or filing a bug.
argument-hint: "<ideas>"
allowed-tools: Agent, AskUserQuestion, Read, Edit, Write, Bash, Grep, Glob
---

You sort a batch of ideas. You are the coordinator. Subagents classify and research one idea each. You split the input,
ask the user, check the subagents' evidence, and write the ideas file. Nobody else writes it.

The ideas file format is "Ideas" in `${CLAUDE_SKILL_DIR}/../../project-management/tracking.md`. Its status vocabulary
is under "Status Vocabularies" there. A project's own format overrides it. Read the file's intro and its existing
sections first, and match them.

## Outcomes

Every idea ends with exactly one outcome:

- `existing`: the code already does it. Evidence: a `file:line` that shows the behavior
- `planned`: a proposal covers it. Evidence: the proposal ID and its status
- `captured`: the ideas file already holds it. Evidence: the section heading. A match on an `unclear` section is
  `unclear` again instead. Its questions go to Step 7, and Step 6 rewrites that section in place. A match on an
  `infeasible` section reports that verdict and its reason
- `new`: written to the ideas file as `open`
- `infeasible`: written to the ideas file as `infeasible`, with the reason
- `delta`: something above covers only part of it. The missing part is written to the ideas file, with an
  `**Extends:**` line naming what covers the rest. The status is `open` or `infeasible`
- `unclear`: it needs the user. When the user does not answer, it is written to the ideas file as `unclear`, with its
  open questions

A proposal counts as `planned` when its status is `draft`, `designing`, `accepted`, or `deferred`. An `implemented`
proposal means the idea is `existing`: cite the code, not just the proposal. A `superseded` proposal points at its
successor, so check that one. A `rejected` or `retracted` proposal does not cover the idea. Research it as new, and cite
the proposal and the reason it was dropped in the context paragraph.

## Step 1: Detect, without asking

Do all of this before any question.

1. **Specs.** Run `python3 ${CLAUDE_SKILL_DIR}/../../scripts/proposals.py locate`, per "Lookup Rule" in
   `${CLAUDE_SKILL_DIR}/../../project-management/tracking.md`. It finds the nearest of the common locations
   (`spec/proposals/`, `docs/proposals/`, `proposals/`). When it reports several candidates, they are the components.
   Go to item 3. Otherwise its `proposals_dir` may be a symlink into a separate specs repo. Follow it. Its `index` is
   the proposals index. When the directory holds both `index.md` and `README.md`, stop and tell the user to
   consolidate them, per "Index File Name" in `tracking.md`.
2. **Ideas file.** Use the `ideas` path that `locate` reports. When it is null, the first idea to write creates
   `ideas.md` beside the proposals directory, with a one-line intro. When `locate` finds no proposals directory either,
   note that. It becomes a question in Step 3.
3. **Components.** Note whether the repo holds several components that keep their own specs. That is so when `locate`
   reports several candidates, or when the repo has a specs directory per component. Find each component's specs with
   `locate --start <a path in it>`. Each idea is then sorted against the component it changes, and written to that
   component's ideas file.
4. **Reach.** List the repos this session can read: the working directory and any added directories. An idea that
   needs a repo outside them can only be `existing` or `planned` for what is visible. The report says so.
5. **Git state.** Run `git status` in the repo that holds the ideas file. When the ideas file already has uncommitted
   changes, note it. Step 6 writes on top of them, and Step 8 does not commit the file.
6. **Commit style.** Read the specs repo's commit style, per `${CLAUDE_SKILL_DIR}/../../rules/commit-style.md`.

## Step 2: Split the input

The ideas come from the skill's arguments. When there are none, ask for them on their own with AskUserQuestion. Nothing
else can be detected without them.

1. Split the input into single ideas. A list item, a paragraph, or a sentence joined by "also" is usually one idea.
   Split an item that asks for two unrelated things.
2. Merge two items that ask for the same thing. Keep both wordings in the merged idea.
3. Give each idea a short name, and note its component when Step 1 found several.
4. Write the list to `idea-intake-run.md` in the session's scratchpad. One line per idea: its name, its text, and an
   empty outcome. Update the line as each idea finishes, so the run survives compaction.

## Step 3: Ask once, up front

Ask every question you can answer without research, in one AskUserQuestion call:

- An idea you cannot research because its meaning is unclear from the text alone
- A split or a merge from Step 2 you are not sure of
- Which component an idea belongs to, when its text does not say
- Where the ideas file goes, when Step 1 found no proposals directory

Before you ask, start Step 4's subagents for every idea that has no question. They run in the background while the
question is open. Do not hold them back.

Skip the question when there is nothing to ask. When there are more than four questions, ask the four that unblock the
most ideas. Mark the rest `unclear` now, and carry their questions to Step 7. When the user does not answer, mark each
idea it asked about `unclear` the same way, and go on. The run never stops for an answer.

## Step 4: Classify and research

Start one subagent per idea, with the `general-purpose` type and the `sonnet` model. Run at most four at once. Start the
next as each one finishes. Each subagent is read-only. It never edits a file.

The subagent knows only its brief. Put all of this in it:

- The idea's name and text, and any answer the user gave about it
- The paths to search: the code repos, the proposals directory and its index, and the ideas file. Name the component
  when there is one
- The outcome list and the proposal-status rules from "Outcomes" above, copied in full
- The order to check: code first, then proposals, then the ideas file. Stop at the first full match. A partial match
  keeps going, so the missing part can be researched
- The research bound. Search the code and the specs. Search the web only when the idea depends on an outside tool, API,
  or standard, and then for at most three queries. Do not start further subagents
- What feasibility means: whether the idea can be built in this project as it stands, what it would touch, and what
  would block it. Not whether it is worth doing
- The return shape below, verbatim

The return shape:

```text
Outcome: existing | planned | captured | new | infeasible | delta | unclear
Evidence: <file:line, proposal ID and status, or ideas heading; one per line>
Extends: <for delta only: what covers the rest>
Status: <for new, infeasible, or delta: open or infeasible>
Problem: <one paragraph>
Context: <one paragraph, citing file:line for related code>
Feasibility: <one paragraph; for infeasible, the reason and what would change it>
Questions: <for unclear only: up to two questions, each with 2-4 concrete options>
Searched: <the repos and directories searched>
```

## Step 5: Check the evidence

Check each result before you act on it.

1. Read every cited `file:line`, proposal, and ideas heading yourself. When a result cites more than five, give them to
   the `citation-verifier` agent (`coding-standards:citation-verifier` under the plugin) instead.
2. The evidence must show what the outcome claims. A `file:line` for `existing` must show the behavior, not just a name
   that matches. A proposal for `planned` must cover the idea, not just its area.
3. When the evidence fails, run the subagent once more, with the failure in its brief. When it fails again, record the
   idea as `unclear`, and say in its questions what could not be confirmed.
4. Check the results against each other. Two ideas that turn out to be the same get one entry.

## Step 6: Write the ideas file

Write each `new`, `infeasible`, and `delta` result as one `##` section, in the format from `tracking.md` or the
project's own. Write them in input order, at the end of the file. Date the `**Captured:**` line with today's date. Turn
the subagent's paragraphs into the section's prose. Keep its `file:line` citations.

Write nothing for `existing`, `planned`, or `captured`. They are reported only.

## Step 7: Ask about the unclear ones

Gather every `unclear` idea's questions into one AskUserQuestion call, up to four questions. When there are more, ask in
rounds of four, with no pause between rounds.

- Run the subagent again for each answered idea, with the answers in its brief. Then repeat Steps 5 and 6 for it. Do
  not ask about it a third time. When it comes back `unclear` again, write it as `unclear`
- When the user does not answer, write each idea as `unclear`, with its questions in the section. Do not wait. A later
  run that gets the same idea asks again

## Step 8: Commit and report

Commit the ideas file only where `${CLAUDE_SKILL_DIR}/../../rules/git-workflow.md` allows it. Name the path in the
commit. A commit by path takes the whole file, so skip the commit when Step 1 found the file already changed. Where the
commit is skipped or not allowed, leave the file and name it in the report.

Report one line per idea, in input order: its name, its outcome, and its evidence or the heading it was written under.
Then list:

- Each idea whose outcome rests on a partial view, with the repos it could not search
- Each idea left `unclear`, with its open questions
- Every bug found along the way, per `${CLAUDE_SKILL_DIR}/../../rules/found-bugs.md`

## Rules

- Only the coordinator writes the ideas file. That is what makes parallel subagents safe
- Never edit a proposal. An idea that adds to a proposal is a `delta` in the ideas file
- Never write a proposal. That is `new-proposal`'s job
- This skill has two question checkpoints, Step 3 and Step 7. That is a deliberate exception to the one-checkpoint rule
  in `${CLAUDE_SKILL_DIR}/../README.md`. Step 7's questions come from research, so they cannot be asked up front.
  Step 3 asks what it can, and Step 7 never blocks: an unanswered idea is written as `unclear`
