"""Tests for rumdl/lint-markdown. Run: uv run --with pytest pytest tests"""

import os
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


def fake_rumdl(tmp_path: Path, version: str) -> dict[str, str]:
    """Put a rumdl on PATH that reports version and records that it ran."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "rumdl"
    fake.write_text(f'#!/bin/sh\n[ "$1" = --version ] && {{ echo "rumdl {version}"; exit 0; }}\ntouch "{tmp_path}/ran"\n')
    fake.chmod(0o755)
    return {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"}


@pytest.mark.parametrize("version", ["0.1.52", "0.2.99"])
def test_a_rumdl_older_than_the_minimum_is_refused(tmp_path: Path, version: str) -> None:
    repo = make_repo(tmp_path / "repo")
    (repo / "note.md").write_text(FIXABLE)

    result = subprocess.run([SCRIPT, "--fix", "note.md"], cwd=repo, capture_output=True, text=True,
                            env=fake_rumdl(tmp_path, version))

    assert result.returncode != 0
    assert "brew upgrade rumdl" in result.stderr
    assert not (tmp_path / "ran").exists()


@pytest.mark.parametrize("version", ["0.3.0", "0.10.1", "1.0.0"])
def test_a_rumdl_at_or_past_the_minimum_runs(tmp_path: Path, version: str) -> None:
    repo = make_repo(tmp_path / "repo")
    (repo / "note.md").write_text(FIXABLE)

    result = subprocess.run([SCRIPT, "--fix", "note.md"], cwd=repo, capture_output=True, text=True,
                            env=fake_rumdl(tmp_path, version))

    assert result.returncode == 0, result.stderr
    assert (tmp_path / "ran").exists()
