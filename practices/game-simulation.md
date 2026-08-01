# Game Simulation Practices

Applies to any game with a simulation that must run headless, reproducibly, or
faster than real time. Engine-agnostic by design.

## Simulation and Render Split

- `tick(dt)` mutates state. `render()` reads state and draws. Nothing does both.
- The simulation layer imports nothing from the engine, the DOM, or `window`
- Enforce that with a lint rule scoped to the simulation directory, not a convention
- Rendering derives from state every frame; it never caches state it can recompute
- Render-only values (tween offsets, camera shake, interpolation alpha) never feed back into the simulation

## Fixed Timestep

- The simulation advances in fixed increments. Frame time is not a simulation input.
- Accumulate real elapsed time, then run whole ticks until the accumulator drains
- Cap the number of catch-up ticks per frame so a stalled tab cannot spiral
- Interpolate between the last two states for rendering; do not interpolate the state itself
- A headless replay runs the same `tick()` with no frames at all

## Determinism

Determinism is a checklist, not an aspiration. Write the list down and test it.

- Iterate entities in stable id order, never in insertion or hash order
- Iterate any spatial query result in id order after collecting it
- Break every tie explicitly: by id, by declaration order, by a stored cursor
- No `Math.random()` in the simulation. Use a seeded PRNG whose state serialises.
- No `Date.now()` or `performance.now()` in the simulation. Time is the tick count.
- No floating-point accumulation where an integer counter would do
- Object iteration order over string keys is stable in JS, but do not rely on it. Sort explicitly.
- The round-robin cursor and the PRNG state are saved state, not runtime state

## System Order

- Systems run in a documented, fixed order every tick
- The order is load-bearing. Record it in the design doc and treat reordering as a design change.
- Each piece of state has exactly one owning system that writes it
- Where a second system must write, name the exception in the design doc and keep the list short
- Stub every system from day one, in order, even when empty. Later work fills a slot rather than choosing a place.

## Persistence

- The save carries the PRNG state and every cursor, or the same absence replays differently each load
- Stamp the save with a wall-clock timestamp at write time
- Version the save format from the first release; write the migration path before you need it
- Validate on load and refuse a save that fails an invariant. Do not silently repair it.
- Local storage only unless there is a server. There is no trustworthy client clock.

## Offline Progress

- Replay real ticks. Do not approximate with a formula.
- An approximation is a second code path that will disagree with the live simulation
- Cap replay duration; state the cap in the design doc
- Run the replay in a Web Worker so a long catch-up does not freeze the page
- Report progress to the main thread; a silent multi-second replay reads as a hang
- Know what bounds the replay cost and write it down. Unbounded catch-up is a design bug.

## Invariants

- Write invariants as prose in the design doc first, then convert each to a test
- Split them into content-time checks and runtime checks
- Content-time checks run at load and refuse to start on failure
- Runtime checks assert every tick in development builds and compile out of release builds
- Add each invariant alongside the build step that makes it checkable. Retrofitting a full suite finds violations that already look like features.

## Testing

- The core test: two runs of N ticks from one seed produce identical state
- Compare serialised state, not object identity. N should be large enough to expose drift.
- Round-trip the PRNG through serialisation and assert unchanged output
- Test systems against hand-built state, not against a running engine
- Simulation tests need no DOM. Run them in a node environment, not jsdom.
- A determinism failure is never flaky. Treat it as a hard bug and find the unordered iteration.
