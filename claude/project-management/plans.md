# Plans (The Queue)

A project builds its work from one ordered queue. Each queue row names a range of one proposal's milestones. The queue's
order is the build order, independent of proposal number and acceptance date. Execution status lives on the proposal
milestones themselves. See `proposals.md` "Milestones".

Phase documents and the phase index belong to earlier eras. A project that still has them keeps them as history. See
`eras.md`.

## Rules

- A queue row names one contiguous range of one proposal's milestones, such as `PROJ-004 M3-M5`. A milestone appears in
  at most one row
- Unfinished rows belong only to `accepted` proposals. Finished rows stay in `history.md`, whatever the proposal's
  status becomes. See "The Queue File"
- A milestone's ID is permanent once any queue row names it, in `queue.md` or `history.md`. Rework, or work split out
  of a milestone, becomes a new milestone with the next free number
- Milestones are units of implementation work only. Design work (a design spike, an ADR, a research write-up) is not a
  milestone. Record its result in the proposal's Design Decisions, the ADR, or the research document
- Refactoring is part of the work. If a feature would be substantially cleaner after restructuring nearby code, include
  that work in the milestone's checks rather than deferring it or working around it

## Before Starting Work

- Before implementing a proposal, check its status field. Only an `accepted` proposal may be implemented
- If the status is anything else, stop and tell the user. This applies even if the user asks you to implement it. Flag
  the status conflict and ask for confirmation to change the status first
- A detailed plan does not imply the proposal has been accepted. The status field is the sole source of truth
- Implement only a milestone that a queue row names. A milestone with no row is not scheduled. Stop and tell the user
- Creating or accepting a proposal is not scheduling it. Schedule a proposal only when the user explicitly asks. A plan
  that lists milestones does not authorize scheduling. It is a design sketch until the user says to schedule it

## Scheduling a Proposal

Scheduling adds queue rows for an `accepted` proposal's milestones. The user picks where the rows go.

1. Add one row per contiguous range the user wants built together. Usually that is one row for the whole proposal
2. Place each row at the position the user picks. The queue's order is the build order
3. Fill each row's depends-on cell with the scheduling dependencies it has, and its note with any reason worth keeping
4. Do not change the proposal's status. Whether a proposal is scheduled is read from the queue

## Choosing What to Schedule

When the user asks to schedule without naming a proposal, tooling recommends candidates. It never picks for the user.
The user's choice is the explicit request "Before Starting Work" requires.

A candidate is an `accepted` proposal with a milestone that is not finished and that no queue row names. Each candidate
falls into one tier:

1. **Ready.** It has no open design question. Every proposal its Dependencies section names is `implemented` or has
   queue rows
2. **Waiting.** It has no open design question. A dependency is `accepted` but has no queue rows. That dependency is
   scheduled first, or ahead of it in the same batch
3. **Not schedulable.** It has an open design question, which goes to `proposal-reviewer`. Or a dependency is neither
   `implemented` nor `accepted`. Or scheduling would refuse it for another reason, such as an unscheduled milestone
   between scheduled ones

Within a tier, candidates are ordered by these signals, in turn:

- **Unblocks.** How many live proposals depend on it, directly or through others. Foundational work comes first
- **Fixes a bug.** A proposal that cites a bug file, such as `spec/bugs/<file>.md`, comes before one that cites none
- **Age.** An older `**Created:**` date comes first. Accepted work drifts from the code the longer it waits

The order is a recommendation. Each candidate carries a one-line reason, drawn from its Motivation, so the user can
overrule the order. When the user picks several, they are scheduled in dependency order, whatever order they were
picked in. `scripts/proposals.py candidates` in the plugin computes the tiers and the order.

## The Queue File

The queue lives in two files beside the proposal index in the proposals directory. `queue.md` holds the unfinished
rows, in the order they will be built. `history.md` holds the finished rows, in the order they were built. Read
together, history first, they are one queue. Every rule here that says "a queue row" means a row in either file.

