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

## Commands the User Runs

Sometimes a command cannot run inside the session. The user then runs it,
either with `! <command>` in the prompt or in a separate terminal.

- A single self-contained command can be handed over as-is.
- When the work needs several commands, specific arguments, or a specific
  working directory, write a wrapper script instead. Do not ask the user to
  chain commands or `cd` somewhere first.
- The wrapper must work from any working directory. Resolve every path it
  needs inside the script.
- Put the wrapper in the scratchpad directory, or `$TMPDIR` when there is no
  scratchpad. Make it executable.
- Always give the user the absolute path to the script. Never give a path
  relative to an assumed directory.
- When you need the output, have the wrapper write stdout and stderr to a
  fixed file next to the script. Tell the user where it is, then read it
  yourself. Do not ask the user to copy and paste output back.
