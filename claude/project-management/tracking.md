# Tracking

## Cross-Reference Conventions

Documents reference each other using these patterns:

- Proposals list dependencies under `## Dependencies` as a bullet list: `- PROJ-001`
- Proposals list ADRs and other references under `## References` as a bullet list: `- ADR-01: decision explanation`
- Queue rows name milestone ranges: `PROJ-003 M1-M4`
- A reference to another project's proposal keeps that project's prefix: `OTHER-007 M2`. The queue's
  `## Other proposals` section says where that project's proposals live. See `plans.md` "Other Projects' Proposals"
- ADRs list the originating proposal under `## References`: `- PROJ-001 (originating proposal, if any)`

## Referring to Milestones

A milestone belongs to a proposal. Write it `PROJ-004 milestone 5`, or
`PROJ-004 M5` for short. A range is `PROJ-004 M3-M5`.

A milestone is a plain ordinal. It never repeats the proposal number as a
prefix. `PROJ-004 milestone 4.5` is wrong. The wrong form restates a number the
reader already has.

Work has no name besides its milestone ID. A queue row is named by its range.
Prose that needs a common noun for a row says "queue row". The word "phase"
names artifacts from earlier eras only. See `eras.md`.

## Dependency Direction

Design dependencies are expressed between proposals. A proposal never depends on
a queue row.

The queue is derived from proposal dependencies. A proposal that names a queue
row as a dependency inverts that, and makes the schedule load-bearing for the
design. Rows split and reorder. Proposal and milestone IDs are permanent.

- In a proposal's `## Dependencies`, `## Impacts`, Design Decisions, and
  Milestones, reference only `PROJ-NNN`, `PROJ-NNN milestone N`, and the
  `PROJ-NNN MN` short form
- A proposal's Decision Log may name a queue row or a phase from an earlier era,
  because recording what happened is history rather than dependency
- A scheduling dependency goes in the queue row's depends-on cell, and its
  reason in the row's note. See `plans.md` "The Queue File"

## Metadata

Each artifact type uses inline markdown metadata (not YAML frontmatter), but the fields differ by type:

- Proposals: `**Status:**`, `**Created:**`, `**Updated:**`, and `**Revisit:**` when deferred
- Proposal milestones: `**Status:**`, under the milestone's heading, and `**Live after:**` on the line after it when
  the milestone's checks need another deploy unit's deployment
- ADRs: `**Status:**`, `**Date:**`
- Bugs: `**Status:**`, plus `**Validation:**`, `**Triaged:**`, `**Estimate:**`, and `**Fixed:**` when they apply

The colon goes inside the bold, in every artifact type and every field.

## Status Vocabularies

Each artifact type has its own status values. The casing differs by type. This
is deliberate, not drift.

- Proposals use lowercase words: `draft`, `designing`, `accepted`,
  `implemented`, `deferred`, `rejected`, `superseded`, `retracted`
- ADRs use lowercase words: `proposed`, `accepted`, `superseded`, `deprecated`,
  `retracted`
- Proposal milestones use uppercase: `NOT STARTED`, `IN PROGRESS`, `DONE`,
  `DROPPED`
- Bugs use lowercase words: `open`, `accepted`, `proposed`, `fixed`,
  `not-reproducible`, `by-design`, `wont-fix`
- Ideas use lowercase words: `open`, `unclear`, `infeasible`

Each vocabulary is closed. A value outside it is an error, not a synonym. A
check reports it. See `proposals.md` "Milestone Status".

Proposals and ADRs share `accepted`, `superseded`, and `retracted`. Name the
artifact alongside those. Earlier eras used other values, such as `scheduled` for
proposals and `PLANNED` and `COMPLETE` for phases. See `eras.md`.

## Numbering Padding

Padding width differs by artifact type. This is deliberate, not an oversight:

- ADRs: 2-digit (`ADR-01`). Architectural decisions are comparatively rare per project.
- Proposals: 3-digit (`PROJ-001`). Proposal volume is typically higher over a project's lifetime.
- Milestones: unpadded (`PROJ-004 M12`). Milestones are referenced in prose and queue rows, not sorted as filenames.

