"""Tests for block-broad-find.sh. Run: uv run --with pytest pytest claude/hooks"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from hooktest import run_hook, run_tool_hook

HOME = Path("/Users/me")
CG_RUN, CG_RUN_MANY = "mcp__cg__cg_run", "mcp__cg__cg_run_many"


def run(command: str, tool: str = "Bash") -> str | None:
    return run_hook("block-broad-find.sh", command, tool=tool, home=HOME)


@pytest.mark.parametrize(
    "command",
    [
        "find / -name x",
        "find /Users -name x",
        "find /Users/me -name x",
        "find /Users/me/ -name x",
        "find /Users/me/projects -name x",
        "ls && find / -name x",
    ],
)
def test_broad_roots_are_denied(command: str) -> None:
    assert run(command) is not None


@pytest.mark.parametrize(
    "command",
    [
        "find . -name x",
        "find /Users/me/projects/foo -name x",
        "find /Users/me/src -name x",
        "find /usr/local -name x",
        "echo find",
    ],
)
def test_narrower_roots_are_allowed(command: str) -> None:
    assert run(command) is None


def test_other_tools_are_ignored() -> None:
    assert run("find / -name x", tool="Edit") is None


def cg_run(argv: list | None, home: Path = HOME) -> str | None:
    return run_tool_hook("block-broad-find.sh", CG_RUN, {"command": argv, "cwd": ""}, home=home)


def cg_run_many(argvs: list, home: Path = HOME) -> str | None:
    return run_tool_hook("block-broad-find.sh", CG_RUN_MANY, {"commands": argvs, "cwd": ""}, home=home)


@pytest.mark.parametrize(
    "argv",
    [
        ["find", "/", "-name", "x"],
        ["find", "/Users", "-name", "x"],
        ["find", "/Users/me", "-name", "x"],
        ["find", "/Users/me/", "-name", "x"],
        ["find", "/Users/me/projects", "-name", "x"],
        ["bash", "-c", "find / -name x"],
        ["sh", "-c", "ls && find /Users/me -name x"],
    ],
)
def test_cg_run_denies_broad_roots(argv: list) -> None:
    """Catches the guard reading only Bash. rules/shell-discipline.md sends agents through cg_run."""
    assert cg_run(argv) is not None


@pytest.mark.parametrize(
    "argv",
    [
        ["find", ".", "-name", "x"],
        ["find", "/Users/me/projects/foo", "-name", "x"],
        ["find", "/usr/local", "-name", "x"],
        ["bash", "-c", "find /usr/local -name x"],
        ["echo", "find"],
        [],
        None,
    ],
)
def test_cg_run_allows_narrower_roots(argv: list | None) -> None:
    assert cg_run(argv) is None


def test_cg_run_many_checks_every_command() -> None:
    assert cg_run_many([["ls"], ["find", "/", "-name", "x"]]) is not None


def test_cg_run_many_allows_a_pool_with_no_broad_find() -> None:
    assert cg_run_many([["ls"], ["find", ".", "-name", "x"], ["echo", "/"]]) is None


def test_a_home_with_a_quote_still_gives_a_parseable_deny() -> None:
    """Catches a deny built by string interpolation. A path with a quote then breaks the JSON, and the
    harness reads the broken output as no decision, so the find runs."""
    home = Path('/Users/m"e')
    assert run_hook("block-broad-find.sh", 'find /Users/m"e -name x', home=home) is not None
    assert cg_run(["find", '/Users/m"e', "-name", "x"], home=home) is not None


def test_the_plugin_wires_the_guard_to_every_tool_it_reads() -> None:
    """Catches the guard wired to Bash alone. The cg tools then skip it."""
    config = json.loads((Path(__file__).parent / "hooks.json").read_text())
    matchers = [
        group["matcher"]
        for group in config["hooks"]["PreToolUse"]
        if any(h["command"].endswith("/hooks/block-broad-find.sh") for h in group["hooks"])
    ]

    for tool in ("Bash", CG_RUN, CG_RUN_MANY):
        assert any(re.fullmatch(m, tool) for m in matchers), f"{tool} is not matched by {matchers}"
