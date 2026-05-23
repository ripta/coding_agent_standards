I want you to produce a deep technical reference document for this project's
architecture by investigating the codebase. Write the result to
`ARCHITECTURE.md` in the current working directory (overwrite if it exists). Do
not modify any other files — this is otherwise a read-only exploration.

Before writing the file, briefly tell me your plan and what you've discovered
at a high level. Then write the full document in one pass.

The document must be well-structured Markdown with a table of contents and the
following sections. Ground every claim in the actual code with `file:line`
citations (use links of the form `[path/to/file.ext:42](path/to/file.ext#L42)`
where possible). If something is ambiguous or you're guessing, say so
explicitly. Prefer reading code over README/docs when they disagree.

## 1. Orientation

- Language(s), framework(s), build/runtime tooling.
- How the API is exposed (HTTP server, RPC, CLI, SDK library, GraphQL, outbox
  views, etc.) and how it's versioned.
- Top-level directory map with the role of each significant folder.

## 2. API Surface Area

- A table of every public endpoint / exported function / command with: name,
  location (`file:line`), inputs, outputs, errors, auth/permissions.
- Flag anything internal, deprecated, or experimental.

## 3. Request/Response Lifecycle

- Pick 2–3 representative endpoints (one read, one write, one auth-sensitive if
  applicable).
- Trace each end-to-end: routing → middleware → validation → handler → business
  logic → data layer → response serialization → error paths, with `file:line`
  references at every hop.

## 4. Cross-cutting Concerns

- Authentication & authorization model
- Data model and persistence (schemas, migrations, ORMs)
- Validation, serialization, error-handling conventions
- Logging, metrics, tracing
- Configuration, secrets, feature flags
- Background jobs, queues, scheduled tasks, websockets/streams
- Rate limiting, caching, idempotency
- Testing strategy and exemplary tests for each API surface

## 5. Mental Model

- ASCII or Mermaid architecture diagram.
- The 5–10 abstractions/concepts to internalize to be productive.
- Non-obvious conventions and idioms.
- Known sharp edges, TODOs, or technical debt observed.

## 6. Onboarding Cheatsheet

- Exact commands to run the API locally and hit it (curl/SDK samples).
- Step-by-step recipe for adding a new endpoint following existing conventions,
  citing the files to touch.
- The 3 files to read first, in order, and why.

After writing the markdown document, print a short summary of what's in it and
any open questions you couldn't resolve from the code alone.

