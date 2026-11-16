# The work-queue progress band test fails, because `AbovePrompt` now requires `isCollapsed`

**Status:** open

## Observed

`make ci` fails in `test-plugin`. `tests/work-queue-progress.test.ts` reports the test "a snapshot draws the band" as
failing. The engine's own band is still drawn, so `ui.find({ type: 'Text', text: 'engine band' })` returns a node, not
`undefined`. The type check fails in the same run: the props passed to the `AbovePrompt` mount lack `isCollapsed`, which
the mount target's type now requires.

It fails on the base commit too, so it is not caused by any change in this repo. The mod and its test last changed on
2026-10-17. The harness was Claude Code 2.1.325 when it was seen.

## Cause

Not confirmed. A newer Claude Code added a required `isCollapsed` prop to the `AbovePrompt` component. The test's
`band()` helper at `claude/tests/work-queue-progress.test.ts:27` builds the mount props without it. The hook's
`ui.render` handler at `claude/hooks/work-queue-progress.tsx:265` may also need to read it before it replaces the
engine's band.

## Repro

```sh
make test-plugin
```

Expected: every test passes. Actual: 8 pass, 1 fails, and TS2345 reports the missing `isCollapsed` at line 174.

## Fix

Add `isCollapsed` to the props `band()` builds. Then decide what the band does when the prompt area is collapsed. The
options are to draw the progress band anyway, to draw a one-line headline, or to leave the area to the engine. Check the
harness's mod docs for what `isCollapsed` means before choosing.
