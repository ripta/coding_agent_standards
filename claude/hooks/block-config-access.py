#!/usr/bin/env python3
"""Deny the file tools any path under ~/.config except ~/.config/coding_agent_standards.

A PreToolUse hook for Read, Edit, Write, MultiEdit, NotebookEdit, Grep, and Glob.
setup_permissions.py registers it in the user's settings when the user's settings deny all of
~/.config.

A permission allow cannot carve an exception out of a permission deny, so a deny on all of
~/.config also blocks the skill preference files. This hook replaces that deny for the file
tools. The sandbox's denyRead covers Bash, which this hook never sees. Neither covers a file
the user attaches with an @ mention.

Paths are compared after resolving ~, .., and symlinks, so no spelling or link reaches past
the carve-out. A Grep or Glob rooted above ~/.config would recurse into it, so those are
denied too. Input the hook cannot read is denied, so a parse failure never opens the guard.
"""

import json
import os
import sys

FILE_KEYS = {
    "Read": "file_path",
    "Edit": "file_path",
    "Write": "file_path",
    "MultiEdit": "file_path",
    "NotebookEdit": "notebook_path",
}
SEARCH_TOOLS = ("Grep", "Glob")
GLOB_CHARS = set("*?[{")


def deny(reason: str) -> None:
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": reason,
    }}))
    sys.exit(0)


def resolve(path: str, base: str) -> str:
    return os.path.realpath(os.path.join(base, os.path.expanduser(path)))


def within(path: str, root: str) -> bool:
    return path == root or path.startswith(root.rstrip(os.sep) + os.sep)


def glob_root(pattern: str, base: str) -> str:
    """Return the directory a glob pattern starts from: its components before the first wildcard."""
    literal = []
    for part in os.path.expanduser(pattern).split(os.sep):
        if GLOB_CHARS & set(part):
            break
        literal.append(part)
    prefix = os.sep.join(literal)
    if pattern.startswith("~") or os.path.isabs(os.path.expanduser(pattern)):
        return os.path.realpath(prefix or os.sep)
    return resolve(prefix, base) if prefix else os.path.realpath(base)


def main() -> None:
    try:
        payload = json.load(sys.stdin)
        tool = payload.get("tool_name", "")
        tool_input = payload.get("tool_input") or {}
        cwd = payload.get("cwd") or os.getcwd()
    except (json.JSONDecodeError, AttributeError) as e:
        deny(f"block-config-access could not read the tool call ({e}), so it denies it.")

    home = os.path.expanduser("~")
    config = os.path.realpath(os.path.join(home, ".config"))
    allowed = os.path.realpath(os.path.join(home, ".config", "coding_agent_standards"))

    targets = []
    if tool in FILE_KEYS:
        path = tool_input.get(FILE_KEYS[tool])
        if isinstance(path, str) and path:
            targets.append(resolve(path, cwd))
    elif tool in SEARCH_TOOLS:
        path = tool_input.get("path")
        root = resolve(path, cwd) if isinstance(path, str) and path else os.path.realpath(cwd)
        pattern = tool_input.get("pattern")
        if tool == "Glob" and isinstance(pattern, str):
            root = glob_root(pattern, root)
        if within(config, root) and root != config:
            deny(
                f"{tool} from {root} would search {config}, which holds credentials. "
                "Narrow the path to a directory that does not contain it."
            )
        targets.append(root)

    for target in targets:
        if within(target, config) and not within(target, allowed):
            deny(
                f"{target} is under {config}, which holds credentials. "
                f"Only {allowed} is open to the file tools."
            )


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        deny(f"block-config-access failed ({type(e).__name__}: {e}), so it denies the call.")
