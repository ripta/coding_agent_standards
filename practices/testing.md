# Testing Practices

## Table-Driven Tests

- Declare a named test struct type at package level (not inline)
- Declare test cases as a package-level variable: `var fooTests = []fooTest{...}`
- Use subtests: `t.Run(test.Name, func(t *testing.T) { ... })`
- Each test case has a descriptive `Name` field

## Golden File Tests

- Store expected output alongside test input: `*.stdout.golden`, `*.stderr.golden`
- Provide an update mechanism: `update-golden` build step or flag
- Validate golden files don't contain failure markers (e.g., `FAIL:`)
- Support per-test configuration via sidecar files (`.flags`, `.stdin`, `.exitcode`)

## Handler/HTTP Tests

- Use `httptest.NewRequest` and `httptest.NewRecorder` (Go)
- Assert on status code, response body, and headers
- Create a `testConfig()` helper that returns a known-good config

## Testability Patterns

- Inject a clock interface (e.g., `clockwork.Clock`) for deterministic time control
- Use dependency injection; never call global state directly in tested code
- Return release/cleanup callbacks from setup functions

## Organization

- Unit tests live next to the code they test (same file in Zig/Rust, `_test.go` in Go)
- Integration tests in a dedicated `tests/` directory
- Test helpers grouped in a shared test utility (not duplicated across test files)

## Running the App by Hand

A test runner owns the process it starts, so it sees a crash. Launching the app by hand to check a change gives no such
guarantee. A crash in a detached process goes unnoticed.

- Start the app so the shell owns it. Run it in the foreground, or in the background with stdout and stderr sent to a log
  file and the PID saved.
- Avoid launchers that detach the process and drop its output, such as macOS `open`.
- After interacting with the app, check that the process is still alive. If it exited, read its exit status and the log.
- Scan the log for crash output: Go `panic:` or `fatal error:`, Rust `panicked at`, Python `Traceback`.
- A crash during a manual check is a failure. Report it with the trace. Do not report the change as verified.

## What to Test

- Public API behavior, not internal implementation details
- Error paths and edge cases
- Concurrency safety (track in-flight operations, verify cleanup)
- Run tests before completing any work: `make test lint`
