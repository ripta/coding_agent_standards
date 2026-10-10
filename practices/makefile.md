# Makefile Practices

## Role

- The Makefile is the project's command entry point. Humans, agents, and CI all run `make <target>`.
- Agents call `make` targets, not the underlying toolchain (`cargo`, `go`, `pnpm run`, `uv run`).
- CI runs `make ci`, so local and CI runs execute the same commands.
- When a needed command has no target, add one rather than running the raw command repeatedly.

## Compatibility

- Write for GNU make. `MAKEFILE_LIST`, `?=`, and `.DEFAULT_GOAL` are GNU features.
- The floor is GNU make 3.81, which macOS ships.
- Avoid features newer than 3.81: `.ONESHELL`, `.RECIPEPREFIX`, `!=`, `$(file ...)`, `undefine`, and grouped targets
  (`&:`).

## Default Goal and Help

- A bare `make` prints help. It never builds, tests, or changes anything.
- Set the default explicitly with `.DEFAULT_GOAL := help` at the top of the file. Do not rely on target order.
- The `help` target reads `##` comments out of every file in `MAKEFILE_LIST`:

```make
.DEFAULT_GOAL := help

.PHONY: help
help: ## Show this help
	@awk 'BEGIN { FS = ":.*## " } \
		/^##@ / { printf "\n%s\n", substr($$0, 5) } \
		/^[a-zA-Z0-9_.-]+:.*## / { printf "  %-24s %s\n", $$1, $$2 }' $(MAKEFILE_LIST)
```

- `awk` reads included files without prefixing filenames. `grep` without `-h` prefixes them once there is more than one
  file, which garbles the output.
- The target pattern allows digits and dots, so targets like `build-arm64` show up.
- A `##@ Section` line starts a heading in the help output. Group targets by purpose: Build, Test, Lint, Clean, Tools.

## Documenting Targets

- Every target a person is meant to run gets a one-line `## description` on the target line.
- Internal helper targets get no `##`, which keeps them out of help.
- A target driven by a variable shows an example invocation in its description:
  `## Run a subset of tests by name, e.g. make test-select TESTS='foo bar'`.
- A target that writes committed files says so: `## Regenerate trybuild snapshots (commit the result)`.
- Explanation longer than one line goes in a `#` comment block above the target or target group. Examples include
  choosing between related targets, prerequisites, and cost.

## Phony Targets

- Declare `.PHONY` on the line directly above each target. Never keep one shared list at the top of the file.

```make
.PHONY: test-select
test-select: ## Run a subset of tests by name, e.g. make test-select TESTS='foo bar'
	cargo nextest run --workspace --no-tests=warn $(TESTS)
```

- Make merges repeated `.PHONY` declarations. Adding or removing a target touches one place.
- A shared list drifts. Targets get added without joining it, and a file or directory with the same name then makes
  the target a silent no-op.
- Every target that does not produce a file named after itself is phony. That includes aggregates like `build` and
  `test`, which commonly collide with `build/` and `test/` directories.
- Real file targets (`dist/libfoo.a`) are not phony. Give them accurate prerequisites instead.

## Variables

- Tunable inputs use `?=` so the environment or command line can override them: `DAYS ?= 14`.
- Put a one-line `#` comment above each tunable variable saying what it controls.
- Declare variables at the top of the file, after `.DEFAULT_GOAL`.
- Honor the toolchain's own variables instead of hard-coding paths. For example, use `CARGO_TARGET_DIR ?= target`
  rather than a literal `target/`.

## Target Vocabulary

Use these names when the project has the matching action. Do not invent synonyms for them.

| Target      | Does                                                                    |
|-------------|-------------------------------------------------------------------------|
| `help`      | Lists documented targets. The default goal.                             |
| `install`   | Installs project dependencies (`pnpm install`, `uv sync`).              |
| `build`     | Builds everything.                                                      |
| `dev`       | Runs the app locally with reload.                                       |
| `watch`     | Rebuilds or retests on file change.                                     |
| `test`      | Runs the default test suite.                                            |
| `bench`     | Runs benchmarks.                                                        |
| `check`     | Runs the type checker or compile-only check, with no artifacts.         |
| `lint`      | Runs linters. Never modifies files.                                     |
| `fmt`       | Formats code in place.                                                  |
| `fmt-check` | Verifies formatting without modifying files.                            |
| `fix`       | Applies automatic lint fixes in place.                                  |
| `ci`        | Runs exactly what CI runs. Never modifies files.                        |
| `clean`     | Removes build artifacts. Never removes source or committed files.       |

Naming patterns for everything else:

- `<verb>-<component>` for a component-specific variant: `test-rust`, `lint-ui`, `build-cli`.
- `<verb>-select` for a run narrowed by a variable: `test-select TESTS='...'`.
- `update-<thing>` to regenerate a committed file such as a snapshot, schema, or golden file.
- `install-<tool>` to install an optional developer tool: `install-nextest`.
- `clean-<scope>` for a narrower clean than `clean`: `clean-incremental`, `clean-stale`.

## Aggregate Targets

- Top-level verbs are aggregates over component targets: `build: build-rust build-ui`.
- An aggregate has no recipe of its own. It only lists prerequisites.
- `ci` composes the read-only targets: `ci: fmt-check lint check test`. It must never depend on `fmt` or `fix`.
- With a single component, the top-level target may carry the recipe directly. Split it once a second component
  appears.

## Optional Tools

- A target that needs an optional tool checks for it first. When the tool is missing, it names the install target and
  fails:

```make
.PHONY: clean-stale
clean-stale: ## GC artifacts untouched for DAYS days, e.g. make clean-stale DAYS=7
	@command -v cargo-sweep >/dev/null || { echo "cargo-sweep not found; run: make install-cargo-sweep"; exit 1; }
	cargo sweep --time $(DAYS)
```

- Pin versions in `install-<tool>` targets, or use the versioned wrappers in `bin/` where the project has them.

## Recipes

- Echo commands by default. Use `@` only for output-only commands (`help`, tool checks) where the echo is noise.
- Keep recipes short. Move a recipe longer than a few lines, or one with real logic, into a script under `bin/` or
  `scripts/`, and call that script from the target.
- Each recipe line runs in its own shell. Join dependent commands with `&&` or a `\` continuation on one logical line.

## Splitting Large Makefiles

- Once a Makefile outgrows one screen of help output, move groups into `include`d files such as `mk/rust.mk` and
  `mk/tools.mk`.
- Each included file declares its own `##@` section and per-target `.PHONY` lines. `help` picks them up through
  `MAKEFILE_LIST`.
- Put `include` lines after the variable block so included files can use those variables.
