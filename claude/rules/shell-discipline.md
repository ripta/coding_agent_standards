# Shell Discipline

## Shell Usage

- Do not chain multiple commands with pipes, `&&`, or `;` in a single shell
  invocation. Run each command separately so output is easier to read and
  failures are easier to identify.

## Running Commands

- Run commands through the `cg_run` MCP tool, or `cg_run_many` for several
  independent commands. Both capture stdout and stderr separately and truncate
  long output on their own, so redirecting with `>` or `2>&1` and piping into
  `head` or `tail` are unnecessary.
