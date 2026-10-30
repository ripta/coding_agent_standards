"""Tests for guardian-session-start.sh. Run: uv run --with pytest pytest claude/hooks"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

HOOK = Path(__file__).parent / "guardian-session-start.sh"


def run(source: str, title: str | None = None) -> str:
    """Return the context the hook adds, or an empty string when it adds none."""
    payload: dict = {"hook_event_name": "SessionStart", "session_id": "abc123", "source": source}
    if title is not None:
        payload["session_title"] = title

    result = subprocess.run([HOOK], input=json.dumps(payload), capture_output=True, text=True, check=True)
    if not result.stdout.strip():
        return ""

    out = json.loads(result.stdout)["hookSpecificOutput"]
    assert out["hookEventName"] == "SessionStart"
    return out["additionalContext"]


@pytest.mark.parametrize("source", ["resume", "clear", "fork"])
def test_a_returning_guardian_is_told_to_rerun_starting(source: str) -> None:
    context = run(source, title="cas_guardian")

    assert "cas_guardian" in context
    assert "/coding-standards:guardian cas" in context
    assert "Starting" in context


@pytest.mark.parametrize("source", ["startup", "compact"])
def test_other_sources_add_nothing(source: str) -> None:
    assert run(source, title="cas_guardian") == ""


@pytest.mark.parametrize("title", [None, "coding-agent-standards-3d", "_guardian", "a/b_guardian", "cas_guardians"])
def test_sessions_that_are_not_guardians_add_nothing(title: str | None) -> None:
    assert run("resume", title=title) == ""
