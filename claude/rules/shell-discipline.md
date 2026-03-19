# Shell Discipline

## Shell Usage

- Do not chain multiple commands with pipes, `&&`, or `;` in a single shell
  invocation. Run each command separately so output is easier to read and
  failures are easier to identify.

## Debugging Tools

- `cg` is a wrapper command that annotates stdout/stderr of any command.
  Prefer `cg` over manually redirecting stdout/stderr to files.
  Do NOT use `2>&1` or any shell redirection with `cg` — it defeats the purpose.
  - `O:` = stdout, `E:` = stderr, `I:` = cg info (e.g., exit code).
  - Each line is timestamped.
  - Basic usage: `cg -- <command>` for line-by-line annotated output.
  - Capture mode: `cg --capture -- <command>` spools output to temp files
    and prints their paths. Read those files afterwards for full output.
  - Run `cg --help` for additional options.
  - Example: `cg -- ./zig-out/bin/1z --trace-modules file.1z | tail -n 20`
