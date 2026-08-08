# Glossary

Terms used across the project management standards. Each term is defined once
here and used consistently in `proposals.md`, `plans.md`, `design.md`, and
`tracking.md`.

**Proposal** — a description of a feature or change at the design level, written
before implementation begins. Carries a lifecycle status from `draft` to
`implemented`. Numbered permanently within a project. One proposal per file.

**Phase** — a unit of implementation work. Each phase implements exactly one
proposal, or a portion of one. A proposal may be split across several phases.
Completed phases keep their number forever. Pending phases may be renumbered.

**Promotion** — moving an accepted proposal into a phase so implementation can
start. Creating a proposal is not promotion. Promotion happens only when the
user asks for it.

**Milestone** — a named subdivision of work. Proposals and phases each number
their milestones separately, and the two namespaces do not overlap.

**Proposal milestone** — an implementable chunk of work listed in a proposal.
Numbered as a plain ordinal from 1. Written `PROJ-004 milestone 5`, or
`PROJ-004 M5`. Carries no status.

**Phase milestone** — a unit of implementation work listed in a phase. Numbered
from `.1` upward within its phase. Written `Phase 7.1`. Phase-local: it does not
inherit the numbering of the proposal milestone it implements. Carries a status,
and that status is the only record of execution progress.

**Research write-up** — a document usually imported from an external source. Its
claims may be unproven. It can feed a design spike, a proposal, or eventually an
ADR.

**Design spike** — a small discovery or experiment run to prove or disprove that
an approach will work. Discovery means reading documentation or code.
Experimentation means writing throwaway code or building a spreadsheet. A spike
usually weighs a few candidate options against each other. Its result is proven,
but it recommends nothing on its own.

**ADR** — a decision codified with its proof. The proof is the explanation,
context, and measurements behind it. An ADR serves as a rule or guideline for
future decisions and designs. Immutable once accepted. Superseded by a new ADR
rather than edited.

These three differ in weight. A research write-up is the lightest and may be
unproven. A design spike is proven, and carries more weight. An ADR is both
proven and recommended, so it is the heaviest. Weight is not permanence. A later
spike, research write-up, or proposal can show an ADR to be wrong, and the ADR
is then superseded.

**Index** — an `index.md` at the root of a proposals or phases directory,
holding a status table with one row per artifact. Created with the first
artifact of its kind, even when only one will ever exist.

**Specs directory** — where proposals, phases, and ADRs live. Often a
centralized directory symlinked into a project as `spec/` or `docs/`. When
neither is a symlink, the documents are committed to the project repo directly.
