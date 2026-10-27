# Bugs

Bugs this repo works around, most often in Claude Code itself. Each file is named `YYYYMMDD-short-name.md`, where the
date is when the bug was first observed. Each file carries a `**Status:**` line (`open`, `fixed`, or
`not-reproducible`), a repro, and the workarounds to keep or remove once it is fixed. `/bug-triage` re-verifies the
oldest open one.

| Bug | Status | Summary |
|---|---|---|
| [20261005-subagent-second-report-dropped](20261005-subagent-second-report-dropped.md) | open | A subagent's second report is refused after a follow-up joins a run kept open by background work |
| [20261027-fmt-hook-formats-wrong-repo](20261027-fmt-hook-formats-wrong-repo.md) | fixed | The format hook runs `make fmt` over the session's whole repo, whichever file was edited |
| [20261027-rumdl-fix-rewrites-unflagged-text](20261027-rumdl-fix-rewrites-unflagged-text.md) | fixed | rumdl's fix mode rewrites fenced markdown examples, and joins lines on a false MD038 |
