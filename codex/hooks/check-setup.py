#!/usr/bin/env python3
"""Refresh the installed standards link and report setup gaps at session start."""

import json
import os
import runpy
import shlex
import sys
from pathlib import Path


def session_source():
    """Return the SessionStart source Codex sent on stdin, or None when there is none."""
    if sys.stdin is None or sys.stdin.isatty():
        return None
    try:
        return json.loads(sys.stdin.read()).get("source")
    except (ValueError, AttributeError):
        return None


def main():
    root = Path(__file__).resolve().parents[1]
    home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")).expanduser().resolve()
    # Refresh before checking so a new snapshot does not produce a stale-link warning. A resumed,
    # compacted, cleared or forked thread keeps the snapshot it started with, so only a fresh start,
    # or hook input without a source, moves the link. The others only repair a missing link, then
    # check the linked snapshot, so the repair hint never names this thread's older setup.py.
    refresh = session_source() in (None, "startup")
    runpy.run_path(str(root / "hooks" / "link-current.py"))["link_current"](root, home, refresh=refresh)
    if not refresh:
        root = (home / "coding-standards-current").resolve()
    setup = runpy.run_path(str(root / "scripts" / "setup.py"))
    issues = setup["check"](root, home, Path.cwd())
    if issues:
        print("CODING STANDARDS SETUP:")
        for issue in issues:
            print(f"  - {issue}")
        print(f"Run: python3 {shlex.quote(str(root / 'scripts' / 'setup.py'))}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError) as error:
        sys.exit(f"coding-standards setup: {error}")
