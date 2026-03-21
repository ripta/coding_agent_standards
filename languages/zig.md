# Zig Standards

## Naming

- Functions: `camelCase` (`nativeAdd`, `executeQuotation`)
- Types/Structs: `PascalCase` (`Context`, `Dictionary`, `Stack`)
- Constants/Enum values: `PascalCase` enum values (`.open_bracket`, `.close_bracket`)
- Module files: `snake_case` (`tokenizer.zig`, `stack_effect.zig`)

## Module Organization

- One type or concept per file
- Re-exports via `pub const` in parent modules
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
- Use `std.testing` for assertions in unit tests
- Run tests with `zig build test` or via Makefile targets

## Build System

- Use Makefile as the entry point; Makefile targets call `zig build` subcommands
- Build options via `addOptions()` for compile-time constants

## Sandbox and Standard Library Access

- Disable the sandbox when running build commands. The sandbox blocks access to
  Zig standard library files. If you see `PermissionDenied` errors for `std.zig`
  or similar, that is the sandbox.
- Note: There is currently no doc tool that allows querying the Zig stdlib from
  the command line. Once such a tool exists, this sandbox-disabling rule may be
  removable.

## Comments

- Doc comments: `///` before functions and types
- Preserve existing comment style and tone when editing
