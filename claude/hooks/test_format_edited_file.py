"""Tests for the PostToolUse format hook as hooks.json wires it. Run: uv run --with pytest pytest claude/hooks"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

PLUGIN = Path(__file__).parent.parent

MAKEFILE = """\
FILES ?=

.PHONY: fmt
fmt:
\t@echo fmt >> {log}
{select}"""

SELECT = """
.PHONY: fmt-select
fmt-select:
\t@echo fmt-select $(FILES) >> {log}
"""

FAILING_SELECT = """
.PHONY: fmt-select
fmt-select:
\t@echo "parse error in $(FILES)"; exit 1
"""


def hook_command() -> str:
    """Return the command hooks.json runs after an Edit or Write, so the test covers the wiring."""
    hooks = json.loads((PLUGIN / "hooks" / "hooks.json").read_text())["hooks"]["PostToolUse"]
    [entry] = [h for h in hooks if h["matcher"] == "Edit|Write"]
    [hook] = entry["hooks"]
    return hook["command"]


def make_repo(root: Path, log: Path, select: str | None = SELECT) -> Path:
    root.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    body = MAKEFILE.format(log=log, select=(select or "").format(log=log))
    (root / "Makefile").write_text(body)
    return root


def run(cwd: Path, file: Path) -> str:
    """Run the hook from cwd for an edit to file. Return its stdout."""
    payload = {"hook_event_name": "PostToolUse", "tool_name": "Edit", "cwd": str(cwd),
               "tool_input": {"file_path": str(file)}}
    env = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(PLUGIN))
    result = subprocess.run(["bash", "-c", hook_command()], input=json.dumps(payload), capture_output=True, text=True,
                            cwd=cwd, env=env, check=True)
    return result.stdout


def logged(log: Path) -> list[str]:
    return log.read_text().splitlines() if log.exists() else []


def test_an_edit_in_another_repo_formats_only_that_file_there(tmp_path: Path) -> None:
    session = make_repo(tmp_path / "session", tmp_path / "session.log")
    other = make_repo(tmp_path / "other", tmp_path / "other.log")
    (other / "docs").mkdir()
    edited = other / "docs" / "note.md"
    edited.write_text("# Note\n")

    run(session, edited)

    assert logged(tmp_path / "session.log") == []
    assert logged(tmp_path / "other.log") == ["fmt-select docs/note.md"]


def test_an_edit_through_a_symlinked_directory_formats_the_target_repo(tmp_path: Path) -> None:
    session = make_repo(tmp_path / "session", tmp_path / "session.log")
    other = make_repo(tmp_path / "other", tmp_path / "other.log")
    (other / "spec").mkdir()
    (session / "spec").symlink_to(other / "spec")
    edited = other / "spec" / "report.md"
    edited.write_text("# Report\n")

    run(session, session / "spec" / "report.md")

    assert logged(tmp_path / "session.log") == []
    assert logged(tmp_path / "other.log") == ["fmt-select spec/report.md"]


def test_an_edit_outside_any_repo_formats_nothing(tmp_path: Path) -> None:
    session = make_repo(tmp_path / "session", tmp_path / "session.log")
    (tmp_path / "loose").mkdir()
    edited = tmp_path / "loose" / "scratch.md"
    edited.write_text("# Scratch\n")

    run(session, edited)

    assert logged(tmp_path / "session.log") == []


def test_a_repo_without_fmt_select_is_never_formatted(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "repo", tmp_path / "repo.log", select=None)
    edited = repo / "README.md"
    edited.write_text("# Readme\n")

    assert run(repo, edited) == ""
    assert logged(tmp_path / "repo.log") == []


def test_a_path_with_whitespace_is_skipped(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "repo", tmp_path / "repo.log")
    edited = repo / "two words.md"
    edited.write_text("# Two\n")

    run(repo, edited)

    assert logged(tmp_path / "repo.log") == []


def test_a_successful_format_is_silent(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "repo", tmp_path / "repo.log")
    edited = repo / "README.md"
    edited.write_text("# Readme\n")

    assert run(repo, edited) == ""
    assert logged(tmp_path / "repo.log") == ["fmt-select README.md"]


def test_a_failed_format_is_reported_without_failing_the_hook(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "repo", tmp_path / "repo.log", select=FAILING_SELECT)
    edited = repo / "main.go"
    edited.write_text("package main\n")

    out = json.loads(run(repo, edited))["hookSpecificOutput"]

    assert out["hookEventName"] == "PostToolUse"
    assert "main.go" in out["additionalContext"]
    assert "parse error" in out["additionalContext"]
