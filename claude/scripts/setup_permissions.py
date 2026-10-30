#!/usr/bin/env python3
"""Bring the user's Claude Code settings in line with what the coding standards need.

    python3 setup_permissions.py [--settings FILE] [--check]

FILE defaults to ~/.claude/settings.json. The script adds the entries in MANAGED, and removes
the entries in RETIRED. When the settings deny reading all of ~/.config, it replaces that deny
with the config guard. See CONFIG_DENY_RULES. It also drops redundant entries:

- exact duplicates in the permission and sandbox lists
- permission rules that a broader rule in the same list already covers
- hooks listed twice, and user hooks that run a standards script the plugin already runs

It never touches any other key.

--check reports what would change and never writes. It exits 5 when a managed entry is
missing, so a hook can warn, and 3 when only redundant entries would go. It exits 4 when the
settings are complete but the config guard's script is missing. None of these is 1, which
Python itself exits with on an uncaught exception, so a hook never mistakes a crash for missing
entries.

Without --check the script writes, but only from a terminal outside a coding agent, and only
after the user confirms the diff.
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path
from typing import Any

STATE_DIR = "~/.local/state/coding_agent_standards"
# nitipan keeps its own state directory, so it works without the standards installed. Its
# CLI runs under the sandbox when a session calls it through Bash.
NITIPAN_STATE_DIR = "~/.local/state/nitipan"
# Skill preference files and the private-terms list. Users may deny reading all of ~/.config,
# since it holds credentials, so this one directory is carved back out of the sandbox.
#
# Sessions may write the preference files, which are JSON, through the Write and Edit tools.
# The glob leaves out private-terms.txt, so changing that list still needs the user's approval.
# Bash stays unable to write anywhere under ~/.config.
CONFIG_DIR = "~/.config/coding_agent_standards"

# Each key is a path into the settings JSON. Entries are added in this order after any the
# file already has.
MANAGED: dict[tuple[str, ...], list[str]] = {
    ("permissions", "allow"): [
        f"Edit({STATE_DIR}/**)",
        f"Edit({NITIPAN_STATE_DIR}/**)",
        f"Read({CONFIG_DIR}/**)",
        f"Edit({CONFIG_DIR}/*.json)",
    ],
    ("sandbox", "filesystem", "allowWrite"): [STATE_DIR, NITIPAN_STATE_DIR],
    ("sandbox", "filesystem", "allowRead"): [CONFIG_DIR],
}

# A permission allow cannot carve an exception out of a permission deny. So a deny on all of
# ~/.config also blocks CONFIG_DIR, whatever MANAGED allows. Settings that hold such a deny get
# the config guard in its place. For Bash, it is a sandbox denyRead, which allowRead can carve.
# For the file tools, which the sandbox does not cover, it is a PreToolUse hook.
#
# The guard is not added to settings without that deny. A sandbox deny on ~/.config would break
# tools such as git and gh that read their own config there.
CONFIG_DENY_RULES = ("Read(~/.config/**)", "Read(~/.config)", "Read(~/.config/)")
CONFIG_DENY_READ = "~/.config"
CONFIG_GUARD_MATCHER = "Read|Edit|Write|MultiEdit|NotebookEdit|Grep|Glob"
CONFIG_GUARD_SCRIPT = "hooks/block-config-access.py"
CONFIG_GUARD_COMMAND = f'"$HOME"/.claude/coding-standards-current/{CONFIG_GUARD_SCRIPT}'

# Entries an earlier version of MANAGED added, and that no version needs any more. Move an
# entry here, rather than deleting it from MANAGED, so machines that have it lose it.
RETIRED: dict[tuple[str, ...], list[str]] = {}

DEDUPED_PARENTS = (("permissions",), ("sandbox", "filesystem"))
RULE_LISTS = ("allow", "deny", "ask")
RULE = re.compile(r"^([\w-]+)(?:\((.*)\))?$")

PLUGIN_HOOKS = Path(__file__).resolve().parent.parent / "hooks" / "hooks.json"
PLUGIN_SCRIPT = re.compile(r"^\$\{CLAUDE_PLUGIN_ROOT\}/(hooks/\S+)$")
# Every place a user's settings may run a standards hook script from: a clone, the link the
# plugin maintains, or a cached plugin version.
STANDARDS_SCRIPT = re.compile(
    r"^~/(?:projects/coding_agent_standards/claude|coding-standards/claude|\.claude/coding-standards-current"
    r"|\.claude/plugins/cache/coding-standards/coding-standards/[^/]+)/(hooks/\S+)$"
)


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


def _rule(rule: Any) -> tuple[str, str | None] | None:
    m = RULE.match(rule) if isinstance(rule, str) else None
    return (m.group(1), m.group(2)) if m else None


def covers(broad: str, narrow: str) -> bool:
    """Report whether the rule broad matches everything the rule narrow does.

    Only forms whose matching is plain are compared: a bare tool name, a Bash prefix rule such
    as "Bash(git:*)", and "WebFetch(domain:*)". Path rules use glob matching, so they are never
    treated as covered.
    """
    b, n = _rule(broad), _rule(narrow)
    if b is None or n is None or b[0] != n[0] or broad == narrow:
        return False

    tool, bspec = b
    nspec = n[1]
    if bspec is None:
        return nspec is not None
    if nspec is None:
        return False

    if tool == "Bash" and bspec.endswith(":*"):
        prefix = bspec[:-2]
        command = nspec[:-2] if nspec.endswith(":*") else nspec
        return command == prefix or command.startswith(prefix + " ")
    if tool == "WebFetch" and bspec == "domain:*":
        return nspec.startswith("domain:")
    return False


def plugin_hooks(path: Path = PLUGIN_HOOKS) -> set[tuple[str, str, str]]:
    """Return (event, matcher, script) for each plugin hook that runs a script of its own."""
    try:
        config = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return set()

    found = set()
    for event, groups in config.get("hooks", {}).items():
        for group in groups:
            for hook in group.get("hooks", []):
                m = PLUGIN_SCRIPT.match(str(hook.get("command", "")).replace('"', ""))
                if m:
                    found.add((event, group.get("matcher", ""), m.group(1)))
    return found


def _standards_script(command: Any) -> str | None:
    """Return the hooks/ script a user hook runs from a copy of the standards, if it runs one."""
    if not isinstance(command, str):
        return None
    command = command.replace('"', "").replace("'", "").strip()
    home = str(Path.home())
    for spelling in ("${HOME}", "$HOME", home):
        if command.startswith(spelling + "/"):
            command = "~" + command[len(spelling):]
    m = STANDARDS_SCRIPT.match(command)
    return m.group(1) if m else None


def _short(text: str) -> str:
    return text if len(text) <= 90 else text[:87] + "..."


def _dedupe_hooks(new: dict[str, Any], plugin: set[tuple[str, str, str]], changes: list[str]) -> None:
    hooks = new.get("hooks")
    if not isinstance(hooks, dict):
        return

    for event, groups in hooks.items():
        if not isinstance(groups, list):
            continue
        seen: set[tuple[str, str]] = set()
        emptied = []
        for group in groups:
            if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
                continue
            matcher = group.get("matcher", "")
            kept = []
            for hook in group["hooks"]:
                label = f"{event}[{matcher}]: {_short(str(hook.get('command', hook)))}"
                key = (matcher, json.dumps(hook, sort_keys=True))
                script = _standards_script(hook.get("command"))
                if key in seen:
                    changes.append(f"drop duplicate hook {label}")
                elif script and (event, matcher, script) in plugin:
                    changes.append(f"drop hook the plugin already runs, {label}")
                else:
                    seen.add(key)
                    kept.append(hook)
            if group["hooks"] and not kept:
                emptied.append(group)
            group["hooks"] = kept
        groups[:] = [g for g in groups if not any(g is e for e in emptied)]


def _config_deny_rules() -> set[str]:
    home = Path.home()
    return set(CONFIG_DENY_RULES) | {r.replace("~", "/" + str(home), 1) for r in CONFIG_DENY_RULES}


def _has_guard_hook(settings: dict[str, Any]) -> bool:
    groups = (settings.get("hooks") or {}).get("PreToolUse") or []
    return any(
        isinstance(g, dict) and any(isinstance(h, dict) and h.get("command") == CONFIG_GUARD_COMMAND
                                    for h in g.get("hooks") or [])
        for g in groups
    )


def _guard_config(new: dict[str, Any], changes: list[str]) -> None:
    """Replace a permission deny on all of ~/.config with the config guard, or finish a partial one."""
    rules = _node(new, ("permissions",), create=False)
    deny = rules.get("deny") if rules is not None else None
    broad = [r for r in deny if r in _config_deny_rules()] if isinstance(deny, list) else []
    filesystem = _node(new, ("sandbox", "filesystem"), create=False)
    deny_read = filesystem.get("denyRead") if filesystem is not None else None
    sandboxed = isinstance(deny_read, list) and CONFIG_DENY_READ in deny_read
    if not (broad or sandboxed or _has_guard_hook(new)):
        return

    for rule in broad:
        deny.remove(rule)
        changes.append(f"remove permissions.deny: {rule}, replaced by the sandbox deny and the guard hook")

    if not sandboxed:
        filesystem = _node(new, ("sandbox", "filesystem"), create=True)
        if filesystem is None or not isinstance(filesystem.setdefault("denyRead", []), list):
            raise SetupError("sandbox.filesystem.denyRead is not a list")
        filesystem["denyRead"].append(CONFIG_DENY_READ)
        changes.append(f"add sandbox.filesystem.denyRead: {CONFIG_DENY_READ}")

    hooks = _node(new, ("hooks",), create=True)
    if hooks is None or not isinstance(hooks.setdefault("PreToolUse", []), list):
        raise SetupError("hooks.PreToolUse is not a list")
    groups = hooks["PreToolUse"]
    placed = False
    emptied = []
    for group in groups:
        if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
            continue
        guard = [
            h for h in group["hooks"] if isinstance(h, dict) and h.get("command") == CONFIG_GUARD_COMMAND
        ]
        if not guard:
            continue
        if group.get("matcher") == CONFIG_GUARD_MATCHER and not placed:
            placed = True
            continue
        group["hooks"] = [h for h in group["hooks"] if not any(h is g for g in guard)]
        changes.append(f"drop guard hook from PreToolUse[{group.get('matcher', '')}]")
        if not group["hooks"]:
            emptied.append(group)
    groups[:] = [g for g in groups if not any(g is e for e in emptied)]
    if not placed:
        hook = {"type": "command", "command": CONFIG_GUARD_COMMAND}
        groups.append({"matcher": CONFIG_GUARD_MATCHER, "hooks": [hook]})
        changes.append(f"add hooks.PreToolUse[{CONFIG_GUARD_MATCHER}]: {CONFIG_GUARD_COMMAND}")


def missing_guard_script(settings: dict[str, Any]) -> Path | None:
    """Return where the registered guard hook's script should be, when it is not there."""
    script = Path.home() / ".claude" / "coding-standards-current" / CONFIG_GUARD_SCRIPT
    return script if _has_guard_hook(settings) and not script.exists() else None


