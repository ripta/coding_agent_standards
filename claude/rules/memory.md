# Memory

Claude Code's auto memory is machine-local and keyed to one project. Nobody reviews it, and nothing expires it. A
correction saved there in the words of the moment becomes a rule for every later session. This rule decides what may
become a memory, and how a memory gains or loses force. Where Claude Code's own memory instructions conflict with it,
this rule wins.

The lifecycle is on trial through at least 2027-01-24. `/memory-sweep` does its bookkeeping, run by hand about once a
week.

## Before Writing a Memory

Ask in order, and stop at the first home that fits:

1. Can code enforce it: a hook, a test, a lint, or a settings key? Put it there
2. Would another developer, or the same user on another machine, need it to do the work right? It belongs to the
   project: `CLAUDE.md`, `AGENTS.md`, a README, a proposal's Decision Log, or an ADR. Use the project's spec repo when
   that is its convention
3. Does it apply to all of the user's work, not just this project? It goes in the shared standards, or in
   `~/.claude/CLAUDE.md` when it is specific to the machine
4. Only what is left goes in memory

This is a starting heuristic, not an exhaustive test. Sweeps refine it.

Save nothing for an instruction about the task at hand, or for what the repo already records. Most corrections save
nothing.

A correction asks first which rule misled you. When one did, propose the fix to that rule, at its home, and let the
user approve it. A one-case lesson whose home is a doc either gets that approval, or enters memory as an observation
whose `Home:` names the doc.

During the trial, nothing the rubric routes lands in a shared product repo, where every developer gets each change at
once. A lesson bound for one enters memory as an observation, with `Home:` naming the doc. Specs repos, the standards
repo, and user-level files may take changes during the trial.

## Tiers

- **observation**: a tentative lesson from one case. Treat it as a hint within its scope, never as a rule beyond it
- **pattern**: an observation that new instances reinforced. Apply it within its scope
- **fact**: information, not a lesson, such as a pointer to a dashboard or private context to respect. It never decays
  with silence. Remove it when it proves wrong

Every new lesson is an observation, however emphatic the correction. Emphasis is one instance said louder.

## Instances

An instance is evidence from the work. A load or a read of the memory is never one.

- **correction**: the user corrected you the way the memory says. Counts toward a pattern
- **confirmation**: the user explicitly confirmed an approach the memory describes. An "ok" is not explicit. Counts
  toward a pattern
- **case**: the memory's case came up within its scope, and you applied it with no objection. Resets the expiry clock.
  Never counts toward a pattern
- **contradiction**: the user corrected you against the memory. Never counts toward a pattern

The case that creates a memory is its first instance. Instances on the same day count as one.

Before acting on a memory, read its topic file. Record the instance then, in the same session.

## Contradictions

On a contradiction, record the instance. Then narrow the memory's scope, or demote a pattern to an observation. Never
delete a memory in-session. Memory directories are not under version control, so a deletion cannot be undone. Only
`/memory-sweep` deletes, after the user approves.

Only counting instances after the latest contradiction count toward a pattern. Narrowing restarts the count under the
new scope.

## Thresholds

- An observation becomes a pattern at 3 counting instances on 3 distinct days
- An observation with no instance of any kind for 60 days is offered for expiry
- A pattern decays only by contradiction. A fact decays only by proving wrong

You write new memories as observations and append instances. `/memory-sweep` retiers them.

## Homes and Promotion

Each memory names its home, which the rubric picks when the memory is written. The home is `memory` when step 4
applies, or the doc the lesson belongs in.

When a pattern's home is a doc, `/memory-sweep` offers to promote it. Promotion moves the lesson to that doc, then
deletes the memory. A declined promotion gets a `Promotion: held` line, which stops the offers until a new instance
arrives. A pattern whose home is `memory` stays.

A promotion to another repo follows `guardian-requests.md`. A promotion to a repo of wider visibility follows
`disclosure.md`.

## Format

A memory file keeps Claude Code's frontmatter. Its body starts with fixed lines, then the lesson, then its instances:

```markdown
Tier: observation
Home: CLAUDE.md "Committing"
Scope: commits at the end of a schedule-proposal run in this repo; not pushes, and not other repos

Commit finished work by path when the run ends.

## Instances

- 2026-11-10 correction (schedule-proposal): left the edits uncommitted; the user asked three times to commit
- 2026-11-12 case (proposal-cleanup): committed by path at the end, with no objection
```

- `Tier` is `observation`, `pattern`, or `fact`
- `Home` is `memory`, or the doc and section the lesson belongs in
- `Scope` says where the lesson applies, and where it does not
- An optional `Promotion: held <date> -- <reason>` line follows `Scope`
- Each instance is `- <YYYY-MM-DD> <kind> (<context>): <case>`. The context names the kind of task, such as a skill or
  an activity
- A fact needs no instances

Keep the tier and instances in the body. Claude Code writes the frontmatter, and may not keep keys it did not write.

The `MEMORY.md` line starts its hook with the tier and a short scope:

```markdown
- [Commit at run end](commit-at-run-end.md) — (observation; schedule-proposal commits) commit by path when the run ends
```

The index loads every session, and topic files load only on demand. The index is where a session sees how firm a
memory is and where it applies.

## Legacy Memories

A memory with no `Tier` line predates this rule. Until `/memory-sweep` triages it:

- A `reference`, `user`, or `project` memory is a fact
- A `feedback` memory is a hint within its evident scope
- A memory marked "HARD RULE" keeps its force

When you act on a legacy memory, leave it as it is. The sweep migrates it with the user.
