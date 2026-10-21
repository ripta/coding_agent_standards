# Plans (The Queue)

A project builds its work from one ordered queue. Each queue row names a range of one proposal's milestones. The queue's
order is the build order, independent of proposal number and acceptance date. Execution status lives on the proposal
milestones themselves. See `proposals.md` "Milestones".

Phase documents and the phase index belong to earlier eras. A project that still has them keeps them as history. See
`eras.md`.

## Rules

- A queue row names one contiguous range of one proposal's milestones, such as `PROJ-004 M3-M5`. A milestone appears in
  at most one row
- Unfinished rows belong only to `accepted` proposals. Finished rows stay, whatever the proposal's status becomes
- A milestone's ID is permanent once any queue row names it. Rework, or work split out of a milestone, becomes a new
  milestone with the next free number
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

The queue is `queue.md`, beside the proposal index in the proposals directory. It holds one table:

```markdown
# Queue

| Milestones | Depends on | Note |
|------------|------------|------|
| PROJ-001 M1-M4 | None | |
| PROJ-003 M1-M2 | PROJ-001 M4 | Needs the parser M4 adds. Split at M2: M3-M5 waits on the PROJ-002 rollout |
| PROJ-002 M1-M3 | None | |
| PROJ-003 M3-M5 | PROJ-002 M3 (deployed) | Split from M1-M2: waits on the PROJ-002 rollout |
```

The queue carries no status column. Status is read from the milestones. `queue.md` records order. It is not a progress
view.

The queue follows these rules:

- **Order.** When a row's milestones all finish, the row moves above every unfinished row. Finished rows stay, so the
  top of the file always records the order work was built in
- **Splits.** When other work is built between milestones of one row, the row splits at that point. Every row of a
  proposal that has more than one row carries a note saying why
- **Depends-on.** The cell holds scheduling dependencies only. It names `PROJ-NNN` or `PROJ-NNN MN`, or `None`. Design
  dependencies stay in the proposal's Dependencies section. See `tracking.md` "Dependency Direction". A dependency's
  reason goes in the row's note
- **Met.** A `PROJ-NNN MN` dependency is met when that milestone is `DONE`. A `PROJ-NNN` dependency is met when the
  proposal is `implemented`. A `(deployed)` dependency is also met only once it runs in production. See "Deployment
  Dependencies"
- **Blocked.** A dependency on a `DROPPED` milestone, or on a proposal that will not be built, blocks the row. The tools
  surface it to the user. They also surface a dependency on a milestone that no queue row names, or on a proposal that
  is not `accepted` or `implemented`. They never hold such a row silently. When a dropped milestone carries a
  `Replaced by` line, they name the replacement as what to wait on instead
- **Readiness.** A row is ready when its dependencies are met and every earlier row of the same proposal is finished.
  A queue row is the unit `/work-queue` runs, reviews over its commit range, and holds or blocks as a whole. Its
  milestone range is its identifier
- **Progress.** A read-only report joins each row with its milestones' status. It prints what is done, what is next,
  and what is held, and lists every revisit hook. `scripts/proposals.py progress` in the plugin prints it. A notice
  at session start names any hook whose date has passed

A milestone of an `implemented` proposal from an earlier era counts as met for a plain dependency on it. See
`proposals.md` "History from Earlier Eras".

## Deployment Dependencies

A plain dependency is a code dependency. Write `PROJ-NNN MN (deployed)` or `PROJ-NNN (deployed)` when the row also needs
that work running in production first.

A deployment dependency crosses a boundary the dependent row cannot satisfy by itself. The dependency's code must be
live somewhere the dependent row does not control. These are the boundaries:

- Another repo. The dependent work lives in a different repo and consumes the dependency through a tagged release or a
  module bump.
- A running process. The dependent row's tests or verification run against a deployed server or consumer that
  exercises the dependency.
- A datastore. The dependent row reads tables, data, or backfilled rows that only the dependency's deployed migration
  produces.
- Adopted consumers. The dependent row removes a compatibility path, flag, or old API version. Consumers must first
  migrate off it, so the dependency must ship and be adopted.

Signals that a boundary exists include a release, a tag, a `go.mod` or version bump, a consumer, a deployed server, a
migration, a backfill, a flag removal, or a separate repo. When both rows are code in one repo, and the dependent row
only builds and tests against the dependency's merged changes, the dependency is code-only. A coordinated downstream
release does not change that. It belongs to the consumer repo's queue.

Tooling looks for these signals before it asks about a deployment. With no signal, it writes a plain dependency and says
the dependency is code-only. With a signal, it asks the user and names the signal. Only the user can confirm a
deployment.

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
- When a row's milestones all finish, move the row above every unfinished row

A queue row inherits a proposal's `**Tradeoffs:** expedient` line. See `proposals.md` "Rules".

## Stopping a Proposal

When a proposal with unfinished rows becomes `deferred`, `retracted`, `superseded`, or `rejected`, its unfinished rows
are removed from the queue. Finished rows stay. The status change goes through these steps, in order:

1. **In-progress milestones.** The user settles an `IN PROGRESS` milestone first. For a terminal status, it becomes
   `DROPPED`. Its As built block records what code already landed, and whether it was reverted. For `deferred`, it goes
   back to `NOT STARTED` with the same note. Or it narrows to what landed and becomes `DONE`, as an amendment, and the
   rest becomes a new milestone. Uncommitted or stashed work is named in the note
2. **Partly finished rows.** A row with some milestones finished splits at its last finished milestone. The finished
   part stays as a finished row and moves up under Order. Only the unfinished part is removed
3. **Milestones.** For `retracted`, `superseded`, and `rejected`, the unfinished milestones become `DROPPED`. Each links
   the Decision Log entry that records the status change. A `superseded` proposal's milestones carry a `Replaced by`
   line where the replacing proposal has matching work. For `deferred`, they stay `NOT STARTED`. Dropping is terminal,
   so a dropped milestone could not be revived without a new number
4. **Deferred rows.** The Decision Log entry for a deferral records each removed row's milestone range, depends-on cell,
   and note. The proposal also carries a revisit hook. See `proposals.md` "Revisit Hooks"

Reviving a deferred proposal does not schedule it. Scheduling stays a separate act the user asks for. It starts from the
rows the deferral recorded, and the user picks the new position.

Rows elsewhere in the queue that depend on the stopped proposal are surfaced under the Blocked rule.
