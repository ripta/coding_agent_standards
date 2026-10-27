"""Tests for rumdl/lint-markdown. Run: uv run --with pytest pytest tests"""

import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent.parent / "rumdl" / "lint-markdown"

pytestmark = pytest.mark.skipif(shutil.which("rumdl") is None, reason="rumdl is not installed")

FIXABLE = "# Title\n\n\n\nText.\n"
FIXED = "# Title\n\nText.\n"
UNFIXABLE = "# Title\n\nText with <b>inline html</b>.\n"


def make_repo(root: Path) -> Path:
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    (root / ".rumdl.toml").write_text("[MD013]\nline-length = 120\n")
    return root


def run(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([SCRIPT, *args], cwd=repo, capture_output=True, text=True)


def test_fix_on_named_files_touches_only_those_files(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    (repo / "named.md").write_text(FIXABLE)
    (repo / "other.md").write_text(FIXABLE)

    result = run(repo, "--fix", "named.md")

    assert result.returncode == 0, result.stdout + result.stderr
    assert (repo / "named.md").read_text() == FIXED
    assert (repo / "other.md").read_text() == FIXABLE


def test_fix_succeeds_when_an_unfixable_finding_remains(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    (repo / "html.md").write_text(UNFIXABLE)

    result = run(repo, "--fix", "html.md")

    assert result.returncode == 0, result.stdout + result.stderr
    assert (repo / "html.md").read_text() == UNFIXABLE


def test_check_on_named_files_still_fails_on_a_finding(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    (repo / "html.md").write_text(UNFIXABLE)

    assert run(repo, "html.md").returncode != 0


def test_named_files_that_are_not_markdown_are_skipped(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    (repo / "main.go").write_text("package main\n")

    result = run(repo, "--fix", "main.go")

    assert result.returncode == 0, result.stdout + result.stderr
    assert (repo / "main.go").read_text() == "package main\n"


def test_named_files_resolve_from_the_callers_directory(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    (repo / "docs").mkdir()
    (repo / "docs" / "note.md").write_text(FIXABLE)

    result = run(repo / "docs", "--fix", "note.md")

    assert result.returncode == 0, result.stdout + result.stderr
    assert (repo / "docs" / "note.md").read_text() == FIXED
