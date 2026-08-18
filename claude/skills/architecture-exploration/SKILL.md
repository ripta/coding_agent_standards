---
name: architecture-exploration
description: |
  Use this skill to produce a deep, citation-grounded ARCHITECTURE.md for the
  current project by investigating the codebase. Detects the project type
  (backend service, frontend app, CLI, library, or full-stack) and tailors the
  reference to it. If invoked with arguments, scopes the exploration to that
  directory/crate/subproject. Read-only except for writing ARCHITECTURE.md.
model: opus
allowed-tools: Read, Glob, Grep, Bash, Write, Task, Workflow
---

You produce a deep technical reference document for a project's architecture by
investigating its code. You write the result to `ARCHITECTURE.md` (overwriting
if it exists) at the root of the explored scope. Apart from that one file, this
is a strictly read-only exploration — do not modify any other files.

You act as an **orchestrator**: you classify the project yourself, then fan out
the bulk of the discovery to parallel `Explore` subagents (one per section),
and finally synthesize their findings into the document. This keeps the raw file
reading out of your context (cheaper) and runs the independent sections
concurrently (faster). The subagents locate and quote code; you verify and
write.

Discovery runs in one of three modes, sized in Step 3:

- **inline** — tiny scope, no fan-out at all; you read the code yourself.
- **fan-out** — the default; parallel `Explore` subagents, and you spot-verify a
  sample of the citations they return.
- **workflow** — large scope; hand the plan to `workflow.js`, which fans out the
  same sections, verifies **every** citation, then shards the writing itself.
  Spot-checking is a cost concession, not a design goal. Once the surface is
  large enough that a bad sample is likely, the workflow buys back the guarantee.

Workflow mode never puts the whole document through one generation. Each part is
written to its own file and the results are concatenated mechanically, so an
agent that dies costs one subsection rather than the document. Above ~60 KB of
predicted output it also splits the reference-heavy sections into sibling files
(`ARCHITECTURE-key-flows.md` and so on), leaving `ARCHITECTURE.md` as the
narrative entry point with a summary and a link for each.

## Workflow

### Step 1: Determine Scope

If the skill was invoked with arguments, treat them as a scope restriction — a
directory, crate, subproject, package, or module. Confine all exploration,
citations, and output to that scope, and write `ARCHITECTURE.md` at the scope
root rather than the working directory.

If no arguments were given, the scope is the whole repository and
`ARCHITECTURE.md` goes in the current working directory.

Resolve the scope to a concrete path before continuing, and report it in Step 4.

Then establish two paths used throughout:

- **citation base** — the directory `ARCHITECTURE.md` is written to (the scope
  root, or the working directory for a whole-repo run). Every citation in the
  document is written relative to this directory.
- **repository root** (`git rev-parse --show-toplevel`) — used only to express
  the citation base in a relative, non-absolute form in the document's header
  note (see Step 6, section 1).

### Step 2: Classify the Project

Inspect manifests (e.g. `package.json`, `go.mod`, `Cargo.toml`, `pyproject.toml`),
entrypoints, and the directory layout within scope to determine the project
type(s):

- **backend service** — exposes HTTP / RPC / GraphQL
- **frontend app** — SPA or SSR rendering a UI
- **CLI** — command-line tool
- **library / SDK** — consumed as a dependency via its exported API
- **full-stack** — more than one of the above

This classification drives which variant of each later section you emit. Prefer
reading code over README/docs when they disagree. Do this yourself (don't
delegate) — it's cheap and it gates the fan-out: the detected type(s) decide
which section variants the discovery agents are briefed to gather.

### Step 3: Size & Plan the Fan-out

Decide how many discovery agents to spawn and how to partition the work. The base
is one agent per section (§§2–6 of Step 6); size only changes whether a heavy
section is *sharded*, not the number of sections. Measure cheaply — these are
read-only and piggyback on the classify pass:

- **`N_files`** — `git ls-files -- <scope> | wc -l`. Tracked files only; excludes
  the gitignored vendor/build noise that a raw `find` would inflate.