def plan(
    settings: dict[str, Any], plugin: set[tuple[str, str, str]] = frozenset()
) -> tuple[dict[str, Any], list[str]]:
    """Return the settings with every change applied, and one line per change.

    plugin is what plugin_hooks returns. A user hook that runs the same script on the same
    event and matcher runs twice, so it is dropped.
    """
    new = json.loads(json.dumps(settings))
    changes: list[str] = []
    managed = {entry for entries in MANAGED.values() for entry in entries}

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

    for key in RULE_LISTS:
        rules = _node(new, ("permissions",), create=False)
        if rules is None or not isinstance(rules.get(key), list):
            continue
        kept = []
        for rule in rules[key]:
            broader = next((b for b in rules[key] if covers(b, rule)), None)
            if broader is not None and rule not in managed:
                changes.append(f"drop permissions.{key}: {rule}, covered by {broader}")
            else:
                kept.append(rule)
        rules[key] = kept

    _dedupe_hooks(new, plugin, changes)
    _guard_config(new, changes)

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
        new, changes = plan(old, plugin_hooks())
        missing = missing_guard_script(new)
        if missing is not None:
            print(
                f"The config guard hook runs {missing}, which does not exist, so the file tools are not "
                "guarded. Update the coding-standards plugin, then start a session with it enabled, "
                "which points ~/.claude/coding-standards-current at the new version."
            )
        if not changes:
            if missing is None:
                print(f"{args.settings} already has what the coding standards need.")
            return 4 if missing is not None else 0

        print(f"{args.settings} needs {len(changes)} change(s) for the coding standards:")
        for change in changes:
            print(f"  - {change}")
        if args.check:
            print("Run setup_permissions.py from your own terminal to apply them.")
            return 5 if any(c.startswith("add ") for c in changes) else 3

        _refuse_unattended()
        # Removing the deny before its hook can run would leave the file tools unguarded.
        if missing is not None and any(c.startswith("remove permissions.deny") for c in changes):
            raise SetupError("not replacing the ~/.config deny until the guard hook's script exists")
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
