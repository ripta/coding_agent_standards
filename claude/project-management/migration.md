# Migrating to Era 3

How a project moves from any earlier era to era 3, which retired phases for proposal milestone status and one queue.
`/migrate-era` follows this guide. The eras and their markers are in `eras.md`. The era 3 rules are in `proposals.md`
and `plans.md`.

## Principles

- **Straight to era 3.** A project migrates from whatever era it is in directly to era 3. It never steps through the
  eras between.
- **Only live work moves.** Pending and in-progress phases move, and so do proposals that are not yet implemented.
  Finished phases, archives, and implemented proposals stay as history from their era. Rewriting finished history
  risks losing the record it holds.
- **Every backfill is offered, not applied.** The migration proposes each change it infers, and applies it only once
  the user approves. Where two artifacts disagree, the user says which is right.
- **Nothing is lost.** A fact held only in a phase, such as a divergence, a check, or the reason for a split, moves into
  the proposal or the queue before the phase is left behind.

## Step 1: Detect

Run `scripts/detect_era.py --specs-dir <specs dir> --project-root <project root>`. It reports:

- The project's era, and every era its artifacts carry
- Each live phase, with its era, status, and the proposals its Scope line names
- Each era 0 plan file, with its `## Phase N:` sections, and whether it looks like an archive of finished work
- Each live proposal, the `scheduled` and `deferred` proposals, and any status outside the vocabulary
- Each `scheduled` proposal that no live phase covers
- Project-local copies of retired skills

A project already in era 3 has nothing to migrate. Stop there. A project reported as `partial` stopped partway
through an earlier migration. Finish the steps it left undone.

Read every live phase and plan section, and every live proposal, before planning anything. Read the phase index too. It
may hold statuses, dependencies, or split reasons that no phase document repeats.

## Step 2: Map phase milestones to proposal milestones

Era 1 phases renumber their milestones from `.1` with nothing that records which proposal milestone each implements.
Era 0 phases may implement no proposal at all. Rebuild the mapping first, since every step below depends on it.

- **Era 2.** Each phase milestone row names its proposal milestone in the Proposal column. Use it.
- **Era 1.** Match each phase milestone to a proposal milestone by its description and checks. Where a proposal has a
  milestone table, use its rows. Renumbering the proposal's milestones is still allowed here, since no queue row names
  them yet. Offer the mapping to the user, and use it only once approved.
- **Era 0.** A plan section that cites a proposal implements that proposal. One that cites none has no proposal yet.
  Offer to write one, or to keep the section as a proposal draft. Never invent its design.

A phase milestone that maps to no proposal milestone becomes a new milestone in that proposal, with the next free
number. Offer it like any other backfill.

## Step 3: Rewrite each live proposal's milestones

Give every live proposal its milestones in the era 3 form, per `proposals.md` "Milestones": a `### MN: Title`
subsection, a `**Status:**` line, and plain bullets phrased as checks.

- **Status.** Take each milestone's status from the phase milestones that implement it, including those in finished
  phases that stay as history. A milestone done in any phase is `DONE`. One a phase started is `IN PROGRESS`. Any other
  is `NOT STARTED`. When a phase and the proposal disagree, ask the user which is right.
- **Checks.** Carry each acceptance criterion held only in a phase into its milestone's checks. Untick every box. Checks
  are never ticked.
- **As built.** A finished milestone gets an As built block. Carry in what its phase recorded that the checks do not
  say, by the rules in `proposals.md` "As Built". Link a long record instead of copying it.
- **Dropped work.** Rewrite `CANCELLED`, `SUPERSEDED`, `SKIPPED`, and other spellings of dropped work to `DROPPED`.
  Each gets a Decision Log entry giving its reason, and its As built block links to it. Name the replacing milestone
  in a `Replaced by` line where there is one.

## Step 4: Amend divergences

