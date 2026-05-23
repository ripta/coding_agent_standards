---
name: architecture-exploration
description: |
  Use this skill to produce a deep, citation-grounded ARCHITECTURE.md for the
  current project by investigating the codebase. Detects the project type
  (backend service, frontend app, CLI, library, or full-stack) and tailors the
  reference to it. If invoked with arguments, scopes the exploration to that
  directory/crate/subproject. Read-only except for writing ARCHITECTURE.md.
model: opus
allowed-tools: Read, Glob, Grep, Bash, Write
---

You produce a deep technical reference document for a project's architecture by
investigating its code. You write the result to `ARCHITECTURE.md` (overwriting
if it exists) at the root of the explored scope. Apart from that one file, this
is a strictly read-only exploration — do not modify any other files.

## Workflow

### Phase 0: Determine Scope

If the skill was invoked with arguments, treat them as a scope restriction — a
directory, crate, subproject, package, or module. Confine all exploration,
citations, and output to that scope, and write `ARCHITECTURE.md` at the scope
root rather than the working directory.

If no arguments were given, the scope is the whole repository and
`ARCHITECTURE.md` goes in the current working directory.

Resolve the scope to a concrete path before continuing, and report it in Phase 2.

### Phase 1: Classify the Project

Inspect manifests (e.g. `package.json`, `go.mod`, `Cargo.toml`, `pyproject.toml`),
entrypoints, and the directory layout within scope to determine the project
type(s):

- **backend service** — exposes HTTP / RPC / GraphQL
- **frontend app** — SPA or SSR rendering a UI
- **CLI** — command-line tool
- **library / SDK** — consumed as a dependency via its exported API
- **full-stack** — more than one of the above

This classification drives which variant of each later section you emit. Prefer
reading code over README/docs when they disagree.

### Phase 2: Plan & Report

Before writing the file, briefly tell the user the resolved scope, the detected
project type(s), and a high-level outline of what you've discovered. Keep this
short — it confirms direction before the full pass.

### Phase 3: Write ARCHITECTURE.md

Write the full document in one pass as well-structured Markdown with a table of
contents and the sections below. Ground every claim in actual code with
`file:line` citations, using links of the form
`[path/to/file.ext:42](path/to/file.ext#L42)` where possible. If something is
ambiguous or you're guessing, say so explicitly.

Emit only the section variants relevant to the detected project type. For
full-stack projects, cover each side.

#### 1. Orientation (always)

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

### Phase 4: Summarize

After writing the document, print a short summary of what's in it and any open
questions you couldn't resolve from the code alone.

## Rules

- Read-only except for writing/overwriting `ARCHITECTURE.md` at the scope root.
- If arguments are given, confine exploration and output to that scope; with no
  arguments, cover the whole repository and write to the working directory.
- Ground every claim in code with `[path:line](path#L42)` citations. Flag
  guesses explicitly, and prefer reading code over README/docs when they
  disagree.
- Report the resolved scope and detected project type before writing; write the
  document in one pass; print a summary plus open questions afterward.
- Emit only the section variants relevant to the detected project type; for
  full-stack projects, cover each side.
