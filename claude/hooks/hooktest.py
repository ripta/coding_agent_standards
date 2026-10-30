"""Runs a PreToolUse shell hook for the hook tests. Run: uv run --with pytest pytest claude/hooks"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

HOOKS = Path(__file__).parent


def run_hook(
    name: str,
    command: str,
    *,
    tool: str = "Bash",
    cwd: Path | None = None,
    home: Path | None = None,
) -> str | None:
    """Feed one command to a hook. Return its deny reason, or None when it allows."""
    return run_tool_hook(name, tool, {"command": command}, cwd=cwd, home=home)


def run_tool_hook(
    name: str,
    tool: str,
    tool_input: dict,
    *,
    cwd: Path | None = None,
    home: Path | None = None,
) -> str | None:
    """Feed one tool call to a hook. Return its deny reason, or None when it allows."""
    payload: dict = {"tool_name": tool, "tool_input": tool_input}
    if cwd is not None:
        payload["cwd"] = str(cwd)
    env = dict(os.environ)
    if home is not None:
        env["HOME"] = str(home)
    result = subprocess.run(
        [HOOKS / name], input=json.dumps(payload), capture_output=True, text=True, env=env, check=True
    )
    if not result.stdout.strip():
        return None
    out = json.loads(result.stdout)["hookSpecificOutput"]
    assert out["hookEventName"] == "PreToolUse"
    assert out["permissionDecision"] == "deny"
    return out["permissionDecisionReason"]
