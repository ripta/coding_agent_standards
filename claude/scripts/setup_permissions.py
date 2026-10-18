#!/usr/bin/env python3
"""Bring the user's Claude Code settings in line with what the coding standards need.

    python3 setup_permissions.py [--settings FILE] [--check]

FILE defaults to ~/.claude/settings.json. The script adds the entries in MANAGED, removes
the entries in RETIRED, and drops exact duplicates from the permission and sandbox lists. It
never touches any other key.

--check reports what would change and never writes. It exits 1 when something would change,
so a hook can warn. Without --check the script writes, but only from a terminal outside a
coding agent, and only after the user confirms the diff.
"""

import argparse
import difflib
import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any

STATE_DIR = "~/.local/state/coding_agent_standards"

# Each key is a path into the settings JSON. Entries are added in this order after any the
# file already has.
MANAGED: dict[tuple[str, ...], list[str]] = {
    ("permissions", "allow"): [f"Edit({STATE_DIR}/**)"],
    ("sandbox", "filesystem", "allowWrite"): [STATE_DIR],
}

# Entries an earlier version of MANAGED added, and that no version needs any more. Move an
# entry here, rather than deleting it from MANAGED, so machines that have it lose it.
RETIRED: dict[tuple[str, ...], list[str]] = {}

DEDUPED_PARENTS = (("permissions",), ("sandbox", "filesystem"))


class SetupError(Exception):
    """A failure the user must act on; the message says what and where."""


def _node(settings: dict[str, Any], keys: tuple[str, ...], create: bool) -> dict[str, Any] | None:
    """Return the object at keys, or None when a key is missing or holds something else."""
    node = settings
    for key in keys:
        child = node.get(key)
        if child is None and create:
            child = node[key] = {}
        if not isinstance(child, dict):
            return None
        node = child
    return node


def _name(path: tuple[str, ...]) -> str:
    return ".".join(path)


def plan(settings: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Return the settings with every change applied, and one line per change."""
    new = json.loads(json.dumps(settings))
    changes: list[str] = []

    for parent_path in DEDUPED_PARENTS:
        parent = _node(new, parent_path, create=False)
        if parent is None:
            continue
        for key, value in parent.items():
            if not isinstance(value, list):
                continue
            seen: list[Any] = []
            for item in value:
                if item in seen:
                    changes.append(f"drop duplicate {_name(parent_path + (key,))}: {item}")
                else:
                    seen.append(item)
            parent[key] = seen

    for path, entries in RETIRED.items():
        parent = _node(new, path[:-1], create=False)
        if parent is None or not isinstance(parent.get(path[-1]), list):
            continue
        for entry in entries:
            if entry in parent[path[-1]]:
                parent[path[-1]].remove(entry)
                changes.append(f"remove retired {_name(path)}: {entry}")

    for path, entries in MANAGED.items():
        parent = _node(new, path[:-1], create=True)
        if parent is None:
            raise SetupError(f"{_name(path[:-1])} is not an object, so {_name(path)} cannot be set")
        current = parent.setdefault(path[-1], [])
        if not isinstance(current, list):
            raise SetupError(f"{_name(path)} is not a list")
        for entry in entries:
            if entry not in current:
                current.append(entry)
                changes.append(f"add {_name(path)}: {entry}")

    return new, changes


def render(settings: dict[str, Any]) -> str:
    return json.dumps(settings, indent=2, ensure_ascii=False) + "\n"


def load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        settings = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        raise SetupError(f"{path} is not valid JSON: {e}") from e
    if not isinstance(settings, dict):
        raise SetupError(f"{path} does not hold a JSON object")
    return settings


def write(path: Path, text: str) -> Path | None:
    """Replace the file in one step, keeping a timestamped backup beside it."""
    json.loads(text)
    backup = None
    if path.exists():
        backup = path.with_name(f"{path.name}.bak-{time.strftime('%Y%m%d-%H%M%S')}")
        shutil.copy2(path, backup)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    tmp.write_text(text)
    if backup is not None:
        shutil.copymode(backup, tmp)
    os.replace(tmp, path)
    return backup


def _refuse_unattended() -> None:
    # The user reviews every change to their settings. A coding agent must never apply them,
    # even when the user's permissions would let it write the file.
    if os.environ.get("CLAUDECODE"):
        raise SetupError("run this from your own terminal, not from inside a coding agent")
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        raise SetupError("run this from an interactive terminal, or pass --check to only report")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--settings", type=Path, default=Path.home() / ".claude" / "settings.json")
    parser.add_argument("--check", action="store_true", help="report what would change, and never write")
    args = parser.parse_args(argv)

    try:
        old = load(args.settings)
        new, changes = plan(old)
        if not changes:
            print(f"{args.settings} already has what the coding standards need.")
            return 0

        print(f"{args.settings} needs {len(changes)} change(s) for the coding standards:")
        for change in changes:
            print(f"  - {change}")
        if args.check:
            print("Run setup_permissions.py from your own terminal to apply them.")
            return 1

        _refuse_unattended()
        diff = difflib.unified_diff(
            render(old).splitlines(keepends=True) if args.settings.exists() else [],
            render(new).splitlines(keepends=True),
            fromfile=str(args.settings),
            tofile=f"{args.settings} (new)",
        )
        sys.stdout.writelines(diff)
        if input("Apply these changes? [y/N] ").strip().lower() not in ("y", "yes"):
            print("Nothing written.")
            return 1

        backup = write(args.settings, render(new))
        print(f"Wrote {args.settings}." + (f" The old file is at {backup}." if backup else ""))
        return 0
    except SetupError as e:
        print(f"setup_permissions: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