`queue.md` holds one table. An optional `## Other proposals` section below the table names where other projects'
proposals live:

```markdown
# Queue

| Milestones | Depends on | Note |
|------------|------------|------|
| PROJ-002 M1-M3 | None | |
| PROJ-003 M3-M5 | PROJ-002 M3 (merge after deployed) | Split from M1-M2: M3 drops the v1 field the deployed PROJ-002 reader still reads |
| PROJ-004 M1-M2 | OTHER-007 M2 | Needs the export endpoint another app adds |

## Other proposals

- OTHER: ../../other-app/docs/proposals
```

`history.md` holds one table with the same columns, and nothing else:

```markdown
# History

| Milestones | Depends on | Note |
|------------|------------|------|
| PROJ-001 M1-M4 | None | |
| PROJ-003 M1-M2 | PROJ-001 M4 | Needs the parser M4 adds. Split at M2: M3-M5 waits on the PROJ-002 rollout |
```

`queue.md` exists once anything is scheduled, even when every row has moved to `history.md`. `history.md` is created
when the first row finishes.

The queue carries no status column. Status is read from the milestones. The two files record order. They are not a
progress view.

The queue follows these rules:

- **Order.** When a row's milestones all finish, the row moves from `queue.md` to the end of `history.md`, with its
  cells unchanged. Rows in `history.md` never move again, so it always records the order work was built in. `queue.md`
  holds only unfinished rows, and `history.md` only finished ones
- **Splits.** When other work is built between milestones of one row, the row splits at that point. Every row of a
  proposal that has more than one row carries a note saying why
- **Depends-on.** The cell holds scheduling dependencies only. It names `PROJ-NNN` or `PROJ-NNN MN`, or `None`. The
  proposal it names may live in another project. See "Other Projects' Proposals". An entry may carry the
  `(merge after deployed)` row gate. Design dependencies stay in the proposal's Dependencies section. See
  `tracking.md` "Dependency Direction". A dependency's reason goes in the row's note
- **Met.** A `PROJ-NNN MN` dependency is met when that milestone is `DONE`. A `PROJ-NNN` dependency is met when the
  proposal is `implemented`. A `(merge after deployed)` dependency also needs that work live in production, and only
  the user says when it is. Until then it is awaiting deploy. See "Deployment Dependencies". A dependency in another
  project is met by that project's milestones and proposal status, the same way
- **Blocked.** A dependency on a `DROPPED` milestone, or on a proposal that will not be built, blocks the row. The tools
  surface it to the user. They also surface a dependency on a milestone that no queue row names, or on a proposal that
  is not `accepted` or `implemented`. They never hold such a row silently. When a dropped milestone carries a
  `Replaced by` line, they name the replacement as what to wait on instead. For a dependency in another project, the
  queue row they look for is in that project's queue. A dependency awaiting deploy is never blocked, and neither is an
  unresolved one
- **Readiness.** A row is ready when its dependencies are met and every earlier row of the same proposal is finished.
  A queue row is the unit `/work-queue` runs, reviews over its commit range, and holds or blocks as a whole. Its
  milestone range is its identifier. A milestone with a `**Live after:**` line also waits for that deployment. Only
  that milestone waits, so the milestones before it in the row still run. An unresolved dependency holds the row
  until its project's proposals can be found
- **Progress.** A read-only report joins each row with its milestones' status. It prints what is done, what is next,
  what is held, and what awaits a deploy. Held rows include those with an unresolved dependency, with the fix. It also
  lists every revisit hook. `scripts/proposals.py progress` in the plugin prints it. A notice at session start names
  any hook whose date has passed

A milestone of an `implemented` proposal from an earlier era counts as met for a plain dependency on it. See
`proposals.md` "History from Earlier Eras".

### Other Projects' Proposals

A depends-on cell, a `**Live after:**` line, or a `Replaced by` line may name a proposal that lives in another
project's proposals directory. The queue says where. A `## Other proposals` section below the table maps each of those
prefixes to a proposals directory, one bullet per prefix. The example above has one entry. There is no separate config
file.

