# Python CLI Profile

For Python command-line tools built with Typer.

@../profiles/baseline.md
@../languages/python.md
@../practices/testing.md
@../practices/error-handling.md
@../practices/security.md

## CLI Framework

- Use Typer for command parsing; Click is acceptable for existing projects
- Define the app as `app = typer.Typer()` in `cli.py`; register subcommands via `app.add_typer()` or `@app.command()`
- Set `no_args_is_help=True` on the top-level app

## Command Structure

- Each subcommand in its own module; expose a `typer.Typer()` instance or a `@app.command()` function
- Use type-annotated parameters: `name: Annotated[str, typer.Argument(help="...")]`
- Use `typer.Option()` with `--flag` style for optional parameters
- Use `typer.Exit(code=N)` for exit codes; raise `typer.Abort()` for user cancellation
- Use `callback()` on the parent app for shared options (verbosity, output format)

## I/O Conventions

- Data to stdout, diagnostics to stderr (`typer.echo(..., err=True)`)
- Support `--output=json` for machine-readable output; default to human-readable text
- Use `rich` for formatted terminal output (tables, progress bars, colors)
- Read from stdin when no file argument is given: `sys.stdin` or `typer.get_text_stream("stdin")`
- Exit codes: 0 success, 1 general error, 2 usage error

## Distribution

- Define `[project.scripts]` entry point in `pyproject.toml`
- Use `uv tool install .` for local development; `uv build` + `uv publish` for distribution
- Consider `shiv` or `zipapp` for single-file distribution when appropriate

## CLI Testing

- Test command functions directly by calling them with arguments, not by invoking subprocess
- Use `typer.testing.CliRunner` to capture output and exit codes
- Use `tmp_path` fixture for file I/O tests
- Golden file tests for complex output (see Testing Practices > Golden File Tests)

## CLI Security

- Sanitize file paths from user input; reject path traversal (`..`) in untrusted arguments
- Never pass user input to `subprocess.run()` with `shell=True`; use explicit argument lists
- Avoid logging secrets or embedding them in process arguments
- Enforce size limits when reading untrusted files or stdin
