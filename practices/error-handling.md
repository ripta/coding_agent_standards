# Error Handling Practices

## General Principles

- Always wrap errors with operation context before returning
- No silent failures; every error path must produce user-visible feedback
- No panics in library code; always return errors

## When to Fail Fast vs. Collect All

- **Fail fast** for runtime errors (I/O, network, database): return on first error with context
- **Collect all** for validation errors (config parsing, user input, schema checks): gather every error before returning so the user can fix them in one pass

## Error Wrapping

- Go: `fmt.Errorf("loading config for %s: %w", name, err)`
- Rust: structured error enum variants with `#[source]` and context fields
- Zig: capture error context in a struct field (source location, line, symbol)

## Sentinel Errors

- Define at package/module level for expected failure modes
- Go: `var ErrNotFound = fmt.Errorf("not found")`
- Rust: enum variants in a `thiserror`-derived type
- Zig: explicit error sets (`pub const FooError = error{ NotFound, ... }`)

## HTTP/RPC Error Responses

- Use structured JSON: `{"error": "message", "code": "ERROR_CODE"}`
- Map internal errors to appropriate status codes (400, 404, 429, 500, 503)
- Define a consistent set of error codes per service (INVALID_PARAMETER, TOO_MANY_REQUESTS, etc.)

## Validation Errors

- Collect all validation errors before returning (don't fail on the first one)
- Include source location (line, column, span) when parsing config or input
- Provide hints and suggestions (e.g., "did you mean X?" via Levenshtein distance)

## Logging Errors

- Use structured logging: `slog.Error("context", "key", value, "error", err)` (Go)
- Use `tracing::error!(error = %e, "context")` (Rust)
- Log at the handling site, not at the returning site (avoid double-logging)
