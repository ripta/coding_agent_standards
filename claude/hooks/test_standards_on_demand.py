"""Tests for standards-on-demand.py. Run: uv run --with pytest pytest claude/hooks

These pin the hook's contract with Claude Code: which paths name which docs, that each group is
named once per session, and that compaction resets it. They cannot prove that Claude Code shows
the context to the model, or that the model then reads the docs.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

import pytest

HOOK = Path(__file__).parent / "standards-on-demand.py"
PM_DOCS = ["glossary.md", "proposals.md", "plans.md", "tracking.md", "design.md"]


@pytest.fixture
def env(tmp_path: Path) -> dict:
    home = tmp_path / "home"
    home.mkdir()
    return {**os.environ, "HOME": str(home), "CLAUDE_PLUGIN_ROOT": str(tmp_path / "plugin")}


def call(env: dict, payload: object) -> str | None:
    """Run the hook once. Return the context it adds, or None."""
    text = payload if isinstance(payload, str) else json.dumps(payload)
    result = subprocess.run([HOOK], input=text, capture_output=True, text=True, env=env, check=True)
    if not result.stdout.strip():
        return None
    out = json.loads(result.stdout)["hookSpecificOutput"]
    assert "permissionDecision" not in out, "the hook must never answer a permission prompt"
    return out["additionalContext"]


def tool(env: dict, path: Path | str, *, name: str = "Read", session: str = "s1") -> str | None:
    key = "notebook_path" if name == "NotebookEdit" else "file_path"
    payload = {
        "hook_event_name": "PreToolUse",
        "session_id": session,
        "tool_name": name,
        "tool_input": {key: str(path)},
    }
    return call(env, payload)


def named(context: str | None) -> list[str]:
    return [Path(line[2:]).name for line in (context or "").splitlines() if line.startswith("- ")]


@pytest.mark.parametrize(
    "relative",
    [
        "spec/proposals/APP-001-thing.md",
        "docs/proposals/queue.md",
        "spec/adrs/ADR-01-outbox.md",
        "design/decisions/adr-0007-events.md",
    ],
)
def test_project_management_files_name_the_pm_docs(env: dict, tmp_path: Path, relative: str) -> None:
    context = tool(env, tmp_path / "app" / relative)
    assert named(context) == PM_DOCS
    assert str(Path(env["CLAUDE_PLUGIN_ROOT"]) / "project-management" / "proposals.md") in context


@pytest.mark.parametrize("name", ["Makefile", "GNUmakefile", "rust.mk"])
def test_makefiles_name_the_makefile_practice(env: dict, tmp_path: Path, name: str) -> None:
    assert named(tool(env, tmp_path / "app" / name)) == ["makefile.md"]


@pytest.mark.parametrize("relative", ["src/main.go", "claude/project-management/proposals.md", "README.md"])
def test_other_files_add_nothing(env: dict, tmp_path: Path, relative: str) -> None:
    assert tool(env, tmp_path / "app" / relative) is None


def test_a_symlinked_spec_dir_matches_by_its_target(env: dict, tmp_path: Path) -> None:
    target = tmp_path / "private_specs" / "app" / "proposals"
    target.mkdir(parents=True)
    (target / "APP-001.md").write_text("x")
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "spec").symlink_to(target)
    assert named(tool(env, tmp_path / "app" / "spec" / "APP-001.md")) == PM_DOCS


@pytest.mark.parametrize("name", ["Edit", "Write", "MultiEdit", "NotebookEdit"])
def test_every_file_tool_triggers_it(env: dict, tmp_path: Path, name: str) -> None:
    assert tool(env, tmp_path / "spec" / "proposals" / "X.md", name=name) is not None


def test_each_group_is_named_once_per_session(env: dict, tmp_path: Path) -> None:
    proposal = tmp_path / "spec" / "proposals" / "A.md"
    assert tool(env, proposal) is not None
    assert tool(env, tmp_path / "spec" / "proposals" / "B.md", name="Edit") is None
    assert tool(env, tmp_path / "Makefile") is not None
    assert tool(env, proposal, session="s2") is not None


@pytest.mark.parametrize("source, renamed", [("compact", True), ("clear", True), ("resume", False)])
def test_compaction_and_clear_reset_the_session(env: dict, tmp_path: Path, source: str, renamed: bool) -> None:
    proposal = tmp_path / "spec" / "proposals" / "A.md"
    tool(env, proposal)
    call(env, {"hook_event_name": "SessionStart", "session_id": "s1", "source": source})
    assert (tool(env, proposal) is not None) == renamed


def test_session_start_prunes_stale_sessions(env: dict, tmp_path: Path) -> None:
    tool(env, tmp_path / "spec" / "proposals" / "A.md", session="old")
    tool(env, tmp_path / "spec" / "proposals" / "A.md", session="new")
    state = Path(env["HOME"]) / ".local" / "state" / "coding_agent_standards" / "on-demand"
    stale = time.time() - 8 * 24 * 3600
    os.utime(state / "old", (stale, stale))
    call(env, {"hook_event_name": "SessionStart", "session_id": "other", "source": "startup"})
    assert sorted(p.name for p in state.iterdir()) == ["new"]


@pytest.mark.parametrize("session", [None, "../escape"])
def test_an_unusable_session_id_names_the_docs_without_state(env: dict, tmp_path: Path, session) -> None:
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Read",
        "tool_input": {"file_path": str(tmp_path / "spec" / "proposals" / "A.md")},
    }
    if session is not None:
        payload["session_id"] = session
    assert call(env, payload) is not None
    assert not (Path(env["HOME"]) / ".local" / "state" / "coding_agent_standards" / "escape").exists()


@pytest.mark.parametrize("payload", ["not json", "[]", {"tool_name": "Bash", "tool_input": {"command": "ls"}}])
def test_input_it_cannot_use_adds_nothing(env: dict, payload: object) -> None:
    assert call(env, payload) is None