A divergence recorded in a phase but absent from the proposal's text is the drift era 3 exists to stop. For each one,
offer to amend the decision or milestone text in place, with one "Amended" marker and a Decision Log entry giving the
prior meaning, per `proposals.md` "Amending a Proposal". A divergence that only reached the Decision Log gets the same
treatment.

An implemented proposal is history and is not amended. Report what you found in it, so the user can decide whether a
correction of fact or a new proposal is needed.

## Step 5: Fix statuses

- Rewrite `scheduled` to `accepted` in every live proposal and in the proposal index. Scheduling is now read from the
  queue.
- A `scheduled` proposal that no live phase covers, which detection lists, would lose its scheduling silently. Ask the
  user whether to give it queue rows in Step 6, or to leave it `accepted` and unscheduled.
- Give every `deferred` proposal a `**Revisit:**` line, per `proposals.md` "Revisit Hooks". Ask the user for its
  condition or its date and anchor. Never invent one.
- Report every status outside the vocabulary, with the proposal. Ask the user what each one is now. A status such as
  "absorbed" usually means superseded by another proposal.
- Report a proposal whose status disagrees with its phases, in either direction, and ask the user.

## Step 6: Build the queue

Create `queue.md` beside the proposal index, in the form `plans.md` "The Queue File" gives.

- **Finished rows.** For each live proposal with milestones already `DONE`, add finished rows for them first, in the
  order their phases were built. These record the build order so far.
- **Unfinished rows.** Add one row for each live or pending phase's unfinished milestones, in the order the project
  would have built them: phase number for era 1 and era 2, and plan order for era 0. A phase that implements only part
  of a proposal becomes a row for just that range.
- **Depends-on.** Translate each phase-level dependency to `PROJ-NNN` or `PROJ-NNN MN`, using the mapping from Step 2.
  Drop each one that is already met. Keep `(deployed)` where the phase had it.
- **Notes.** Carry the reasons behind splits and interruptions, and dependency reasons held only in a phase, into each
  row's note. Every row of a proposal with more than one row needs a note saying why.

Do not add rows for proposals no phase scheduled, except those the user chose to schedule in Step 5. Scheduling the
rest stays the user's call, through `/schedule-proposal`.

Run `scripts/proposals.py check` and `scripts/proposals.py progress`. Fix every finding the migration caused.

## Step 7: Retire what era 3 replaces

- **The phases directory.** Leave every phase document in place. Add a short note at its root, such as a `README.md`
  section, naming its era and pointing to `queue.md`. Do not delete or rewrite finished phases.
- **Moved phases.** Each live phase whose work moved into the queue gets one line under its title, such as
  `**Migrated:** 2026-10-17, see queue.md row PROJ-004 M3-M5`. Change nothing else in it. The line marks the document
  as history, so neither a reader nor detection mistakes it for live work. An era 0 plan section that moved gets the
  same line under its heading.
- **Era 0 plans and archives.** Leave them in place as history, with the same note at their top.
- **Summaries of finished work.** A project-local summary of finished phases, such as one grouped by topic, can no
  longer be kept in sync. Offer to keep it frozen as history with a note, or to retire it.
- **Retired skills.** Offer to delete each project-local copy of `promote-proposal` and `phase-cleanup` that detection
  found. Under their old names they would run era 2 logic on the migrated tree. The plugin's `schedule-proposal` and
  `proposal-cleanup` replace them.
- **Project instructions.** Report any line in the project's `CLAUDE.md` or `AGENTS.md` that tells agents to maintain
  phase documents or the phase index. Offer to rewrite it for era 3.

## Step 8: Verify

Run `scripts/detect_era.py` again. It must report era 3. It reports `partial` when a queue exists beside a live phase
or plan section with no `**Migrated:**` line. Mark or move that work, then run it again. Run `scripts/proposals.py
check`, `progress`, and `hooks --passed`. Report what each says.

## Committing

A migration lands as one commit per repo it touches: the project repo and, when the specs live in a separate repo, the
specs repo. Commit by path, so unrelated changes another session left in either tree stay out. The specs repo's commit
names the project.
