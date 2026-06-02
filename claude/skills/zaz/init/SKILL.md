---
name: init-zaz
description: |
  Scan the current project and generate a zaz.toml config file. Use when
  bootstrapping a new project to run under zaz. Automatically loads the zaz
  configuration reference and all worked examples as context.
model: sonnet
allowed-tools: Bash, Read, Write, Glob, Grep
---

@./configuration.md

You generate a `zaz.toml` for the current project by scanning its files and
applying the schema documented above.

## Workflow

### 1. Check for existing config

Look for `zaz.toml` or `zaz.json` in the current directory. If one exists,
read it and confirm with the user before overwriting.

### 2. Scan for project signals

Look for these files and directories in the project root:

- `Cargo.toml` — Rust; check `[[bin]]` entries and workspace members for
  binary names; check `[workspace]` for monorepo layout
- `go.mod`, `cmd/` subdirectory — Go; binary names come from `cmd/<name>/`
  subdirs; watch `**/*.go`, `go.mod`, `go.sum`
- `package.json` — Node/TypeScript; check `"scripts"` for `"start"`,
  `"dev"`, `"build"`, `"typecheck"`, `"lint"`; watch `src/**`
- `pyproject.toml`, `setup.py`, `requirements.txt` — Python
- `Makefile` — read targets; use them as task commands where appropriate
- `Dockerfile`, `docker-compose.yml` — hints about what services run
- Nested subdirectories that each contain one of the above — monorepo;
  create one group per service with `working_dir` set

Read whichever of these exist. Don't guess at contents; read them.

### 3. Classify each service

For each identifiable service or concern, decide:

- **Task**: runs to completion (fmt, lint, test, build). Use
  `on_change_only = true` for test/lint when they're slow and shouldn't
  run on startup.
- **Daemon**: long-running process that should stay up (server, watcher,
  vite, webpack, tailwind). Always prefer daemon over a task that loops.

Order tasks within a group to sequence naturally: format → lint → test →
build → (then the daemon picks up the result).

### 4. Choose watch patterns

Be specific:

- Match only the source files the group cares about.
- Always ignore `target/`, `build/`, `dist/`, `node_modules/`, test data,
  and generated files.
- Use `${zaz:dirs}` in test commands when the tool supports running a
  subset (e.g., `go test ${zaz:dirs}`).

For monorepo groups, scope patterns to the service subdirectory:
`services/api/**/*.go` not `**/*.go`.

### 5. Write the file

Emit the config as TOML. Add a one-line comment at the top describing the
project in the same style as the examples above. Write each group as an
`[[group]]` block with nested `[[group.task]]` and `[[group.daemon]]`
blocks indented with two spaces.

After writing, briefly explain each group: what it watches, what it builds,
and what daemon it keeps running.

## Rules

- Never overwrite `zaz.toml` without confirmation
- Always read manifest files; never guess at script names, binary paths, or
  target directories
- Prefer daemons over looping tasks for long-running processes
- Separate build tasks from the daemon that runs the result
- Use `depends_on` when groups must sequence (e.g., backend must build
  before frontend starts)
- Keep `debounce` at the default (100ms) unless the scan reveals a clear
  reason to change it (e.g., `package.json` uses vite, which saves burst
  files — 200ms is reasonable)
- Use `no_pty = true` only for tools that don't need color or interactive
  output (CI-style commands, JSON-output daemons)
- Name tasks and daemons from the command, not from the service name, so
  the TUI output is self-describing (`fmt`, `test`, `build`, `server`, not
  `api-build`, `api-run`)
