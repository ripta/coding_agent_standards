# Go CLI Profile

For Go command-line tools built with Cobra.

@../profiles/baseline.md
@../languages/go.md
@../practices/testing.md
@../practices/error-handling.md
@../practices/security.md

## CLI Framework

- Prefer Cobra for command parsing; add a hypercmd wrapper when subcommand count reaches 4-6+
- Set `SilenceErrors: true` and `SilenceUsage: true` on the root command; handle error display in `main()`
- Register subcommands via `rootCmd.AddCommand(NewFooCommand())` in the root command factory

## Command Structure

- Each subcommand lives in its own file and exposes a `NewCommand() *cobra.Command` factory
- Define an options struct per command; bind flags in the factory, run logic as a method on the struct
- Use `RunE` (not `Run`) so errors propagate to the root error handler
- Use `PersistentFlags` on parent commands for shared state (verbosity, output format)
- Use `Args: cobra.ExactArgs(N)` or similar validators; don't manually check `len(args)` in `RunE`

## I/O Conventions

- Follow Unix conventions: data to stdout, diagnostics to stderr, read from stdin when no file args
- Support multiple input modes where appropriate: positional args, `--file` flag, and piped stdin
- Detect interactive vs piped mode with `golang.org/x/term.IsTerminal(int(os.Stdin.Fd()))`
- Offer `--output=json` (or `-o json`) for machine-readable structured output; default to human-readable text
- Use consistent exit codes: 0 success, 1 general error, 2 usage error; document any additional codes

## Version & Build Info

- Provide a `version` subcommand using a reusable `NewVersionCommand()` factory
- Populate version, commit, and date via ldflags at build time (see Go Standards > Build)
- Fall back to `debug.ReadBuildInfo()` for `go install`-built binaries where ldflags are absent

## Release & Distribution

- Use goreleaser for builds and release artifacts
- Cross-compile for linux/darwin on amd64/arm64 at minimum
- Include optional WASM targets when the tool is useful in browser or edge contexts
- Package as tar.gz archives; use brew taps or `go install` as primary install paths

## CLI Testing

- Test flag parsing and argument validation independently from command execution logic
- Capture stdout/stderr with `bytes.Buffer` injected via command `SetOut`/`SetErr`
- Use golden files for command output (see Testing Practices > Golden File Tests)
- Write compiled-binary integration tests that exec the built binary and assert on output and exit code

## CLI Security

- Sanitize file paths from user input; reject path traversal (`..`) in untrusted arguments
- Never pass user input unsanitized to `os/exec.Command` arguments; use explicit arg lists, not shell strings
- Avoid logging secrets or embedding them in process arguments visible via `ps`
- Enforce size limits when reading untrusted files or stdin to prevent memory exhaustion
- Validate numeric flag values against reasonable bounds; don't trust user-supplied sizes or counts
