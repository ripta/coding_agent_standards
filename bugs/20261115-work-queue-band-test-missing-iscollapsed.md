# The work-queue progress band test fails, because `AbovePrompt` now requires `isCollapsed`

**Status:** fixed 2026-11-15

**Fixed:** 2026-11-15

## Observed

`make ci` fails in `test-plugin`. `tests/work-queue-progress.test.ts` reports the test "a snapshot draws the band" as
failing. The engine's own band is still drawn, so `ui.find({ type: 'Text', text: 'engine band' })` returns a node, not
`undefined`. The type check fails in the same run: the props passed to the `AbovePrompt` mount lack `isCollapsed`, which
the mount target's type now requires.

It fails on the base commit too, so it is not caused by any change in this repo. The mod and its test last changed on
2026-10-17. The harness was Claude Code 2.1.325 when it was seen.

## Cause

Two harness changes, both in the test's fixtures. The hook is right.

The `AbovePrompt` props gained `isCollapsed`. The harness docs say a collapsed band still asks for its tree and only
hides it. So the hook needs no collapsed branch. The test's `band()` helper lacked the prop, which failed the type
check.

The band also became one row per plugin. Every plugin that hooks `AbovePrompt` is asked for its own row, and the test
counts as a plugin named `test`. The test's unscoped `engine` stub then drew a row beside the hook's row instead of
beneath it. "a snapshot draws the band" found that row and failed. "no run leaves the band to the engine" passed only
because of that row, so it no longer proved the fall-through.

The original guess follows. A newer Claude Code added a required `isCollapsed` prop to the `AbovePrompt` component. The
test's `band()` helper at `claude/tests/work-queue-progress.test.ts:27` builds the mount props without it. The hook's
`ui.render` handler at `claude/hooks/work-queue-progress.tsx:265` may also need to read it before it replaces the
engine's band.

## Repro

```sh
make test-plugin
```

Expected: every test passes. Actual: 8 pass, 1 fails, and TS2345 reports the missing `isCollapsed` at line 174.

## Fix

Fixed in `claude/tests/work-queue-progress.test.ts`. `band()` passes `isCollapsed: false`. The `engine` stub matches
`{ plugin: 'coding-standards' }`, so it answers only beneath the hook's row. A mutant hook that never falls through
now fails "no run leaves the band to the engine".

The original plan follows. Add `isCollapsed` to the props `band()` builds. Then decide what the band does when the
prompt area is collapsed. The options are to draw the progress band anyway, to draw a one-line headline, or to leave the
area to the engine. Check the harness's mod docs for what `isCollapsed` means before choosing.
