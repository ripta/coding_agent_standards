"""Tests for block-config-access.py. Run: uv run --with pytest pytest claude/hooks"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from hooktest import HOOKS, run_tool_hook

HOOK = "block-config-access.py"


@pytest.fixture
def home(tmp_path: Path) -> Path:
    home = tmp_path / "home"
    (home / ".config" / "coding_agent_standards").mkdir(parents=True)
    (home / ".config" / "coding_agent_standards" / "session-report.json").write_text("{}")
    (home / ".config" / "gh").mkdir()
    (home / ".config" / "gh" / "hosts.yml").write_text("token")
    (home / "projects" / "app").mkdir(parents=True)
    return home


def run(home: Path, tool: str, tool_input: dict, cwd: Path | None = None) -> str | None:
    return run_tool_hook(HOOK, tool, tool_input, cwd=cwd or home / "projects" / "app", home=home)


@pytest.mark.parametrize(
    "tool, key",
    [
        ("Read", "file_path"),
        ("Edit", "file_path"),
        ("Write", "file_path"),
        ("MultiEdit", "file_path"),
        ("NotebookEdit", "notebook_path"),
        ("Grep", "path"),
        ("Glob", "path"),
    ],
)
def test_other_config_dirs_are_denied_to_every_file_tool(home: Path, tool: str, key: str) -> None:
    assert run(home, tool, {key: str(home / ".config" / "gh" / "hosts.yml")}) is not None


@pytest.mark.parametrize(
    "path",
    [
        "~/.config/gh/hosts.yml",
        "~/.config",
        "../../.config/gh",
        "~/.config/coding_agent_standards/../gh/hosts.yml",
        "~/.config/coding_agent_standards_evil/x.json",
    ],
)
def test_spellings_that_land_in_config_are_denied(home: Path, path: str) -> None:
    assert run(home, "Read", {"file_path": path}) is not None


def test_the_standards_directory_is_allowed(home: Path) -> None:
    allowed = home / ".config" / "coding_agent_standards"
    assert run(home, "Read", {"file_path": str(allowed / "session-report.json")}) is None
    assert run(home, "Write", {"file_path": str(allowed / "new.json")}) is None
    assert run(home, "Grep", {"path": str(allowed)}) is None
    assert run(home, "Glob", {"pattern": "~/.config/coding_agent_standards/*.json"}) is None


def test_paths_outside_config_are_allowed(home: Path) -> None:
    assert run(home, "Read", {"file_path": str(home / "projects" / "app" / "main.go")}) is None
    assert run(home, "Grep", {"pattern": "x"}) is None
    assert run(home, "Glob", {"pattern": "**/*.go"}) is None


def test_a_symlink_into_config_is_denied(home: Path) -> None:
    link = home / "projects" / "app" / "creds"
    link.symlink_to(home / ".config" / "gh")
    assert run(home, "Read", {"file_path": str(link / "hosts.yml")}) is not None


def test_a_symlinked_config_dir_is_still_guarded(tmp_path: Path) -> None:
    home = tmp_path / "home"
    dotfiles = tmp_path / "dotfiles" / "config"
    (dotfiles / "gh").mkdir(parents=True)
    (dotfiles / "coding_agent_standards").mkdir()
    home.mkdir()
    (home / ".config").symlink_to(dotfiles)
    assert run(home, "Read", {"file_path": str(dotfiles / "gh" / "hosts.yml")}, cwd=home) is not None
    assert run(home, "Read", {"file_path": str(home / ".config" / "gh" / "x")}, cwd=home) is not None
    assert run(home, "Read", {"file_path": str(dotfiles / "coding_agent_standards" / "a.json")}, cwd=home) is None


@pytest.mark.parametrize("tool", ["Grep", "Glob"])
def test_a_search_that_would_recurse_into_config_is_denied(home: Path, tool: str) -> None:
    assert run(home, tool, {"pattern": "**/*", "path": str(home)}) is not None
    assert run(home, tool, {"pattern": "**/*"}, cwd=home) is not None


@pytest.mark.parametrize("pattern", ["~/.config/**/*.yml", "~/.config/gh/*", "../../.config/*/hosts.yml"])
def test_a_glob_pattern_rooted_in_config_is_denied(home: Path, pattern: str) -> None:
    assert run(home, "Glob", {"pattern": pattern}) is not None


def test_other_tools_are_ignored(home: Path) -> None:
    assert run(home, "Bash", {"command": "cat ~/.config/gh/hosts.yml"}) is None


def test_malformed_input_is_denied(home: Path) -> None:
    result = subprocess.run(
        [HOOKS / HOOK], input="not json", capture_output=True, text=True,
        env={**os.environ, "HOME": str(home)}, check=True,
    )
    assert json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"
