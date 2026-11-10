# Terminal UI Practices

These apply to command-line output and full-screen terminal UIs. CLI profiles import this file without
`practices/ui-design.md`, so it stands on its own. Streams, `--output=json`, and exit codes are in the CLI profiles.

## Color

- Color only when stdout is a terminal. Check the stream you are writing to, not stdin.
- Honor `NO_COLOR`: when it is set to a non-empty value, emit no color. See <https://no-color.org>.
- Offer `--color=auto|always|never`, with `auto` as the default. An explicit flag beats `NO_COLOR`.
- Treat `TERM=dumb` as no color and no cursor movement
- Use the 16 basic ANSI colors for text. The user's terminal theme picks their values, so contrast follows the user's
  choice. A fixed 256-color or truecolor value can vanish on someone's background.
- Never use color alone to carry meaning. Pair it with a word or symbol: `error:`, `warning:`, `✓`, `✗`.
- Do not set a background color for body text. Bold and dim are safe for emphasis. Dim text must stay readable.

## Width and Layout

- Wrap help and prose to the terminal width, capped at about 100 columns. Fall back to 80 when the width is unknown.
- Never truncate data when stdout is not a terminal. Truncate only for display, and mark it with `…`.
- Align table columns. Right-align numbers, keep the same precision down a column, and show units in the header.
- Keep long lines and paths intact, so they can be copied. Do not insert a newline into an identifier.
- Use Unicode symbols and box drawing only when the locale is UTF-8. Fall back to ASCII otherwise.

## Progress and Feedback

- Write spinners and progress bars to stderr, and only when stderr is a terminal. Piped output stays clean.
- Show progress for any step that takes more than about a second. Use a count or a bar when the total is known.
- Clear a spinner when its step finishes, and leave one line saying what happened
- Update progress a few times a second at most. Fast redraws flood screen readers and remote sessions.
- Offer a plain mode, or detect a non-terminal, that prints each step once with no redraws

## Messages

- An error says what failed, why if known, and what to do next: the flag to pass, the file to fix, the command to
  run.
- Prefix diagnostics with the program name, so they are traceable in a pipeline
- Put the most important line last, just above the prompt, where the user will see it
- Do not print a stack trace for an expected error. Offer one behind `--verbose` or a debug variable.
- A destructive command asks before acting when stdin is a terminal, and needs `--yes` or `--force` when it is not

## Full-Screen TUIs

- Restore the terminal on every exit path: normal exit, error, panic, and signals such as SIGINT and SIGTERM. A
  crashed TUI must not leave the terminal in raw mode or the alternate screen.
- Use the alternate screen, so the user's scrollback survives
- Handle resize: redraw at the new size, and show a message instead of a broken layout when the window is too small
- Show the key bindings, at least `?` for help and `q` or Escape to quit, in a footer or a help screen
- Support the arrow keys as well as any vi-style bindings
- Show where focus is, with reverse video or a marker, not with color alone
- Offer a non-interactive equivalent for every action that scripts may need
