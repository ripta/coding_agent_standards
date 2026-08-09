# three.js Standards

Written against three.js r185. The library ships breaking changes on a monthly
cadence and publishes a migration guide per release. Pin the version and read
that guide before bumping it.

Use three.js when the project needs 3D. Use [`pixijs.md`](./pixijs.md) for 2D.

## Role in the Stack

- three.js is a renderer. It owns the scene graph and nothing else.
- Game logic lives in the simulation layer and knows nothing about three.js
- See [`game-simulation.md`](../practices/game-simulation.md) for the split and its enforcement
- three.js supplies no scene lifecycle, input abstraction, or asset pipeline
- Build those explicitly rather than letting them accrete in the animation callback

## Renderer

- One `WebGLRenderer` per page, created in `src/main.ts`
- Pass the existing canvas as `{ canvas }` rather than appending `renderer.domElement`
- A canvas already in the HTML gets the page's layout before the first frame
- Clamp the pixel ratio: `setPixelRatio(Math.min(devicePixelRatio, 2))`
- Above 2 the cost is quadratic and the gain is invisible
- Resize from a `ResizeObserver` on the canvas, not from a `window` resize listener
- On resize, call `setSize`, then set the camera's `aspect` and call `updateProjectionMatrix`
- `WebGPURenderer` lives behind the `three/webgpu` entry point and has its own material set
- Do not mix the two renderers in one project

## Colour Management

- Colour management is on by default. Leave it on.
- The working space is linear and `outputColorSpace` is sRGB. Both are defaults.
- Albedo, emissive, and specular textures are sRGB
- Normal, roughness, metalness, and ambient occlusion maps are linear
- `GLTFLoader` sets `colorSpace` correctly. A hand-loaded texture does not.
- Pick a tone mapping and set it once on the renderer. `ACESFilmicToneMapping` is the usual choice.
- A colour that looks wrong after a version bump is almost always a `colorSpace` on a
  hand-loaded texture

## Scene Graph

- Group by logical layer: one `Group` per layer, added to the scene in a fixed order
- Build the graph once; mutate transforms per frame
- Never add or remove objects per frame. Toggle `visible` instead.
- Set `matrixAutoUpdate = false` on anything static, then call `updateMatrix()` by hand when it moves
- Set `frustumCulled = false` only where a bounding volume lies about where the object is,
  such as a mesh moved by a vertex shader
- Never resolve a node by traversal at runtime. Resolve it once at load and hold the reference.
- `renderer.info.render.calls` and `renderer.info.memory` report what a frame costs
- Assert against those counters rather than trusting that nothing allocates

## Render Loop

- Drive frames with `renderer.setAnimationLoop(callback)`, not with a bare `requestAnimationFrame`
- It is the only loop that works under WebXR
- The loop drives rendering only. It does not advance the simulation directly.
- Accumulate the delta from one `Clock` and run fixed simulation ticks from it
- Stop the loop with `setAnimationLoop(null)` when the scene ends
- Hoist scratch `Vector3`, `Quaternion`, and `Matrix4` instances to module scope
- A vector allocated per object per frame is the most common source of collection pauses here

## Assets

- Load through a declared manifest with named bundles
- No ad-hoc `fetch` for models or textures
- Keep asset keys in one exported const object. Never hardcode a path at a call site.
- Pass one `LoadingManager` to every loader, for one place to track progress and catch failures
- glTF is the delivery format. `GLTFLoader` handles both `.gltf` and `.glb`.
- Loaders live in `three/addons/*`, which is unminified example code shipped in the package
- It is stable enough to depend on, and it is not covered by the library's deprecation policy
- Reach for `DRACOLoader` or `KTX2Loader` only when a measurement says the download is the problem
- Both add a decoder to the bundle
- `THREE.Cache.enabled = true` deduplicates fetches across loaders

## Models and Instances

- Load a model once and clone it per instance
- Loading the same file twice is a second copy on the GPU
- Clone a skinned mesh with `SkeletonUtils.clone()` from `three/addons/utils/SkeletonUtils.js`
- `Object3D.clone()` shares the skeleton, and every copy then animates as one
- A clone shares its source's geometry and material by default, which is what you want
- Clone a material only when an instance needs its own uniforms, and dispose that clone yourself
- Use `InstancedMesh` for hundreds of copies of one static mesh. It does not apply to skinned meshes.
- Pool anything that recurs. Build the pool at load, sized to a known ceiling.
- Hide a pooled object rather than removing it

## Materials and Lighting

- Prefer `MeshStandardMaterial`
- Reach for `MeshPhysicalMaterial` only for clearcoat, transmission, or sheen, which cost more
- Share one material across every object that looks alike
- Each distinct material is a shader program to compile, and a program switch between draws
- Sharing one does not lower the draw call count. Only `InstancedMesh` and `BatchedMesh` do that.
- Changing a material's structure at runtime needs `material.needsUpdate = true`
- Changing a colour or a scalar does not
- Keep the light count small and fixed. Each light recompiles the shaders that receive it.
- Enable shadows deliberately: `renderer.shadowMap.enabled`, then `castShadow` and
  `receiveShadow` per object
- Both default to off, and an object that does neither costs nothing
- Fit a directional light's `shadow.camera` to the area that needs shadows
- It is orthographic, and its default frustum is rarely the right one
- Shadow acne is a `shadow.bias` and `shadow.normalBias` problem
- Reach for those before raising the shadow map's size

## Animation

- One `AnimationMixer` per animated instance, driven by the frame delta
- Hold `AnimationAction` references from `mixer.clipAction(clip)`
- Resolving a clip by name every frame searches an array
- Cross-fade between actions rather than stopping one and starting another
- Clips loaded with a model belong to the file, not to the instance. One clip drives many mixers.
- Animation is presentation. A clip's playhead never feeds back into simulation state.

## Camera

- One `PerspectiveCamera`, constructed with the canvas aspect and updated on resize
- Keep `near` as far out and `far` as close in as the scene allows
- The depth buffer's precision is spent between them, and a near plane of 0.01 is where
  z-fighting comes from
- Camera movement is presentation. It reads simulation state and never writes it.

## Input

- Input produces intents. The simulation consumes intents on the next tick.
- Never mutate simulation state from an event handler.
- Raycast against a filtered list of candidates, never against the whole scene
- Register pointer listeners on the canvas, not on `window`, and remove them on teardown

## Teardown

three.js does not free GPU resources on garbage collection. Removing an object
from the scene frees nothing. Leaks here are silent until the context is lost.

- Every geometry, material, and texture a scene creates is disposed when that scene ends
- Register each disposable as it is created
- A teardown that traverses the graph at the end misses whatever was already detached
- Dispose a material's textures separately. `Material.dispose()` does not touch them.
- Do not dispose a shared resource from one of its users
- Ownership belongs to whatever created it
- Call `renderer.setAnimationLoop(null)` on shutdown, then `renderer.dispose()`
- Remove every listener, observer, and timer the scene registered

## Commands

- Package manager: `pnpm`
- Build and dev server: Vite
- Type checking: `tsc --noEmit`
- Types come from `@types/three`; the library does not ship its own
- Formatting and linting: Biome (see [`typescript.md`](./typescript.md))
- Tests: Vitest, in a node environment for simulation code
- Renderer code that needs a GL context is verified against a rendered frame, not in a unit test
- Makefile wraps all of the above
