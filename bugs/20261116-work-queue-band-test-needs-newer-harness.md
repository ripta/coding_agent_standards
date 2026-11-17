# The work-queue band test fails on a harness older than the one its fixtures were fixed for

**Status:** open

**Validation:** not confirmed as the cause; the harness version mismatch is the leading explanation, and was not
tested by switching harness versions

## Observed

`make test-plugin` fails on Claude Code 2.1.322. `claude/tests/work-queue-progress.test.ts` reports "no run leaves the
band to the engine" as failing: `ui.find({ type: 'Text', text: 'engine band' })` returns `undefined`. The other 8 tests
pass. It fails on the base commit too, in a clean worktree, so no working-tree change causes it.

## Cause

The fixtures were fixed for Claude Code 2.1.325. See `20261115-work-queue-band-test-missing-iscollapsed.md`. That fix
scoped the `engine` stub to `{ plugin: 'coding-standards' }`, because 2.1.325 asks each plugin for its own
`AbovePrompt` row. The machine that saw this failure runs 2.1.322, which is older. Under that harness the stub's scope
likely matches no row, so the engine band is never drawn.

## Repro

```sh
claude --version
make test-plugin
```

Expected: every test passes. Actual on 2.1.322: 8 pass, and "no run leaves the band to the engine" fails.

## Fix

A design call. The options:

- Require a minimum harness version for `test-plugin`, and have the target say which version it needs
- Make the `engine` stub work under both band models
- Treat it as a stale local install, and update Claude Code on the machine

## Workarounds

Update Claude Code to 2.1.325 or later before `make ci`. Nothing in the repo works around it.
