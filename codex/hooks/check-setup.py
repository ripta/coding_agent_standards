#!/usr/bin/env python3
"""Refresh the installed standards link and report setup gaps at session start."""

import os
import runpy
import shlex
import sys
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")).expanduser().resolve()
    # Refresh before checking so a new snapshot does not produce a stale-link warning.
    runpy.run_path(str(root / "hooks" / "link-current.py"))["link_current"](root, home)
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
