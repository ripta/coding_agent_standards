"""Tests for name-guardian.sh. Run: uv run --with pytest pytest claude/hooks"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

HOOK = Path(__file__).parent / "name-guardian.sh"


def run(prompt: str, title: str | None = None) -> str | None:
    """Return the session title the hook sets, or None when it leaves the session alone."""
    payload: dict = {"hook_event_name": "UserPromptSubmit", "prompt": prompt}
    if title is not None:
        payload["session_title"] = title

    result = subprocess.run([HOOK], input=json.dumps(payload), capture_output=True, text=True, check=True)
    if not result.stdout.strip():
        return None

    out = json.loads(result.stdout)["hookSpecificOutput"]
    assert out["hookEventName"] == "UserPromptSubmit"
    return out["sessionTitle"]


@pytest.mark.parametrize(
    ("prompt", "title"),
    [
        ("/guardian cas", "cas_guardian"),
        ("/coding-standards:guardian cas", "cas_guardian"),
        ("/coding-standards:guardian cas ~/projects/coding_agent_standards", "cas_guardian"),
        ("  /guardian team-notes.v2 claude/", "team-notes.v2_guardian"),
    ],
)
def test_a_domain_name_names_the_session(prompt: str, title: str) -> None:
    assert run(prompt) == title


def test_an_existing_title_is_replaced() -> None:
    assert run("/guardian cas", title="coding-agent-standards-3d") == "cas_guardian"


def test_a_matching_title_is_left_alone() -> None:
    assert run("/guardian cas", title="cas_guardian") is None


@pytest.mark.parametrize(
    "prompt",
    [
        "/guardian",
        "/coding-standards:guardian ",
        "/guardian ~/projects/coding_agent_standards",
        "/guardian /Users/me/projects/x",
        "/guardians cas",
        "/other:guardian cas",
        "please act as /guardian cas",
        "fix the guardian docs",
    ],
)
def test_other_prompts_are_ignored(prompt: str) -> None:
    assert run(prompt) is None
