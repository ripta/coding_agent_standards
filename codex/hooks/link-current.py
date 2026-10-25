#!/usr/bin/env python3
"""Keep the standards reference on the installed Codex plugin snapshot."""

import os
import sys
import tempfile
from pathlib import Path


def link_current(root, codex_home):
    root = root.resolve(strict=True)
    cache = (codex_home / "plugins" / "cache").resolve()
    if cache not in root.parents:
        raise ValueError("refusing to link a working tree; install the plugin first")
    if not (root / "baseline.md").is_file():
        raise ValueError(f"installed plugin has no baseline.md: {root}")
    link = codex_home / "coding-standards-current"
    if link.is_symlink() and link.resolve() == root:
        return
    if link.exists() and not link.is_symlink():
        raise ValueError(f"{link} exists and is not a symlink; leaving it unchanged")
    # A private temporary directory avoids collisions between simultaneous session starts.
    with tempfile.TemporaryDirectory(prefix=".coding-standards-", dir=codex_home) as temporary:
        pending = Path(temporary) / "current"
        pending.symlink_to(root, target_is_directory=True)
        os.replace(pending, link)


def main():
    codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    root = Path(os.environ.get("PLUGIN_ROOT", Path(__file__).resolve().parents[1]))
    link_current(root, codex_home)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError) as error:
        sys.exit(f"coding-standards: {error}")
