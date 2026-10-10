# Makefile Practices

These rules apply to projects that have a Makefile. A project without one does not need to add one.

## Role

- The Makefile is the project's command entry point. Humans, agents, and CI all run `make <target>`.
- Agents call `make` targets, not the underlying toolchain (`cargo`, `go`, `pnpm run`, `uv run`).
- CI runs `make ci`, so local and CI runs execute the same commands.
- When a needed command has no target, add one rather than running the raw command repeatedly.
- The `makefile-helper` skill audits a Makefile against the checkable rules in this practice. Change its checklist
  when those rules change.

## Compatibility

- Write for GNU make. `MAKEFILE_LIST`, `?=`, and `.DEFAULT_GOAL` are GNU features.
- The floor is GNU make 3.81, which macOS ships.
- Avoid features newer than 3.81: `.ONESHELL`, `.RECIPEPREFIX`, `.SHELLFLAGS`, `!=`, `$(file ...)`, `undefine`, and
  grouped targets (`&:`).
- Recipes run under bash. Install it on minimal CI images such as Alpine.

## Header

Every Makefile opens with this block:

```make
SHELL := bash -o pipefail
.DEFAULT_GOAL := help
.DELETE_ON_ERROR:
.SUFFIXES:
MAKEFLAGS += --warn-undefined-variables
```

- `SHELL := bash -o pipefail` fails a recipe line when any command in a pipeline fails. Without it,
  `cargo test | tee test.log` passes when the tests fail.
