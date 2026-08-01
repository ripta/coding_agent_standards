# TypeScript Standards

## Naming

- Types/interfaces/classes: PascalCase (`WorldState`, `StationKind`)
- Functions/variables: camelCase (`advanceTick`, `maxCarrySlots`)
- Constants: SCREAMING_SNAKE_CASE (`TICK_RATE_HZ`, `MAX_OFFLINE_TICKS`)
- Files: kebab-case (`task-selection.ts`, `world-state.ts`)
- No `I` prefix on interfaces; no `T` prefix on type aliases
- Enum-like values: prefer a string literal union over `enum`

## Project Structure

```
src/
  main.ts               entry point and wiring only
  <domain>/             pure logic, no I/O
  <adapter>/            framework, DOM, and platform edges
tests/                  integration and cross-module tests
index.html
vite.config.ts
tsconfig.json
biome.json
Makefile
```

- Entry point wires modules together; it holds no logic
- Keep pure domain code in its own directory with no framework imports
- Enforce that boundary with a lint rule, not a comment (see Formatting & Linting)
- Unit tests live next to the code (`foo.ts` → `foo.test.ts`); cross-module tests in `tests/`

## Types

- `strict: true` is non-negotiable; add `noUncheckedIndexedAccess` and `exactOptionalPropertyTypes`
- Annotate exported function signatures; let inference handle locals
- Use tagged unions for state that varies by kind, with a `kind` discriminant
- Use `satisfies` to check a literal against a type without widening it
- Never use `any`; use `unknown` and narrow
- Reserve `as` for cases the checker cannot see, with a comment saying why
- Use `readonly` on arrays and fields that must not be mutated after construction
- Model absence with `undefined`; avoid `null` unless an external API requires it

## Modules & Imports

- ESM only (`"type": "module"`); no CommonJS
- Use `import type { ... }` for type-only imports (`verbatimModuleSyntax` requires it)
- No barrel `index.ts` files; import from the defining module
- No default exports except where a framework demands one
- Biome's assist sorts imports; do not hand-order them

## tsconfig

Start from this and change it only with a reason:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "moduleResolution": "bundler",
    "moduleDetection": "force",
    "types": [],

    "strict": true,
    "noUncheckedIndexedAccess": true,
    "noImplicitOverride": true,
    "noFallthroughCasesInSwitch": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "exactOptionalPropertyTypes": true,

    "isolatedModules": true,
    "verbatimModuleSyntax": true,
    "esModuleInterop": true,
    "noEmit": true,
    "skipLibCheck": true
  },
  "include": ["src", "vite.config.ts"]
}
```

- The bundler emits; `tsc` only checks (`noEmit: true`)
- `types: []` keeps ambient `@types` packages out unless named explicitly

## Formatting & Linting

- Use Biome for both formatting and linting. No ESLint, no Prettier.
- Biome does not replace the type checker. `tsc --noEmit` stays in the gate.
- Biome has no type-aware rules, so anything requiring types is `tsc`'s job.
- Do not use Biome on `.svelte`, `.vue`, or `.astro` files. That support is still experimental. Those projects keep ESLint and Prettier.

Baseline `biome.json`:

```json
{
  "$schema": "https://biomejs.dev/schemas/2.5.6/schema.json",
  "vcs": { "enabled": true, "clientKind": "git", "useIgnoreFile": true },
  "formatter": {
    "enabled": true,
    "indentStyle": "space",
    "indentWidth": 2,
    "lineWidth": 100
  },
  "linter": { "enabled": true, "rules": { "preset": "recommended" } },
  "assist": { "actions": { "source": { "organizeImports": "on" } } },
  "javascript": { "formatter": { "quoteStyle": "double" } }
}
```

- Pin the `$schema` version to the installed Biome so config drift shows up as a schema error
- Enable `vcs.useIgnoreFile` so Biome respects `.gitignore`
- Biome defaults to tabs; the block above overrides that to two spaces

Enforce architectural boundaries with `overrides`. Both rules live in the `style` group:

```json
{
  "overrides": [
    {
      "includes": ["src/sim/**"],
      "linter": {
        "rules": {
          "style": {
            "noRestrictedImports": {
              "level": "error",
              "options": {
                "paths": {
                  "phaser": "The simulation layer must not import the engine."
                }
              }
            },
            "noRestrictedGlobals": {
              "level": "error",
              "options": {
                "deniedGlobals": {
                  "window": "The simulation runs in a Worker. There is no window.",
                  "document": "The simulation runs in a Worker. There is no document."
                }
              }
            }
          }
        }
      }
    }
  ]
}
```

- Biome 2.x uses a single `includes` array with `!` negation. There is no `include`/`ignore` pair.
- Migrating an existing project: `biome migrate eslint --write` and `biome migrate prettier --write`

## Dependencies

- Use `pnpm` exclusively. No npm, yarn, or bun.
- Commit `pnpm-lock.yaml`; pin the manager in `packageManager`
- Set an `engines.node` range and honour it
- Prefer zero-dependency solutions for anything under ~50 lines

## Build & Commands

- Build with Vite; test with Vitest
- A Makefile wraps the package scripts. Agents call `make`, not `pnpm run`.
- Targets: `install`, `dev`, `build`, `preview`, `check`, `test`, `lint`, `fmt`, `clean`
- `make check` runs `tsc --noEmit`; `make lint` runs `biome check .`; `make fmt` runs `biome check --write .`
- `build` runs the type check before bundling

## Comments

- Comments explain WHY, not WHAT
- Document non-obvious invariants at the definition, not the call site
- Use `// TODO(name):` for tracked work; `// FIXME:` for known issues
- No JSDoc type annotations; the types are in the signature