A relative path resolves against the directory `queue.md` sits in. When the specs directory is a symlink, the path
starts from the link's target, not from the link. Every checkout that links the same specs repo then resolves an entry
to the same place. The one entry form covers every repository layout:

- In a monorepo with one app per directory, the entry points at the other app's proposals directory.
- In a monorepo whose parts are submodules, the entry points into the submodule's checkout. It resolves once the
  submodule is checked out.
- In a polyrepo, the entry points at a sibling checkout, such as `../../../other-repo/docs/proposals`.
- A hybrid mixes these, with one entry per prefix.

A sibling checkout may sit at another relative path on some machine. There, pass `--proposals-for OTHER=<path>` to
`scripts/proposals.py` instead of editing the entry. The flag adds an entry or overrides one for that run. A relative
path on the flag resolves against the current directory.

An ID found in this project's own proposals directory is local, whatever its prefix. Any other ID resolves through the
entry for its prefix. A dependency resolved that way follows the Met, Blocked, and Readiness rules above, against the
other project's proposals and its own `queue.md` and `history.md`. Only this project's queue is read for entries. The
other project's entries are never followed.

A missing ID whose prefix this project uses, and that has no entry, does not exist. It blocks the row. A dependency is
unresolved when its prefix has no entry and this project uses no such prefix. It is also unresolved when its entry
leads to a missing directory, or to one that holds no proposals with that prefix. An unresolved dependency holds its
row. It is never blocked, since the fix is an entry or a flag, not a decision about the work. `scripts/proposals.py
check` reports each entry that does not resolve, and each unresolved reference.

## Deployment Dependencies

A plain dependency is a code dependency. It is met once the work it names is merged. That holds in every repository
layout. Code reaches the dependent work as merged changes in one repo, as a submodule pointer bump, or as a tag or
module bump across repos. A release that a milestone cuts is part of that milestone's `DONE`. None of these waits on a
deployment.

A deployment matters only between deploy units, which `glossary.md` defines. Two components in one repo may be
separate deploy units. Two repos may be one. Key every deployment question on deploy units, never on repos and never on
client and server roles.

Work can need another deploy unit's deployment in two ways. Each has its own marker.

### Live Checks

Some milestones have checks that read production state another deploy unit's deployment produces. Such a milestone
carries a `**Live after:**` line, on the line after its `**Status:**` line:

```markdown
### M4: Verify the backfill

**Status:** NOT STARTED
**Live after:** PROJ-002 M3 deployed
```

Write `PROJ-NNN deployed` when the whole proposal must be live. The line lives in the proposal, not in the queue. Only
that milestone waits for the deployment. The milestones before it in its row run as usual.

Not every check against production needs the line:

- A check written to record what it observes needs none. That includes a check that may record "not seen yet".
- A re-measure on recorded or hand-built input needs none.

A milestone may hold both implementation checks and checks that need the deployment. Split the live checks into a
milestone of their own. The implementation then lands without waiting for the deploy. A tool cannot read what a check
means, so reviews enforce this split. `scripts/proposals.py check` does not.

### Row Gates

A row gate holds a whole row until another deploy unit's deployment is live. The row's code must not merge before then.
Write it in the depends-on cell as `PROJ-NNN MN (merge after deployed)` or `PROJ-NNN (merge after deployed)`.

A row gate needs the proposal's skew analysis. See `proposals.md` "Version Skew". The analysis must name a failing
direction that the design cannot make tolerant. Removing a compatibility path that a deployed unit still calls is one
example. Dropping a column that the deployed version still reads is another. Without such a direction, the dependency
is a `Live after` line or a plain dependency.

### Awaiting Deploy

A deployment never confirms itself. A `Live after` line or a row gate whose code is finished is awaiting deploy until
the user says the deployment is live. Tooling reports it in its own bucket. It is never blocked.

