"""Tests for block-zig-cache.sh. Run: uv run --with pytest pytest claude/hooks"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from hooktest import run_hook


def run(command: str, tool: str = "Bash") -> str | None:
    return run_hook("block-zig-cache.sh", command, tool=tool)


@pytest.mark.parametrize(
    ("command", "hint"),
    [
        (".zig-cache/o/abc/app", "Do not run binaries"),
        ("./.zig-cache/o/abc/app --help", "Do not run binaries"),
        ("timeout 30 .zig-cache/o/abc/app", "Do not run binaries"),
        ("zig build && .zig-cache/o/abc/app", "Do not run binaries"),
        ("rm -r .zig-cache", "Do not delete .zig-cache"),
        ("cd x; rm .zig-cache/o/abc/app", "Do not delete .zig-cache"),
    ],
)
def test_running_or_deleting_the_cache_is_denied(command: str, hint: str) -> None:
    reason = run(command)
    assert reason is not None
    assert hint in reason


@pytest.mark.parametrize(
    "command",
    [
        "./zig-out/bin/app",
        "zig build",
        "ls .zig-cache/o",
        "du -sh .zig-cache",
    ],
)
def test_other_commands_are_allowed(command: str) -> None:
    assert run(command) is None


def test_other_tools_are_ignored() -> None:
    assert run(".zig-cache/o/abc/app", tool="Edit") is None