- **`N_units`** — count of the natural partition unit for the detected type, via
  one targeted grep (you know the framework by now): route/handler registrations
  (backend), route entries + top-level components (frontend), command definitions
  (CLI), exported symbols or top-level modules (library).
- **`N_dirs`** — significant top-level directories in scope.

Apply these as **rough, tunable defaults** — not hard rules:

- `N_files` ≲ 25 → **skip the fan-out** and explore inline; the orchestration
  overhead outweighs the parallelism on a project this small.
- `N_files` ≳ 200, **or** any section shards → run **workflow mode** (Step 5b).
  Both signals mean the same thing: enough citations that spot-checking a
  handful of them is not evidence. Everything between this and the 25-file
  floor runs the default fan-out (Step 5a).
- `N_units` ≳ 30 → shard Public Surface (§2) into ⌈`N_units` / 20⌉ agents.
- Many cross-cutting categories apply → split Cross-cutting (§4) into two agents
  (data/auth/persistence ∥ observability/config/jobs/testing).
- Large surface → give Key Flows (§3) one agent per flow (2–3) rather than one
  agent for all.

Two guardrails override the table:

- **Shard along structural boundaries that tile cleanly** — per router file, per
  command group, per top-level package — so the shards partition the surface
  exhaustively with no gaps or overlap. Never shard by an arbitrary file range.
- **Cap the fan-out at ~10–12 agents in fan-out mode.** Beyond that, findings
  reflood the synthesis context — the exact cost this delegation exists to avoid
  — and the dedup work grows faster than the parallelism helps. This caps
  *discovery* agents, because they are what feeds synthesis. Verifiers do not
  count against it: their output is verdicts, not findings.

**Workflow mode relaxes that cap to ~16.** Nothing there reads all the findings
at once — each part writer sees only its own section's evidence, and the one
agent that sees everything gets claim sentences with the snippets stripped. Use
the headroom: a section that returns more than ~110 claims produces roughly 25 KB
in one generation, which is the top of the range that has been observed to
complete. The script warns when a section lands over that, so treat the warning
from one run as the sharding plan for the next.

In workflow mode also tag each section for the document layout:

- `mode: 'narrative'` — read start to finish, stays in `ARCHITECTURE.md`. Use it
  for §1 Orientation, §5 Mental Model, and §6 Onboarding.
- `mode: 'reference'` — looked up, not read, and eligible to move to its own
  file. Use it for §2 Public Surface Area, §3 Key Flows, and §4 Cross-cutting.
- `group` — shards of one document section share a `group` title and each keep a
  distinct `key`. They render as one `##` heading with a `###` per shard.

Carry the resulting agent list into Step 4 (to report) and Step 5a or 5b (to
dispatch).

### Step 4: Report

Before fanning out, briefly tell the user the resolved scope, the citation base
(expressed relative to the repository root, so the user sees what paths will be
anchored to), the detected project type(s), the chosen mode and the measurements
that selected it, the planned fan-out (agent count and how sections are
partitioned), and a high-level outline of what you've discovered. Keep this
short — it confirms direction before the full pass.

Workflow mode spends materially more than fan-out mode. Report the mode and
stop for the user's go-ahead before starting Step 5b. Do not launch it on the
strength of the size thresholds alone.

### Step 5a: Parallel Discovery (fan-out mode)

Dispatch one `Explore` subagent per documentation section to gather its raw
material concurrently. **Issue all the Task calls in a single message** so they
run in parallel. Follow the fan-out plan from Step 3: default to one agent per
section in Step 6 (§§2–6), sharding the heavy sections as that plan decided.

Give every discovery agent the same **shared brief**, then its section-specific
task:

> You are gathering material for one section of an ARCHITECTURE.md. This is a
> strictly read-only task — do not modify any files. Confine your exploration to
> the scope `<resolved scope path>`. The project is classified as
> `<detected type(s)>`.
>
> Your deliverable IS the evidence, not prose. For every claim, return the exact
> `file:line` plus a **verbatim** code snippet (a few lines) proving it — these
> become citations I cannot re-derive, so paraphrase is useless to me. Express
> every path **relative to `<citation base>`**; never return an absolute path or
> one starting with `/` or `~`. Prefer reading code over README/docs when they
> disagree. If something is ambiguous or you are inferring, say so explicitly and
> mark it as a guess. Be thorough within your section and ignore everything
> outside it.

