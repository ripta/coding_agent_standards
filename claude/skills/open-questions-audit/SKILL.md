---
name: open-questions-audit
description: |
  Scan a project's in-flight proposals (those not yet finalized or closed) and
  rank them by the number of unresolved design questions. Reports the top
  proposals with the most open questions so design review can be prioritized.
model: haiku
allowed-tools: Read, Glob, Grep
---

You audit a project's proposals for unresolved design questions and rank them so design review effort can target the proposals carrying the most open decisions.

The canonical proposal format, lifecycle, and statuses live in `project-management/proposals.md` (in the coding-agent-standards repo). Always defer to a project-specific deviation when one exists.

## Workflow

### Phase 1: Locate Proposals

1. Find the proposals directory by checking common locations: `spec/proposals/`, `docs/proposals/`, `proposals/`. Use the first that exists and contains proposal files.
2. If an `index.md` exists in that directory, read it — its status table is the fastest way to see every proposal and its status. If there is no index, enumerate the proposal files directly (`<PREFIX>-NNN-*.md`).

### Phase 2: Select In-Flight Proposals

Collect every proposal whose status is **not** finalized or closed. Using the standard lifecycle in `project-management/proposals.md`, the closed/finalized statuses are:

`accepted`, `scheduled`, `implemented`, `rejected`, `superseded`, `retracted`

This leaves in-flight statuses where open questions still matter — typically `draft`, `designing`, and `deferred`. If the project defines its own statuses, exclude the ones that mean "design is finalized" or "no longer active" and keep the rest. When in doubt, keep a proposal in scope.

### Phase 3: Count Open Questions

For each in-flight proposal, read its file and count the **open design questions**. An open question is any of:

- A bullet or sub-heading under a "Design Decisions (Open)" section that is **not** struck through (`~~...~~`) and **not** marked as settled.
- A bullet under an "Open Questions" section, if the project uses one.

Handle both formats the proposal skills use: sub-heading questions (`### Question`) and bullet-list questions (`- **Question**: ...`).

Ignore items explicitly marked "(Settled)", "(none remaining)", struck through, or recorded as a "decision to defer" (these have moved to Settled per the proposals standard).

### Phase 4: Rank & Report

1. Rank proposals by open-question count, descending. Break ties arbitrarily.
2. Report the **top 5** (or all in-flight proposals if there are fewer than five) in a markdown table:

```markdown
| Rank | Proposal | Title | Status | Open Qs |
|------|----------|-------|--------|---------|
| 1 | PREFIX-NNN | ... | draft | 5 |
| 2 | PREFIX-NNN | ... | designing | 3 |
```

3. After the table, note the total number of in-flight proposals scanned and the proposals directory used.

## Rules

- Read-only audit: never modify proposals.
- Defer to `project-management/proposals.md` for the lifecycle and format, and to any project-specific deviation over the standard.
- Count only genuinely open questions; exclude settled, struck-through, and deferred-to-settled items.
- When a proposal's status is ambiguous, keep it in scope rather than dropping it silently.
