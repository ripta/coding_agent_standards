# Svelte Standards

## Component Structure (Svelte 5 Runes)

- Props: `let { prop1, prop2 = default }: Props = $props()`
- State: `let variable = $state(initialValue)`
- Derived: `let derived = $derived(calculation)`
- Effects: `run(() => { sideEffect() })` (import `run` from `svelte/legacy`)
- Guard browser-only code with `browser` from `$app/environment`

## Project Structure

- Routes: `src/routes/` (SvelteKit file-based routing)
- Components: `src/lib/components/` (reusable)
- Stores: `src/lib/stores/` (writable/readable stores)
- Utilities: `src/lib/` (TypeScript utilities, API clients)
- Generated code: `src/gen/` (auto-generated, do NOT edit)

## State Management

- Use Svelte writable/readable stores for shared state
- Store factory pattern: `createFooStore()` returns `{ subscribe, ...methods }`
- Encode view state in URL hash for client-side routing

## Styling

- Use Tailwind CSS for utility-first styling
- Use a component library (e.g., Skeleton UI) for consistent design
- Comments before properties, same as Go/Proto standards

## Commands

- `pnpm` (not `npm`) for package management
- Type checking: `svelte-check`
- Linting: ESLint + Prettier
- Formatting: Prettier via `pnpm run format`

## Why Not Biome

Reviewed 2026-08-01 against Biome 2.5.

Plain TypeScript projects use Biome for both formatting and linting. See
[`typescript.md`](./typescript.md). Svelte projects stay on ESLint and Prettier
for three reasons.

- Biome's Svelte support is experimental. It landed in 2.3 and improved in 2.4. Full `.svelte` handling still requires opting in with `html.experimentalFullSupportEnabled`.
- `prettier-plugin-svelte` is the only formatter that handles Svelte templates reliably today.
- Biome has no equivalent to `eslint-plugin-svelte`, so the rune and template-a11y rules have no replacement.

Splitting by extension is not worth it. Biome for `.ts` plus Prettier for
`.svelte` buys little and costs a two-tool setup.

Revisit when Biome marks Svelte support stable.

## RPC Communication

- Use generated TypeScript clients from Protocol Buffer definitions
- Client factory in `src/lib/api/clients.ts` exports typed client getters
- Type safety end-to-end via shared `.proto` files
