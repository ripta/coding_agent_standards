# Go Standards

## Naming

- Package names: lowercase, single word (`services`, `models`, `server`)
- Exported types/functions: PascalCase (`FeedService`, `NewTracker`)
- Unexported: camelCase (`subscribeFeed`, `writeError`)
- Constructor functions: `New*` prefix (`NewService`, `NewTracker`)
- No inline anonymous structs; always declare named types at package level

## Project Structure

- Entry point in `cmd/<name>/main.go`, minimal wiring only
- Application logic in `internal/` by default; use `pkg/` only when the package is explicitly intended for import by other Go modules
- Configuration parsed at command level, passed as structs via dependency injection
- Libraries never call `os.Getenv()`; config flows top-down from the command layer

## Error Handling

- Wrap errors with context: `fmt.Errorf("operation context: %w", err)`
- Early returns on error; never accumulate error variables
- Define sentinel errors at package level: `var ErrName = fmt.Errorf("description")`
- For RPC services: `connect.NewError(connect.CodeInternal, fmt.Errorf(...))`
- For HTTP handlers: structured JSON with `error` and `code` fields

## Configuration

- Environment variable prefix per project (e.g., `MYAPP_`)
- Typed getters: `getEnvString`, `getEnvInt`, `getEnvDuration`, `getEnvBool`
- Validation in a `Validate()` method on the config struct
- Boolean naming: `DISABLE_X` when enabled by default, `ENABLE_X` when disabled (zero value is valid)

## Concurrency

- Use `sync/atomic` with `CompareAndSwap` for check-then-increment (avoid TOCTOU races)
- Return release callbacks from acquire operations: `release, err := tracker.Acquire(op); defer release()`
- Use `errgroup` for concurrent operations with shared error handling
- Pass `context.Context` through all async operations

## Imports

- Group: stdlib, blank line, external, blank line, internal
- Use `goimports` with local prefix set to the module path

## Linting

- Use `golangci-lint` with a `.golangci.yml` config
- Never default to `//nolint`; fix the root cause
- Exclude generated code directories from linting
- Relax `funlen`, `gocyclo`, `dupl` for `_test.go` files

## Build

- Use Makefile targets; never raw `go` commands
- Version injection via ldflags: `-X 'pkg/version.Version=$(VERSION)'`
- Tool wrappers in `bin/` that auto-install versioned tools
- Use `modd` for development watch/rebuild

## Comments

- Comments before declarations, not inline
- Focus on WHY and non-obvious behavior; avoid restating what the code does
