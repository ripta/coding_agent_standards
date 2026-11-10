# 1z Interpreter Profile

@../profiles/baseline.md
@../languages/zig.md
@../languages/1z.md
@../practices/error-handling.md

## 1z Interpreter Build

- Build via `make` targets, not raw `zig build`
  - `make build` / `make release` for building
  - `make test-integration` / `make test-unit` / `make test-fmt` for tests. These follow the vocabulary in
    `practices/makefile.md`. A 1z checkout that still has `integration-test`, `unit-test`, and `fmt-test` predates
    it: rename those targets and their callers to match.
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
