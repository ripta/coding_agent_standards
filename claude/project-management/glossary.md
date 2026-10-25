# Glossary

Terms used across the project management standards. Each term is defined once
here and used consistently in `proposals.md`, `plans.md`, `design.md`,
`tracking.md`, and `eras.md`.

**Proposal**: a description of a feature or change at the design level, written
before implementation begins. Carries a lifecycle status from `draft` to
`implemented`. Numbered permanently within a project. One proposal per file.

**Milestone**: a chunk of work a proposal commits to. A plain ordinal from 1.
Written `PROJ-004 milestone 5`, or `PROJ-004 M5`. A subsection of the proposal
whose bullets are its checks. Carries a status, and that status is the only
record of execution progress. Its number is permanent once a queue row names
it.

**As built**: the block at the end of a started milestone that records what
implementation found: bugs fixed along the way, residuals, measurements, and
scope narrowed.

**Queue**: the ordered list of work a project will build, in `queue.md` beside
the proposal index. Its order is the build order. Finished rows move to
`history.md` beside it, which records the order work was built in.

**Queue row**: one contiguous range of one proposal's milestones, such as
`PROJ-004 M3-M5`, with its scheduling dependencies and a note. Named by its
range. The unit `/work-queue` runs and reviews as a whole.

**Scheduling**: adding queue rows for an accepted proposal. Creating or
accepting a proposal is not scheduling it. Scheduling happens only when the user
asks for it.

**Deploy unit**: the set of components that reach production together, in one
artifact or one atomic switch. Repo layout does not decide it. Two apps in one
monorepo that deploy separately are two units. Repos or submodules built into
one artifact are one unit. A coordinated release of separately running
processes is still several units. A rolling or staged rollout runs their old and
new versions side by side.

**Revisit hook**: a `**Revisit:**` line that says when to look at deferred work
again: a condition, an on-or-after date with its anchor, or both.

**Phase**: a unit of implementation work in eras 0 through 2. Era 3 retired
it. The word names those artifacts only. See `eras.md`.

**Research write-up**: a document usually imported from an external source. Its
claims may be unproven. It can feed a design spike, a proposal, or eventually an
ADR.

**Design spike**: a small discovery or experiment run to prove or disprove that
an approach will work. Discovery means reading documentation or code.
Experimentation means writing throwaway code or building a spreadsheet. A spike
usually weighs a few candidate options against each other. Its result is proven,
but it recommends nothing on its own.

**ADR**: a decision codified with its proof. The proof is the explanation,
context, and measurements behind it. An ADR serves as a rule or guideline for
future decisions and designs. Reserved for decisions that are cross-cutting,
hard to reverse, or a departure from the past. Records an invariant or
constraint, never the format or mechanism that implements it. Takes only minor
edits once accepted. A change to what it decides is a new ADR that supersedes it.

These three differ in weight. A research write-up is the lightest and may be
unproven. A design spike is proven, and carries more weight. An ADR is both
proven and recommended, so it is the heaviest. Weight is not permanence. A later
spike, research write-up, or proposal can show an ADR to be wrong, and the ADR
is then superseded.

**Era**: a numbered style of project management, written `era 1`. Each era is a
set of conventions for where design, execution status, and implementation order
live. An artifact belongs to the era whose markers it carries. The first mention
of an era in a document carries a short gloss naming what that era introduced.
See `eras.md`.

**Index**: an `index.md` or `README.md` at the root of a proposals
directory, holding a status table with one row per proposal. Created with the
first proposal, even when only one will ever exist.

**Specs directory**: where proposals, the queue, and ADRs live. Often a
centralized directory symlinked into a project as `spec/` or `docs/`. When
neither is a symlink, the documents are committed to the project repo directly.