- Name `bash`, not `/bin/bash`. Make finds it on `PATH`, and some systems such as NixOS have no `/bin/bash`.
- Do not use `.SHELLFLAGS` for this. It needs GNU make 3.82.
- `.DEFAULT_GOAL := help` makes a bare `make` print help. See [Default Goal and Help](#default-goal-and-help).
- `.DELETE_ON_ERROR:` deletes a file target when its recipe fails. Otherwise a half-written file looks up to date on
  the next run.
- `.SUFFIXES:` with no suffixes turns off make's built-in compile rules. These Makefiles run commands, so a built-in
  rule only causes surprises. One example is `cc` running on a stray `.c` file.
- `MAKEFLAGS += --no-builtin-rules` is not a substitute. GNU make 3.81 ignores it when it is set inside the Makefile.
- `--warn-undefined-variables` catches typos such as `$(TEST)` for `$(TESTS)`. It works only when every optional
  input is declared. See [Variables](#variables).
- `MAKEFLAGS` passes the flag to sub-makes. A `$(MAKE) -C` call into a third-party Makefile then prints its warnings
  too. Those warnings are noise, not findings.

## Default Goal and Help

- A bare `make` prints help. It never builds, tests, or changes anything.
- The header sets this explicitly. Do not rely on target order.
- The `help` target reads `##` comments out of every file in `MAKEFILE_LIST`:

```make
.PHONY: help
help: ## Show this help
	@awk 'BEGIN { FS = ":.*## " } \
		/^##@ / { printf "\n%s\n", substr($$0, 5) } \
		/^[a-zA-Z0-9_.\/-]+:([^=]|$$).*## / { printf "  %-24s %s\n", $$1, $$2 }' $(MAKEFILE_LIST)
```

- `awk` reads included files without prefixing filenames. `grep` without `-h` prefixes them once there is more than one
  file, which garbles the output.
- The target pattern allows digits, dots, and slashes. Targets like `build-arm64` and `dist/app` show up.
- The pattern skips variable assignments such as `FOO:=x`. Still, put `##` only on target lines. Any other line that
  starts with a name and a colon, such as `.PHONY:`, shows up in help when it carries `##`.
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
# Space-separated test-name substrings for test-select. Empty runs every test.
TESTS ?=

.PHONY: test-select
test-select: ## Run a subset of tests by name, e.g. make test-select TESTS='foo bar'
	cargo nextest run --workspace --no-tests=warn $(TESTS)
```

- Make merges repeated `.PHONY` declarations. Adding or removing a target touches one place.
- A shared list drifts. Targets get added without joining it.
- A target missing from `.PHONY` breaks once a file or directory with its name exists. Make reports it as up to date
  and runs nothing.
- Every target that does not produce a file named after itself is phony. That includes aggregates like `build` and
  `test`, which commonly collide with `build/` and `test/` directories.
- Real file targets (`dist/libfoo.a`) are not phony. Give them accurate prerequisites instead.

## Variables

- Tunable inputs use `?=` so the environment or command line can override them: `DAYS ?= 14`.
- Declare every input a recipe reads, even one that defaults to empty: `TESTS ?=`. That keeps
  `--warn-undefined-variables` quiet for intentional blanks.
- This includes variables only CI sets. Shell environment variables such as `HOME` are already defined.
- Put a one-line `#` comment above each tunable variable saying what it controls.
- Declare variables right after the header.
- Honor the toolchain's own variables instead of hard-coding paths. For example, use `CARGO_TARGET_DIR ?= target`
  rather than a literal `target/`.
- When the build embeds a version, spell it `VERSION`:

```make
# Version embedded in build artifacts. Override with make build VERSION=1.2.3.
VERSION ?= $(shell git describe --tags --always --dirty 2>/dev/null || echo dev)
```

- `--always` falls back to a commit hash when the clone has no tags. Shallow CI checkouts often have none.
- `|| echo dev` covers builds outside a git checkout, such as from a source tarball. `VERSION` is never empty.
- `?=` defers the `git` call until a recipe uses `VERSION`. `make help` does not run it.
- `?=` also re-runs `git` on every expansion. That is cheap for a few uses. A recipe that needs it many times binds it
  once to a shell variable.
- A `VERSION` already in the environment wins over `git`. CI or a container that sets `VERSION` for another purpose
  must unset it before running `make`.

## Target Vocabulary

Use these names when the project has the matching action. Do not invent synonyms for them.

| Target      | Does                                                                      |
|-------------|---------------------------------------------------------------------------|
| `help`      | Lists documented targets. The default goal.                               |
| `install`   | Installs project dependencies (`pnpm install`, `uv sync`).                |
| `build`     | Builds everything.                                                        |
| `dev`       | Runs the app locally with reload.                                         |
| `watch`     | Rebuilds or retests on file change.                                       |
| `test`      | Runs the default test suite.                                              |
| `bench`     | Runs benchmarks.                                                          |
| `check`     | Runs the type checker or compile-only check. Builds nothing to ship.      |
| `lint`      | Runs linters. Never modifies source files.                                |
| `fmt`       | Formats code in place.                                                    |
| `fmt-check` | Verifies formatting without modifying files.                              |
| `fix`       | Applies automatic lint fixes in place.                                    |
| `ci`        | Runs exactly what CI runs. Never modifies source or committed files.      |
| `clean`     | Removes build artifacts. Never removes source or committed files.         |

- `install` here means project dependencies. It does not copy a built program into a prefix, as in the GNU
  convention. A project that needs that uses `install-bin` or a similar name.
- Other verbs are fine when no listed name fits: `generate`, `coverage`, `preview`, `package`, `publish`, `release`.
  Use the plain verb. Do not add a second name for an action the table already covers.

Naming patterns for everything else:

- `<verb>-<component>` for a component-specific variant: `test-rust`, `lint-ui`, `build-cli`.
- `<verb>-select` for a run narrowed by a variable: `test-select TESTS='...'`.
- `update-<thing>` to regenerate a committed file such as a snapshot, schema, or golden file.
- `install-<tool>` to install an optional developer tool, named after the package: `install-cargo-sweep`.
- `clean-<scope>` for a narrower clean than `clean`: `clean-incremental`, `clean-stale`.

## Aggregate Targets

- Top-level verbs are aggregates over component targets: `build: build-rust build-ui`.
- An aggregate that only fans out has no recipe of its own. It only lists prerequisites.
- `ci` composes the read-only targets the project has, typically `ci: fmt-check lint check test`.
- `ci` must never depend on `fmt` or `fix`.
- With a single component, the top-level target may carry the recipe directly. Split it once a second component
  appears.
- Prerequisite order is not execution order. Under `make -j`, the prerequisites of `ci` run in parallel and their
  output interleaves. An aggregate whose steps must run in order calls them from its recipe instead:

```make
.PHONY: release
release: ## Build, test, then package, in that order
	$(MAKE) build
	$(MAKE) test
	$(MAKE) package
```

## Optional Tools

- A target that needs an optional tool checks for it first. When the tool is missing, it names the install target and
  fails:

```make
# Age cutoff for clean-stale, in days.
DAYS ?= 14

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
- Call make recursively as `$(MAKE)`, never a literal `make`. `$(MAKE)` passes `-j`, `-n`, and the jobserver through
  to the inner run.

## Splitting Large Makefiles

- Once a Makefile outgrows one screen of help output, move groups into `include`d files such as `mk/rust.mk` and
  `mk/tools.mk`.
- Each included file declares its own `##@` section and per-target `.PHONY` lines. `help` picks them up through
  `MAKEFILE_LIST`.
- Put `include` lines after the variable block so included files can use those variables.
