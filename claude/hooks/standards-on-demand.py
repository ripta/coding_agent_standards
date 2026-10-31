#!/usr/bin/env python3
"""Point the session at the standards a file needs, the first time it touches such a file.

A PreToolUse hook for Read, Edit, Write, MultiEdit, and NotebookEdit, and a SessionStart hook.
Profiles leave the project-management docs and makefile.md out of every session's startup
context, since most sessions never need them. This hook names them when a session first reads
or changes a proposal, an ADR, the queue, or a Makefile.

It names the files instead of inlining them. Hook context is capped at 10,000 characters, and
proposals.md alone is larger.

Each group is named once per session. The claim is a marker file under the state directory,
created with O_EXCL, so parallel tool calls name it only once. A SessionStart after compaction
or /clear removes the session's markers, since the docs left context with everything else.

Paths match on both their spelling and their resolved target. A spec/ directory is often a
symlink into another checkout, and Claude Code's own path-scoped rules miss files reached that
way. The hook never blocks a tool call, and fails silent.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
import time
from pathlib import Path

FILE_KEYS = {
    "Read": "file_path",
    "Edit": "file_path",
    "Write": "file_path",
    "MultiEdit": "file_path",
    "NotebookEdit": "notebook_path",
}

PM_DIRS = {"proposals", "adrs", "adr"}
ADR_FILE = re.compile(r"^adr-\d+.*\.md$", re.IGNORECASE)
MAKEFILES = {"Makefile", "makefile", "GNUmakefile"}

GROUPS = {
    "project-management": (
        "a proposal, ADR, or queue document",
        [
            "project-management/glossary.md",
            "project-management/proposals.md",
            "project-management/plans.md",
            "project-management/tracking.md",
            "project-management/design.md",
        ],
    ),
    "makefile": ("a Makefile", ["practices/makefile.md"]),
}

STATE = Path.home() / ".local" / "state" / "coding_agent_standards" / "on-demand"
# Session directories older than this are from sessions that ended long ago.
STALE_SECONDS = 7 * 24 * 3600
SESSION_ID = re.compile(r"^[A-Za-z0-9_-]+$")


def group_for(path: str) -> str | None:
    for spelling in {path, os.path.realpath(path)}:
        parts = Path(spelling).parts
        name = parts[-1] if parts else ""
        if PM_DIRS & {p.lower() for p in parts[:-1]} or ADR_FILE.match(name):
            return "project-management"
        if name in MAKEFILES or name.endswith(".mk"):
            return "makefile"
    return None


def session_dir(session_id: object) -> Path | None:
    if isinstance(session_id, str) and SESSION_ID.match(session_id):
        return STATE / session_id
    return None


def claim(directory: Path | None, group: str) -> bool:
    """Return True the first time this session claims the group."""
    if directory is None:
        return True
    directory.mkdir(parents=True, exist_ok=True)
    try:
        os.close(os.open(directory / group, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
    except FileExistsError:
        return False
    return True


def prune() -> None:
    cutoff = time.time() - STALE_SECONDS
    for child in STATE.iterdir() if STATE.is_dir() else []:
        if child.is_dir() and child.stat().st_mtime < cutoff:
            shutil.rmtree(child, ignore_errors=True)


def on_tool(payload: dict) -> str | None:
    key = FILE_KEYS.get(payload.get("tool_name", ""))
    path = (payload.get("tool_input") or {}).get(key) if key else None
    root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if not isinstance(path, str) or not root:
        return None

    group = group_for(path)
    if group is None or not claim(session_dir(payload.get("session_id")), group):
        return None

    kind, docs = GROUPS[group]
    listing = "\n".join(f"- {Path(root) / doc}" for doc in docs)
    return (
        f"{path} is {kind}. The coding standards for it load on demand. Unless they are already in "
        f"your context, read these with the Read tool before you change it:\n{listing}"
    )


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except (OSError, ValueError):
        return
    if not isinstance(payload, dict):
        return

    event = payload.get("hook_event_name", "PreToolUse")
    if event == "SessionStart":
        directory = session_dir(payload.get("session_id"))
        if directory is not None and payload.get("source") in ("compact", "clear"):
            shutil.rmtree(directory, ignore_errors=True)
        prune()
        return

    context = on_tool(payload)
    if context:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": event, "additionalContext": context}}))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
