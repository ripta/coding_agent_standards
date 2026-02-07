# Rust Standards

## Module Organization

- Private modules by default; selective re-exports via `pub use` in `lib.rs`
- One `error.rs` module per crate with domain-specific error types
- Flat module hierarchy within each crate
- Crate-level doc comments (`//!`) in every `lib.rs`

## Workspace

- Define all dependency versions in `[workspace.dependencies]`
- Individual crates reference with `.workspace = true`
- Separate crates by concern; keep dependency graph acyclic
- Use `resolver = "2"` in workspace `Cargo.toml`

## Error Handling

- Use `thiserror` for library/crate error types with `#[derive(Debug, Error)]`
- Use `anyhow::Result` only in the top-level binary for CLI propagation
- Include context in error variants: path, key, index, etc.
- For validation: collect all errors before returning using a `ValidationErrors` collection type
- Use `#[from]` for automatic conversion; `#[source]` for wrapping with context

## Naming

- Types: PascalCase (`DaemonError`, `ProcessState`)
- Functions: snake_case (`spawn_with_env`, `validate_config`)
- Constants: SCREAMING_SNAKE_CASE (`MAX_RETRIES`, `DEFAULT_SHELL`)
- Enum variants: PascalCase (`ProcessStatus::Running`)

## Patterns

- Builder pattern: `fn with_field(mut self, val: T) -> Self` for configuration structs
- Constructor: `fn new() -> Self` with `Default` implementation
- Display trait: implement for all user-facing types
- Serde: `#[serde(default, deny_unknown_fields)]` on config structs; `#[serde(alias = "...")]` for flexibility

## Testing

- Unit tests in `#[cfg(test)] mod tests` within the same file
- Integration tests in `tests/integration/`
- Assert on Display output for error messages

## Unsafe

- Minimize usage; only for system interactions (process groups, libc calls)
- Wrap immediately in safe abstractions
- Document the safety justification

## Formatting & Linting

- `.rustfmt.toml`: `edition = "2021"`, `max_width = 100`
- `clippy.toml`: set `msrv` to the minimum supported Rust version
- CI runs: `cargo fmt --check`, `cargo clippy --all-targets --all-features -- -D warnings`
- Makefile targets: `build`, `test`, `lint`, `fmt`, `fmt-check`, `ci`, `watch`
