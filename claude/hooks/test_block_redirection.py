"""Tests for block-redirection.sh. Run: uv run --with pytest pytest claude/hooks"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from hooktest import run_hook


def run(command: str, tool: str = "Bash") -> str | None:
    return run_hook("block-redirection.sh", command, tool=tool)


@pytest.mark.parametrize(
    ("command", "hint"),
    [
        ("ls > out.txt", "Shell redirection"),
        ("ls >> out.txt", "Shell redirection"),
        ("make 2>&1", "Shell redirection"),
        ("make 2> err.txt", "Shell redirection"),
        ("make &> all.txt", "Shell redirection"),
        ("make |& grep x", "Shell redirection"),
        ("git log | head", "head/tail"),
        ("git log | tail -n 5", "head/tail"),
        ("git log |head -3", "head/tail"),
    ],
)
def test_redirection_and_truncation_are_denied(command: str, hint: str) -> None:
    reason = run(command)
    assert reason is not None
    assert hint in reason


@pytest.mark.parametrize(
    "command",
    [
        "ls -la",
        "git log | grep head",
        "[ 3 -ge 2 ] && echo ok",
        "awk '$1 >= 2'",
        "awk '$1 <= 2'",
        "cat < in.txt",
        "make && make test",
    ],
)
def test_plain_commands_are_allowed(command: str) -> None:
    assert run(command) is None


def test_other_tools_are_ignored() -> None:
    assert run("ls > out.txt", tool="Edit") is None
