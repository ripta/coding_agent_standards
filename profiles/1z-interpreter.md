# 1z Interpreter Profile

@../profiles/baseline.md
@../languages/zig.md
@../languages/1z.md
@../practices/testing.md
@../practices/error-handling.md

## 1z Interpreter Build

- Build via `make` targets, not raw `zig build`
  - `make build` / `make release` for building
  - `make integration-test` / `make unit-test` / `make fmt-test` for tests
  - `make update-golden` / `make update-fmt-golden` for golden files
- Symlink standard library to `zig-out/lib/` so the interpreter can find it at runtime

## Stack Effect Comments in Zig

Use stack effect notation in Zig comments to document the 1z-level behavior of operations:

```zig
// ( a b -- sum )   adds top two stack values
fn nativeAdd(ctx: *Context) !void { ... }
```

## Module Organization

Primitive/operation modules export arrays that get aggregated in a `mod.zig`.