`/work-on` and `/work-queue` ask the user once whether the deploy is live, with their other front-loaded questions. A
yes lets the work run. A no holds only the work that waits. For a `Live after` line, that is the milestone and the
milestones after it in its row. For a row gate, it is the row.

When the code the deployment needs is not finished yet, the waiting work is held instead. A run cannot deploy, so it
cannot finish that code and use the deployment in the same run.

### Legacy `(deployed)`

`(deployed)` is the earlier spelling of the row gate. A depends-on cell that carries it still parses, and tools treat it
as `(merge after deployed)`. `scripts/proposals.py check` reports each one. Reclassify it as one of these:

- A `Live after` line on the milestone whose checks need the deployment
- A `(merge after deployed)` row gate, backed by a skew analysis
- A plain dependency

### Detecting Deployment Dependencies

Repo and role signals do not imply a deployment. A separate repo, a consumer, a server, a release, a tag, or a module
or version bump says nothing about deployment on its own. Tooling reads the proposal's deploy units and its skew
analysis instead:

- A contract that crosses deploy units, with a skew analysis that names a failing direction, raises a question. The
  user decides whether the row needs a row gate.
- A contract that crosses deploy units with no skew analysis is a finding for proposal review. Tooling reports it, and
  asks no deploy question.
- Tooling notes each `Live after` line it finds. A `Live after` line needs no question at scheduling time.
- Every other dependency is plain.

## Working a Milestone

- Confirm with the user before moving on to a new milestone
- Queue rows and milestones are project management artifacts. Do not reference proposal or milestone IDs in code or
  comments
- If the proposal defers a decision to a milestone, that milestone names the deferred questions it settles. See
  `proposals.md` "Deferring Decisions"

Updating the proposal is part of the work, not an afterthought:

- When a milestone starts, set its status to `IN PROGRESS`
- When implementation changes, narrows, or corrects a decision or milestone, amend the text in place. See
  `proposals.md` "Amending a Proposal"
- When a milestone finishes, set its status to `DONE` and write its As built block
- When the last milestone finishes, set the proposal to `implemented` and update the proposal index. See
  `proposals.md` "Milestone Status"
- When a row's milestones all finish, move the row to the end of `history.md`

A queue row inherits a proposal's `**Tradeoffs:** expedient` line. See `proposals.md` "Rules".

## Stopping a Proposal

When a proposal with unfinished rows becomes `deferred`, `retracted`, `superseded`, or `rejected`, its unfinished rows
are removed from `queue.md`. Finished rows stay in `history.md`. The status change goes through these steps, in order:

1. **In-progress milestones.** The user settles an `IN PROGRESS` milestone first. For a terminal status, it becomes
   `DROPPED`. Its As built block records what code already landed, and whether it was reverted. For `deferred`, it goes
   back to `NOT STARTED` with the same note. Or it narrows to what landed and becomes `DONE`, as an amendment, and the
   rest becomes a new milestone. Uncommitted or stashed work is named in the note
2. **Partly finished rows.** A row with some milestones finished splits at its last finished milestone. The finished
   part stays as a finished row and moves to `history.md` under Order. Only the unfinished part is removed
3. **Milestones.** For `retracted`, `superseded`, and `rejected`, the unfinished milestones become `DROPPED`. Each links
   the Decision Log entry that records the status change. A `superseded` proposal's milestones carry a `Replaced by`
   line where the replacing proposal has matching work. For `deferred`, they stay `NOT STARTED`. Dropping is terminal,
   so a dropped milestone could not be revived without a new number
4. **Deferred rows.** The Decision Log entry for a deferral records each removed row's milestone range, depends-on cell,
   and note. The proposal also carries a revisit hook. See `proposals.md` "Revisit Hooks"

Reviving a deferred proposal does not schedule it. Scheduling stays a separate act the user asks for. It starts from the
rows the deferral recorded, and the user picks the new position.

Rows elsewhere in the queue that depend on the stopped proposal are surfaced under the Blocked rule.
