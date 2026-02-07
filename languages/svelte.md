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

## RPC Communication

- Use generated TypeScript clients from Protocol Buffer definitions
- Client factory in `src/lib/api/clients.ts` exports typed client getters
- Type safety end-to-end via shared `.proto` files
