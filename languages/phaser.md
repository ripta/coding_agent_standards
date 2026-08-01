# Phaser Standards

Written against Phaser 4. Verify API details against the installed version on a
major upgrade.

## Role in the Stack

- Phaser is rendering, input, and asset loading over plain data
- Game logic lives in the simulation layer and knows nothing about Phaser
- A Scene reads simulation state and draws it. It does not own state.
- See [`game-simulation.md`](../practices/game-simulation.md) for the split and its enforcement

## Scenes

- One class per Scene, one file per Scene, in `src/render/scenes/`
- Give every Scene an explicit string `key`; never rely on the class name
- Keep keys in one exported const object so transitions cannot typo a target
- Lifecycle: `init(data)` for parameters, `preload()` for loading, `create()` for building, `update(time, delta)` for per-frame work
- `update()` renders from state. It does not advance simulation time.
- Register teardown on `Phaser.Scenes.Events.SHUTDOWN`; remove every listener and timer you added
- Pass data between scenes through `scene.start(key, data)`, not through module-level variables

## Game Objects

- Build display objects once in `create()`; mutate them in `update()`
- Never create or destroy game objects per frame
- Set `depth` explicitly on anything that can overlap. For isometric projection, derive depth from the projected y coordinate.
- Group related objects in a `Container` so they transform together
- Destroy with `destroy(true)` to take children with it
- Prefer `setVisible(false)` over destroy for anything that will come back

## Pooling

- Pool anything spawned repeatedly: entities, particles, floating text
- Use `this.add.group({ classType, maxSize })` and `group.get()`
- Release with `killAndHide()`, not `destroy()`
- A pool that grows without bound is a leak. Set `maxSize` and handle exhaustion.

## Assets

- Load through the Scene loader in `preload()`; no ad-hoc `fetch` for game assets
- Use texture atlases, not loose images. One atlas per logical set.
- Keep asset keys in one exported const object alongside the scene keys
- Load shared assets in a dedicated boot or preload Scene that runs first
- Never hardcode an asset path at a call site

## Input

- Register input in `create()`; remove it on shutdown
- Prefer Scene-level `this.input.on("pointerdown", ...)` over per-object handlers when objects are numerous
- Input produces intents. The simulation consumes intents on the next tick.
- Never mutate simulation state from an input handler.

## Configuration

- One game config object in `src/main.ts`; nothing else constructs a `Phaser.Game`
- Set `type: Phaser.AUTO` unless a specific renderer is required
- Fix `width` and `height` as named constants; use a scale mode for responsiveness
- Disable `banner` in production builds if the console output matters

## Projection

- Isometric projection is hand-rolled; Phaser has no built-in isometric mode
- Keep the projection functions pure and in one module (`src/render/iso.ts`)
- Projection is a render concern. The simulation works in grid coordinates.
- Test projection round-trips: grid → screen → grid returns the original tile

## Physics

- Do not enable a physics system the game does not use. It costs a per-frame update.
- If the simulation owns movement, physics stays off entirely.

## Commands

- Package manager: `pnpm`
- Build and dev server: Vite
- Type checking: `tsc --noEmit`
- Formatting and linting: Biome (see [`typescript.md`](./typescript.md))
- Tests: Vitest, in a node environment for simulation code
- Makefile wraps all of the above