Keep each artifact type's padding fixed once established; do not repad existing files. These widths are defaults for a
new project. A project that started with another width, such as `ADR-0001`, keeps it, and tools match the existing
files.

## Specs Directory

Spec and design documents may live in a centralized specs directory, symlinked into each project's `spec/` or `docs/`
directory. This keeps individual repos uncluttered while maintaining a single source of truth. If neither `spec/` nor
`docs/` are symlinks, then it means the documents live in the project repository and are committed directly there.

Proposals live in their own subdirectory under this specs directory: `spec/proposals/` (or the `docs/` equivalent). It
holds the proposals, the proposal index, `queue.md`, and `history.md`. This is why `proposals.py locate`, and the
proposal-related skills and commands that run it, look for `spec/proposals/` and `docs/proposals/` as common locations.
They're checking for this directory. A `spec/phases/` directory is history from an earlier era. See `eras.md`.

ADRs are usually named `spec/adrs/`, although legacy projects have no fixed subdirectory name; place them alongside any
existing ADRs, or ask where they should live if none exist yet.

Bugs live in `bugs/` beside the proposals directory, such as `spec/bugs/` next to `spec/proposals/`, or the `docs/`
equivalent. Some projects use `bugs/` at the repo root. The "Lookup Rule" below checks `<proposals parent>/bugs` first,
then `<repo root>/bugs`. Use the first that exists. When none does, create `bugs/` beside the proposals directory. When
the project has no proposals directory either, ask the user where bugs go.

In a repo with several components, a bug goes with the component that owns the code, when components keep their own
specs. The same rule finds that component's bugs directory. See "Bugs" below for the format.

Ideas live in one file, `ideas.md`, beside the proposals directory, such as `spec/ideas.md` next to `spec/proposals/`.
Use the file that exists. See "Ideas" below for the format.

### Index File Name

A proposals directory has exactly one index. So does a bugs directory. It is named `index.md` or `README.md`. A new
index is `index.md`. Skills and commands accept either name.

A directory holding both is out of standard. Consolidate it before any tool updates its index. Merge the rows and any
prose into one file, then delete the other. A tool that finds both stops before editing either one and tells the user.

## Lookup Rule

A repo can hold several components. Each may keep its own specs, Makefile, and `.gitignore`. The ones nearest the code
at hand belong to it. A skill or command that needs them follows this rule and does not search on its own. A project's
own instructions override it.

1. **Specs.** Run `python3 <root>/scripts/proposals.py locate`. The `<root>` is the plugin root that the
   `coding-standards:` line at session start names. The command searches up from the current directory, or from
   `--start DIR`. It takes the nearest proposals directory, as "Specs Directory" names the locations. It stops at the
   repo boundary, a `.git` directory or file. It prints JSON with `repo_root`, `proposals_dir`, `index`, `queue`,
   `history`, `ideas`, `bugs_dir`, and `bugs_index`. Each is an absolute path, or null when nothing was found.
2. **Which component.** A monorepo can keep a proposals directory per component. A root that keeps its own proposals
   directory hides theirs from a search that starts there. A root that keeps none searches below it, checked-out
   submodules included. A single component found there is returned as found, with `found_below` set to true. Pass
   `--start` a path inside the component the work concerns. When several candidates match, `locate` exits non-zero and
   lists them. Ask the user which component, with AskUserQuestion, then run it again with
   `--start`. When none exists, it exits with a distinct code. Follow the creation rules under "Specs Directory" and
   "Bugs".
3. **Makefile and `.gitignore`.** Use the one nearest at or above the target path, up to the repo root. When the changed
   paths span several, use each path's own. A path with none has none. Say so. Do not take a farther one in its place.
   `makefile-helper` uses the nearest Makefile. It may mention the repo root's Makefile when that one differs, but must
   not run it in place of the nearest one.

## Bugs

Each bug is one file, named `YYYYMMDD-short-name.md`. The date is when the bug was first observed. Filing it is covered
by `rules/found-bugs.md`. Verifying it later is the `bug-triage` skill's job. `bug-sweep` runs `bug-triage` over every
open bug in one unattended run.

