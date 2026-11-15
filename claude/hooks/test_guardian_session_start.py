"""Tests for guardian-session-start.sh. Run: uv run --with pytest pytest claude/hooks"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

HOOK = Path(__file__).parent / "guardian-session-start.sh"


COMPLETE = {
    "checkout": "",
    "scopes": [],
    "commit_policy": {"branch": "main", "push": False, "style": "rules/commit-style.md"},
    "visibility": "public",
}


@pytest.fixture(autouse=True)
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point HOME at an empty directory, so the hook never reads the real saved domains."""
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


def save_domain(home: Path, name: str, entries: list) -> None:
    saved = home / ".local" / "state" / "coding_agent_standards" / "guardians" / name / "domain.json"
    saved.parent.mkdir(parents=True)
    saved.write_text(json.dumps({"entries": entries}))


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


def test_a_complete_saved_domain_is_reused_without_asking(home: Path) -> None:
    """Catches a restart that asks the user again for a domain it already saved."""
    checkout = home / "cas"
    checkout.mkdir()
    save_domain(home, "cas", [dict(COMPLETE, checkout=str(checkout))])

    context = run("clear", title="cas_guardian")

    assert str(checkout) in context
    assert '"visibility":"public"' in context
    assert "without asking" in context


def test_an_incomplete_saved_domain_names_only_what_is_missing(home: Path) -> None:
    """Catches a restart that asks for every setting when only some are missing."""
    checkout = home / "cas"
    checkout.mkdir()
    save_domain(home, "cas", [{"checkout": str(checkout), "scopes": []}])

    context = run("resume", title="cas_guardian")

    assert "has no commit_policy" in context
    assert "has no visibility" in context
    assert "ledger" in context
    assert "without asking" not in context


def test_no_saved_domain_falls_back_to_starting(home: Path) -> None:
    context = run("fork", title="cas_guardian")

    assert "no saved domain" in context
    assert "Starting" in context
