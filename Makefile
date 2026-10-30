SHELL := bash -o pipefail
.DEFAULT_GOAL := help
.DELETE_ON_ERROR:
.SUFFIXES:
MAKEFLAGS += --warn-undefined-variables

# Directories pytest collects. Listed explicitly so agent worktrees under .claude/ stay out.
PYTEST_PATHS ?= claude tests

# Oldest Python the plugin scripts support. macOS ships it as /usr/bin/python3, which hooks may run.
PYTHON_FLOOR ?= 3.9

# Space-separated paths, relative to the repo root, for fmt-select. Empty formats nothing.
FILES ?=

.PHONY: help
help: ## Show this help
	@awk 'BEGIN { FS = ":.*## " } \
		/^##@ / { printf "\n%s\n", substr($$0, 5) } \
		/^[a-zA-Z0-9_.\/-]+:([^=]|$$).*## / { printf "  %-24s %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

##@ Test

.PHONY: test
test: test-python test-python-floor test-js test-plugin ## Run every test suite

.PHONY: test-python
test-python: ## Run the pytest suites, including the standards checker
	uvx --with pyyaml pytest -q $(PYTEST_PATHS)

.PHONY: test-python-floor
test-python-floor: ## Run the pytest suites under the oldest supported Python, PYTHON_FLOOR
	uvx --python $(PYTHON_FLOOR) --with pyyaml pytest -q $(PYTEST_PATHS)

.PHONY: test-js
test-js: ## Run the architecture-exploration workflow tests
	node claude/skills/architecture-exploration/workflow.test.mjs

# Needs the claude CLI. Validates the plugin manifest and runs the hooks module's tests.
.PHONY: test-plugin
test-plugin: ## Validate the coding-standards plugin and run its module tests
	@command -v claude >/dev/null || { echo "claude not found; install Claude Code"; exit 1; }
	claude plugin validate claude
	claude plugin test claude

##@ Lint

.PHONY: lint
lint: lint-md lint-prose ## Run the markdown and prose linters

.PHONY: lint-md
lint-md: ## Lint all markdown with rumdl
	./rumdl/lint-markdown --all

# Vale reports warnings without failing, and only on files changed against main. The full
# tree carries a backlog, so `vale/lint-prose --all` is a report, never a gate.
.PHONY: lint-prose
lint-prose: ## Lint prose and comments changed against main with Vale
	./vale/lint-prose

.PHONY: fmt
fmt: ## Fix markdown lint findings in place
	./rumdl/lint-markdown --all --fix

# The plugin's format hook calls this after each edit. See "Formatting Edited Files" in practices/makefile.md.
.PHONY: fmt-select
fmt-select: ## Fix markdown lint findings in the named files only, e.g. make fmt-select FILES='README.md'
	$(if $(FILES),./rumdl/lint-markdown --fix -- $(FILES))

##@ CI

.PHONY: ci
ci: lint test ## Run every check, read-only