Brief each agent against the matching Step 6 section spec (§§2–6), and emit only
the variant relevant to the detected type(s). Suggested split:

- **Orientation & layout** → §1 (languages, frameworks, build/runtime tooling,
  how it's consumed/exposed and versioned, top-level directory map).
- **Public Surface Area** → §2.
- **Key Flows** → §3 (identify and trace 2–3 representative flows end-to-end with
  a `file:line` at every hop).
- **Cross-cutting Concerns** → §4 (may be split across two agents).
- **Mental Model** → §5 (core abstractions, conventions/idioms, sharp edges,
  TODOs, tech debt).
- **Onboarding** → §6 (run commands, add-a-unit recipe, first files to read).

You may also do a quick `Glob`/`Bash` pass yourself for the directory map and
manifests if that's faster than briefing an agent for it.

### Step 5b: Delegated Discovery (workflow mode)

Hand the Step 3 plan to the bundled script instead of dispatching the agents
yourself. It runs the same per-section fan-out, verifies every returned citation
against the source, fixes the shared vocabulary, then writes the document one
part at a time.

Budget, for `S` sections and `C` verified claims: `S` discovery agents, about
`C/80` verifiers, one spine agent, `S` part writers, and one assembler — so
roughly `2S + C/80 + 2`. A 12-section plan over 1,250 claims comes to about 42
agents. Most of that is verifiers running at low effort. Quote the number to the
user when you ask for the go-ahead in Step 4.

```js
Workflow({
  scriptPath: "${CLAUDE_SKILL_DIR}/workflow.js",
  args: {
    scope:            "<absolute path to the explored root>",
    citationBase:     "<ABSOLUTE path to the dir ARCHITECTURE.md goes in>",
    citationBaseLabel: "the repository root",   // or e.g. "`packages/api/`"
    skillDir:         "${CLAUDE_SKILL_DIR}",
    types:            ["backend"],
    sections: [
      { key: "orientation", title: "Orientation & layout", brief: "<§1 spec>",
        mode: "narrative" },
      { key: "surface-http", title: "HTTP endpoints", brief: "<§2 spec>",
        mode: "reference", group: "Public Surface Area" },
      { key: "surface-rpc",  title: "RPC methods",    brief: "<§2 spec>",
        mode: "reference", group: "Public Surface Area" }
      // ...one entry per section in the Step 3 plan
    ]
  }
})
```

Contract notes, all of which the script enforces or depends on:

- `citationBase` must be **absolute** — the discovery and verifier agents
  resolve relative citations against it. The script rejects a relative value.
- `citationBaseLabel` is the *same directory* written relative to the repository
  root. It is the only form that reaches the document, per Step 6 section 1.
  Keep these two in sync; they describe one directory in two notations.
- `archPath` is not an argument. The script derives it as
  `<citationBase>/ARCHITECTURE.md` so the two cannot drift apart.
- Sharded sections are separate `sections` entries with distinct `key`s, sharing
  one `group`. The script rejects duplicate keys rather than silently merging
  two shards into one part.
- `mode` defaults to `narrative`, which keeps a section in the main file. A
  section only ever moves to a sibling file if you tag it `reference` **and** the
  document is large enough to warrant splitting.
- Include §1 here. The "do the directory map yourself" shortcut in Step 5a has
  no equivalent mid-workflow.

The script owns Step 6 in this mode — its part writers read this file for the
format spec and write the document themselves. Do not write it yourself as well.
It returns:

```text
{ wrote, path, files: [{ path, bytes }], partsDir, failedParts,
  citations: { confirmed, corrected, refuted, unchecked },
  refutedSample, uncheckedSample, outline, openQuestions }
```

`refuted` means a verifier read the file and the snippet was not there.
`unchecked` means no verifier ever returned a verdict, after retries. Both are
excluded from the document, but they mean different things and Step 7 reports
them separately.

On `wrote: false`, report the `reason` and stop. Do not fall back to Step 5a
silently — a failed run usually means the plan or the scope was wrong, and
re-running the same plan by hand will fail the same way. If `partsDir` comes
back non-null, the individual parts survived on disk; say so, because that is
recoverable work.

### Step 6: Synthesize & Write ARCHITECTURE.md

**Fan-out mode only** — in workflow mode the script's part writers do this, each
reading the section specs below for the format of its own part. The rules in this
step bind both paths; only the executor differs.

In workflow mode the script owns the document skeleton, not the writers: it
assigns every `##`/`###` heading, builds the table of contents, writes the
citation-base note, and decides which sections land in sibling files. Writers
receive their heading verbatim and the resolved link target for every other part,
so they can cross-link to sections that have not been written yet.

Assemble the agents' findings into the full document in one pass — well-structured
Markdown with a table of contents and the sections below. Ground every claim in
actual code with `file:line` citations, using links of the form
`[path/to/file.ext:42](path/to/file.ext#L42)`. If something is ambiguous or a
subagent flagged it as a guess, carry that caveat through — never launder an
inference into a confident claim.

**Spot-verify before committing citations.** The discovery agents locate code but
don't audit it, so their line numbers can drift. Before writing, sample a handful
of the returned citations across different sections and confirm them yourself with
`Grep`/`Read`. If a sample is wrong, distrust that agent's batch and re-check its
citations more broadly. Discard any claim you can't ground.

Sampling is a concession to context cost — reading every cited file back into
this context would undo the delegation. Workflow mode does not have that
constraint: it verifies every citation in parallel subagents and only verdicts
return, so the claims reaching its synthesis agent are already confirmed and
line-corrected. In that mode do not re-verify, and treat the supplied line
numbers as correct.

Citation paths MUST be relative to the citation base (the directory containing
this document), so the links resolve when the document is opened. Never emit an
absolute path or one beginning with `/` or `~`, and never leak a symlinked or
machine-specific prefix. If a subagent or tool reports an absolute path, strip
everything up to and including the citation base before citing it.

Emit only the section variants relevant to the detected project type. For
full-stack projects, cover each side.

#### 1. Orientation (always)

- A one-line note, near the top of the document, stating the citation base so
  readers know what every path is relative to. Express it relative to the
  repository root — never as an absolute path. For a whole-repo run write "All
  paths are relative to the repository root."; when scoped, name the scope, e.g.
  "All paths are relative to `packages/api/`."
- Language(s), framework(s), build/runtime tooling.
- How the project is consumed or exposed, and how it's versioned:
  - backend → HTTP server / RPC / GraphQL / outbox views
  - frontend → routes, entry HTML, bundler/dev server
  - CLI → commands and how it's installed/invoked
  - library → exported package API and how it's imported
- Top-level directory map with the role of each significant folder.

#### 2. Public Surface Area

A table of the project's public interface, adapted to the project type:

- backend → endpoints / RPC methods / GraphQL resolvers
- frontend → routes/pages + top-level components + public hooks/stores
- CLI → commands, subcommands, flags
- library → exported functions / types / classes

Columns: name, location (`file:line`), inputs, outputs, errors, and
auth/permissions (omit the auth column when it doesn't apply). Flag anything
internal, deprecated, or experimental.

#### 3. Key Flows / Lifecycle

Pick 2–3 representative flows and trace each end-to-end with `file:line`
references at every hop:

- backend → a request: routing → middleware → validation → handler → business
  logic → data layer → response serialization → error paths
- frontend → a user interaction: user action → event handler → state update →
  data fetch → re-render → loading/error states
- CLI → an invocation: arg parsing → command dispatch → core work → output /
  exit codes
- library → a public call: entry function → internal layering → return/error
  contract

Choose a mix that exercises different concerns (e.g. one read, one write, one
auth-sensitive flow for a backend).

#### 4. Cross-cutting Concerns

Cover the following where they apply; skip what's genuinely N/A:

- Authentication & authorization model
- Data model and persistence (schemas, migrations, ORMs)
- State management — client and/or server (especially for frontends)
- Validation, serialization, error-handling conventions
- Logging, metrics, tracing
- Configuration, secrets, feature flags
- Background jobs, queues, scheduled tasks, websockets/streams
- Rate limiting, caching, idempotency
- Routing & navigation (frontend)
- Styling/theming and the asset/bundling pipeline (frontend)
- Testing strategy and exemplary tests for each public surface

#### 5. Mental Model

- ASCII or Mermaid architecture diagram.
- The 5–10 abstractions/concepts to internalize to be productive.
- Non-obvious conventions and idioms.
- Known sharp edges, TODOs, or technical debt observed.

#### 6. Onboarding Cheatsheet

- Exact commands to run the project locally and exercise it:
  - backend → start the server and hit it (curl/SDK samples)
  - frontend → start the dev server and the URL to open
  - CLI → an example invocation
  - library → install + a minimal import/usage snippet
- Step-by-step recipe for adding a new unit following existing conventions
  (a new endpoint / route+component / subcommand / exported function), citing
  the files to touch.
- The 3 files to read first, in order, and why.

### Step 7: Summarize

After writing the document, print a short summary of what's in it and any open
questions you couldn't resolve from the code alone.

In workflow mode, build that summary from the returned `outline` and
`openQuestions` rather than re-reading the document. Also report:

- **The citation tally** — confirmed, line-corrected, refuted, and unchecked.
  Keep the last two apart. A refuted citation was checked and found wrong; an
  unchecked one means a verifier died and nobody ever looked. Reporting the
  second as the first tells the user the document is thinner than it is *for the
  wrong reason*. Surface `refutedSample` and `uncheckedSample` when either count
  is non-trivial.
- **`failedParts`**, if non-empty. Those subsections are placeholders in the
  document, and re-running fills them in.
- **Every file written**, not just `ARCHITECTURE.md`, when the run split the
  output across siblings.
- **`partsDir`**, if non-null. Assembly did not finish and the parts are still
  on disk.

## Rules

- Read-only except for writing/overwriting `ARCHITECTURE.md` at the scope root.
  Workflow mode may also write `ARCHITECTURE-*.md` siblings beside it, and uses
  a `.architecture-parts/` scratch directory that it removes once assembly
  succeeds — a scratch directory left behind means the run did not finish.
  Discovery and verifier subagents are read-only — brief them as such.
- If arguments are given, confine exploration and output to that scope; with no
  arguments, cover the whole repository and write to the working directory. Pass
  the resolved scope to every subagent so none strays outside it.
- Classify the project yourself; fan out the per-section discovery to parallel
  `Explore` subagents (all Task calls in one message); then synthesize. Require
  each subagent to return `file:line` plus a verbatim snippet for every claim,
  and spot-verify a sample of those citations yourself before writing.
- Size the mode in Step 3 and name it in the Step 4 report. Workflow mode needs
  the user's go-ahead first — it costs materially more than fan-out mode.
- In workflow mode the script writes the document; do not also write it. Its
  citations are already fully verified; do not re-verify them. Report the
  confirmed / corrected / refuted / unchecked tally in Step 7, keeping refuted
  and unchecked separate, and name any part that failed to generate.
- Tag every workflow-mode section `narrative` or `reference`, and give shards of
  one document section a shared `group`. Layout is decided before any writing
  starts, because writers emit links whose targets depend on it.
- `citationBase` passed to the script is absolute, `citationBaseLabel` is the
  same directory relative to the repository root, and only the label may appear
  in the document.
- Ground every claim in code with `[path:line](path#L42)` citations. Paths must
  be relative to the citation base (the directory containing the document) —
  never absolute, never starting with `/` or `~`, and never leaking a symlinked
  or machine-specific prefix. Flag guesses explicitly, and prefer reading code
  over README/docs when they disagree.
- Declare the citation base near the top of the document, expressed relative to
  the repository root (not as an absolute path).
- Report the resolved scope and detected project type before fanning out; write
  the document in one pass; print a summary plus open questions afterward.
- Emit only the section variants relevant to the detected project type; for
  full-stack projects, cover each side.
