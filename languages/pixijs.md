# PixiJS Standards

Written against PixiJS v8. The v8 API changed substantially from v7. Verify
against the installed version on a major upgrade.

Use PixiJS when the project needs a 2D renderer and nothing else. Use
[`phaser.md`](./phaser.md) when it also needs scenes, input, and an asset
pipeline.

## Role in the Stack

- Pixi is a renderer. It owns the display list and nothing else.
- Game logic lives in the simulation layer and knows nothing about Pixi
- See [`game-simulation.md`](../practices/game-simulation.md) for the split and its enforcement
- Pixi supplies no scene lifecycle, input abstraction, or game loop discipline. Build those explicitly rather than letting them accrete in the ticker callback.

## Application

- Construct with `new Application()` then `await app.init({ ... })`. The v8 constructor takes no options.
- Mount `app.canvas` (v8 renamed it from `app.view`)
- One `Application` per page, created in `src/main.ts`
- Set `antialias: false` and `roundPixels: true` for pixel art
- Set `resolution: window.devicePixelRatio` and `autoDensity: true` for crisp output

## Scene Graph

- Group by logical layer: one `Container` per layer, added to `app.stage` in draw order
- Set `sortableChildren = true` only on containers that need it, then set `zIndex` on children. Sorting every container is wasted work.
- For isometric projection, derive `zIndex` from the projected y coordinate
- Build the graph once; mutate transforms per frame
- Never add or remove display objects per frame. Toggle `visible` instead.
- Destroy with `destroy({ children: true })` and drop every reference

## Ticker

- `app.ticker.add((ticker) => ...)`; the callback receives a `Ticker`, not a number
- The ticker drives rendering only. It does not advance the simulation directly.
- Accumulate `ticker.deltaMS` and run fixed simulation ticks from it
- Remove ticker callbacks when the owning object goes away

## Assets

- Load through `Assets`; no ad-hoc `fetch` for textures
- Declare a manifest and use `Assets.init({ manifest })` with named bundles
- Load bundles with `Assets.loadBundle(name)`; do not load textures one at a time
- Use texture atlases (`Spritesheet`), not loose images
- Keep asset aliases in one exported const object

## Sprites and Graphics

- `Sprite.from(alias)` for atlas frames; do not build textures at runtime in a loop
- v8 `Graphics` is verb-then-style: `g.rect(x, y, w, h).fill(color)`
- Rebuild a `Graphics` object only when its shape changes. Clearing and redrawing every frame is expensive.
- Prefer `ParticleContainer` for large counts of same-texture sprites

## Input

- Set `eventMode` explicitly (`"static"` for clickable, `"none"` for the rest). The default costs hit-testing on every object.
- Set `eventMode: "none"` on decorative layers
- Input produces intents. The simulation consumes intents on the next tick.
- Never mutate simulation state from an event handler.

## Commands

- Package manager: `pnpm`
- Build and dev server: Vite
- Type checking: `tsc --noEmit`
- Formatting and linting: Biome (see [`typescript.md`](./typescript.md))
- Tests: Vitest, in a node environment for simulation code
- Makefile wraps all of the above
