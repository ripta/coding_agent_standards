"""Tests for block-gcloud-project-number.sh. Run: uv run --with pytest pytest claude/hooks"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from hooktest import run_hook, run_tool_hook

HOOK = "block-gcloud-project-number.sh"


@pytest.mark.parametrize(
    "command",
    [
        "gcloud builds describe b-1 --region=us-central1 --project=134954827775",
        "gcloud builds describe b-1 --project 134954827775 --region=us-central1",
        "gcloud builds log b-1 --project='134954827775'",
        'gcloud builds log b-1 --project "134954827775"',
        "gcloud builds describe b-1 --project=134954827775 --format='value(status)' 2>&1 | tail -3",
        "cd x && gcloud builds list --project=134954827775",
        "/usr/local/bin/gcloud builds list --project=134954827775",
        "gcloud config set project 134954827775",
        "gcloud config set core/project 134954827775",
        "CLOUDSDK_CORE_PROJECT=134954827775 gcloud builds list",
        "bash -c 'gcloud builds list --project=134954827775'",
    ],
)
def test_a_project_number_in_bash_is_denied(command: str) -> None:
    reason = run_hook(HOOK, command)
    assert reason is not None
    assert "gcloud projects describe 134954827775 --format='value(projectId)'" in reason


@pytest.mark.parametrize(
    "command",
    [
        "gcloud builds describe b-1 --project=my-proj-1",
        "gcloud builds describe b-1 --project my-proj-123456",
        "gcloud projects describe 134954827775 --format='value(projectId)'",
        "gcloud builds list --region=us-central1 --limit=10",
        "gcloud config set project my-proj",
        "python3 detect_era.py --project-root 123",
        "terraform plan -var project=134954827775 --project=134954827775",
        "grep -n gcloudrc --project=12",
        "gcloud builds describe b-1 --project=134954827775x",
    ],
)
def test_a_project_id_or_a_non_gcloud_command_is_allowed(command: str) -> None:
    """Catches a false positive. The plugin wires this hook for everyone, so these would recur."""
    assert run_hook(HOOK, command) is None


def test_cg_run_argv_with_a_number_is_denied() -> None:
    argv = ["gcloud", "builds", "describe", "b-1", "--project", "134954827775"]
    assert run_tool_hook(HOOK, "mcp__cg__cg_run", {"command": argv}) is not None


def test_cg_run_argv_with_an_id_is_allowed() -> None:
    argv = ["gcloud", "builds", "describe", "b-1", "--project=my-proj"]
    assert run_tool_hook(HOOK, "mcp__cg__cg_run", {"command": argv}) is None


def test_cg_run_env_with_a_number_is_denied() -> None:
    tool_input = {"command": ["gcloud", "builds", "list"], "env": {"CLOUDSDK_CORE_PROJECT": "134954827775"}}
    reason = run_tool_hook(HOOK, "mcp__cg__cg_run", tool_input)
    assert reason is not None
    assert "gcloud projects describe 134954827775" in reason


def test_cg_run_many_checks_every_command() -> None:
    commands = [["gh", "pr", "view"], ["gcloud", "builds", "log", "b-1", "--project=134954827775"]]
    assert run_tool_hook(HOOK, "mcp__cg__cg_run_many", {"commands": commands}) is not None


def test_other_tools_are_ignored() -> None:
    assert run_tool_hook(HOOK, "Write", {"content": "gcloud builds list --project=134954827775"}) is None


def test_the_plugin_wires_the_guard_on_bash_and_cg() -> None:
    """Catches the guard shipping unwired, or wired on Bash alone while gcloud also runs through cg."""
    config = json.loads((Path(__file__).parent / "hooks.json").read_text())
    matchers = [
        group.get("matcher", "")
        for group in config["hooks"]["PreToolUse"]
        for hook in group["hooks"]
        if hook["command"] == f'"${{CLAUDE_PLUGIN_ROOT}}"/hooks/{HOOK}'
    ]
    assert len(matchers) == 1
    assert set(matchers[0].split("|")) >= {"Bash", "mcp__cg__cg_run", "mcp__cg__cg_run_many"}
