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
| [20261115-skills-assume-origin-is-the-base-repo](20261115-skills-assume-origin-is-the-base-repo.md) | fixed | Four skills take the base repo from `origin`, which is the fork in a fork checkout |
| [20261115-work-queue-band-test-missing-iscollapsed](20261115-work-queue-band-test-missing-iscollapsed.md) | fixed | The work-queue progress band test fails, because `AbovePrompt` now requires `isCollapsed` |
| [20261116-work-queue-band-test-needs-newer-harness](20261116-work-queue-band-test-needs-newer-harness.md) | open | The work-queue band test fails on a harness older than the one its fixtures were fixed for |
| [20261121-preflight-may-read-unreadable-protection-as-none](20261121-preflight-may-read-unreadable-protection-as-none.md) | open | `pr_watch.py preflight` may report a non-admin's unreadable classic protection as no protection |
| [20261122-find-base-remote-takes-a-lone-fork-remote](20261122-find-base-remote-takes-a-lone-fork-remote.md) | open | `find_base_remote` returns a lone fork remote as the base repo, so tracker-sync reads the fork |
