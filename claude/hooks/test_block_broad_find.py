"""Tests for block-broad-find.sh. Run: uv run --with pytest pytest claude/hooks"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from hooktest import run_hook

HOME = Path("/Users/me")


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