The file opens with a title that states the wrong behavior in one line. The `**Status:**` line comes right after it.
The status vocabulary is under "Status Vocabularies" above. The sections follow:

- `## Observed`: what goes wrong, as a user or caller sees it
- `## Cause`: the code that produces it, by file and line. Leave this out when the cause is unknown
- `## Repro`: the commands or input that show it, with the expected and the actual result
- `## Fix`: the suggested fix. Name each design call it needs, with its options. A partial fix that already landed is
  recorded here by commit subject
- `## Workarounds`: what works around the bug today, and what to remove once it is fixed. Leave this out when nothing
  does

A bug the filer could not confirm stays `open`. A `**Validation:**` line under the status says what was tried, and that
it did not confirm the bug, such as `**Validation:** not confirmed; the repro needs a second node`. `bug-triage`
reproduces it later.

`fixed`, `not-reproducible`, `by-design`, and `wont-fix` close a bug. The others leave it open. Two of the closed
statuses need a `**Resolution:**` line under the status, which says why the bug closed:

- `by-design`: the behavior reproduces, and it is what the code is meant to do. The line cites the contract that says
  so: a doc, an ADR, a test that asserts the behavior, or a decision the user recorded. Code that disagrees with its
  own docs is a bug, not a design. Only the user closes a bug as `by-design`
- `wont-fix`: the bug is real, and the user decided not to fix it. The line gives the user's reason and the date they
  decided. Only the user closes a bug as `wont-fix`

A bug the filer finds to be by design before filing gets no file. See `rules/found-bugs.md`.

The directory's index opens with a short note on the format, then a table with one row per bug. The columns are Bug,
Status, and Summary. The Bug cell links the file. The file's `**Status:**` line is the authority, and the index mirrors
it. Change both in the same commit.

## Ideas

An idea is a feature or concern that no proposal covers yet. The ideas file holds them until one becomes a proposal or
is dropped. `idea-intake` checks new ideas against the code, the proposals, and this file, then writes the ones that are
new. `proposal-cleanup` removes an idea once a proposal covers it.

The file opens with a short intro paragraph. Each idea is one `##` section with no sub-headings. A section runs to the
next `##` heading, so a sub-heading would cut it short when it is removed. Each section holds:

- The heading: a short name for the idea
- A `**Status:**` line. The vocabulary is under "Status Vocabularies" above
- A `**Captured:**` line with the date it was written, as `YYYY-MM-DD`
- An `**Extends:**` line, only when the idea adds to something that already exists. It names the feature by file and
  line, the proposal by ID, or the idea by heading. The idea covers only what that thing lacks
- A paragraph on the problem: what the idea is for, and who wants it
- A paragraph on context: the related code by file and line, related proposals, and prior art
- A paragraph on feasibility: a sketch of the approach, its risks, and its open questions

An `infeasible` idea's feasibility paragraph says why, and what would change the verdict. It stays in the file, so the
same idea is not researched again. An `unclear` idea lists the questions it still needs answered. A section with no
status line reads as `open`. Older ideas files are free-form, and a project's own format overrides this one.

In a repo with several components that keep their own specs, an idea goes in the file of the component it changes.

## Markdown Quality

- Use a markdown linter with a shared config. The config is `rumdl/rumdl.toml.template` in the coding standards repo;
  copy it to `.rumdl.toml` at the project root. See `rumdl/README.md` for setup and for why it is copied rather than
  symlinked
- ATX-style headings (`#`)
- Dash-style unordered lists (`-`)
- Line length: 120 characters (excluding code blocks)
- GitHub Flavored Markdown

The 120 here governs markdown prose only. Code and code comments wrap at 100, which `claude/rules/work-discipline.md`
sets and each language's formatter enforces. The two numbers are independent.

Configure the linter rather than trusting its defaults. rumdl's built-in MD013 width is 80, so a project that ships no
`.rumdl.toml` enforces 80 while documenting 120, and the run still looks clean.
