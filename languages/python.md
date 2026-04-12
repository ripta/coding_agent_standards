# Python Standards

## Naming

- Modules: lowercase with underscores (`feed_parser`, `http_client`)
- Classes: PascalCase (`FeedService`, `RetryPolicy`)
- Functions/variables: snake_case (`parse_entry`, `max_retries`)
- Constants: SCREAMING_SNAKE_CASE (`DEFAULT_TIMEOUT`, `MAX_BATCH_SIZE`)
- Private: single leading underscore (`_validate_input`, `_registry`)
- No dunder names outside of protocol/magic method implementations

## Project Structure

```
src/<package_name>/
  __init__.py
  py.typed              # PEP 561 marker
  models.py
  services.py
  exceptions.py
tests/
  conftest.py
  test_models.py
  test_services.py
pyproject.toml
Makefile
.python-version         # pinned via uv python pin
```

- Always use `src/` layout; never flat layout
- Entry points in `pyproject.toml` `[project.scripts]`, not a bare `if __name__` at the top level
- Configuration parsed at entry point, passed as typed objects via dependency injection
- Libraries never call `os.environ` directly; config flows top-down

## Type Hints

- Use builtin generics: `list[int]`, `dict[str, Any]`, `tuple[int, ...]`
- Use union syntax: `str | None`, `int | float`
- Use `Self` return type for fluent/builder methods
- Annotate all function signatures; omit obvious local variable annotations
- Use the `type` statement for complex aliases: `type UserID = int`
- Use `Protocol` for structural typing instead of ABC when only method signatures matter

## Error Handling

- Define a base exception per package: `class FeedError(Exception): ...`
- Derive specific exceptions: `class ParseError(FeedError): ...`
- Include context in exception messages: `raise ParseError(f"failed to parse {url}: {reason}")`
- Use `raise ... from err` to chain exceptions; never bare `raise ... from None` unless intentionally suppressing
- Use `match` for multi-error dispatch in handlers

## Imports

- Ruff manages import sorting (`isort`-compatible rules)
- Group: stdlib, blank line, third-party, blank line, local
- Prefer explicit imports: `from collections import defaultdict`
- No star imports; no `from __future__ import annotations` on 3.13+

## Dependencies & Environments

- Use `uv` exclusively; no pip, poetry, or pipenv
- `uv venv` to create, `uv run` to execute (prefer `uv run` over manual activation)
- `uv add <pkg>` for dependencies; `uv add --dev <pkg>` for dev dependencies
- Pin Python version with `uv python pin 3.13` (creates `.python-version`)
- Commit `uv.lock`; do not commit `.venv/`

## Formatting & Linting

- Use `ruff` for both formatting and linting; no black, flake8, or isort
- Configure in `pyproject.toml`:
  ```toml
  [tool.ruff]
  target-version = "py313"
  line-length = 100

  [tool.ruff.lint]
  select = ["E", "F", "W", "I", "UP", "B", "SIM", "RUF"]
  ```
- Makefile targets: `make fmt` (`uv run ruff format .`), `make lint` (`uv run ruff check .`), `make fix` (`uv run ruff check --fix .`)

## Build & Distribution

- Define metadata in `pyproject.toml` `[project]` table; no `setup.py` or `setup.cfg`
- Build with `uv build`; publish with `uv publish`
- Makefile targets: `make build`, `make publish`

## Testing

- Use `pytest` via `uv run pytest`
- Test files mirror source: `src/pkg/models.py` → `tests/test_models.py`
- Use fixtures in `conftest.py`; avoid deep fixture inheritance
- Parametrize over test cases with `@pytest.mark.parametrize` (table-driven equivalent)
- Makefile target: `make test` (`uv run pytest`)

## Comments & Docstrings

- Use `"""triple-double-quote"""` docstrings on public modules, classes, and functions
- First line is a single imperative sentence: `"""Parse a feed URL and return entries."""`
- Comments explain WHY, not WHAT; no restating the code
- Use `# TODO(name):` for tracked work; `# FIXME:` for known issues
