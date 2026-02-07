# Zig Standards

## Naming

- Functions: `camelCase` (`nativeAdd`, `executeQuotation`)
- Types/Structs: `PascalCase` (`Context`, `Dictionary`, `Stack`)
- Constants/Enum values: `PascalCase` enum values (`.open_bracket`, `.close_bracket`)
- Module files: `snake_case` (`tokenizer.zig`, `stack_effect.zig`)

## Module Organization

- One type or concept per file
- Re-exports via `pub const` in parent modules
- Primitive/operation modules export arrays that get aggregated in a `mod.zig`
- Code organization within files: imports, helpers, public types, public arrays, implementation, tests

## Error Handling

- Define explicit error sets: `pub const FooError = error{ A, B, C }`
- Propagate with `try`; handle with `catch |err| { ... }`
- Capture error context in a struct field (source location, line number, word name)
- No silent failures; always surface errors to the user
- Use `anyerror!void` for functions that may return various error sets

## Memory Management

- Use `ArenaAllocator` for short-lived allocations (per-expression, per-statement)
- Use `GeneralPurposeAllocator` for long-lived data
- Wrap allocators with a `MemoryLimitAllocator` for hard memory caps
- Collections use `ArrayListUnmanaged` and `StringHashMapUnmanaged` (explicit allocator passing)
- Always `defer deinit()` immediately after allocation

## Testing

- Unit tests: embedded `test "description" { ... }` blocks at the bottom of source files
- Integration tests: golden file approach in `tests/integration/`
  - `*.stdin` for input, `*.stdout.golden` and `*.stderr.golden` for expected output
  - `*.flags` for per-test CLI flags, `*.exitcode` for expected exit codes
  - Update with `zig build update-golden`; validate no `FAIL:` appears in golden files
- Formatter tests: separate golden files in `tests/formatting/`

## Build System

- Use Makefile as the entry point; Makefile targets call `zig build` subcommands
- Dynamic test discovery: iterate test directory at build time via `build.zig`
- Symlink standard library to `zig-out/lib/`
- Build options via `addOptions()` for compile-time constants

## Comments

- Doc comments: `///` before functions and types
- Stack effect notation in comments: `( input -- output )`
- Preserve existing comment style and tone when editing
