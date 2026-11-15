#!/usr/bin/env python3
"""Run a guardian's optional hooks for one event.

    python3 guardian_hooks.py start DOMAIN_NAME < domain.json
    python3 guardian_hooks.py stop DOMAIN_NAME [--detach]
    python3 guardian_hooks.py saved DOMAIN_NAME

Hooks are executables in ~/.config/coding_agent_standards/guardian-hooks/<event>/. They run
in name order. Files that start with a dot, and files that are not executable, are skipped. A
missing directory means no hooks, which is the usual case.

`start` reads the domain on stdin as JSON and saves it beside the ledger as domain.json:

    {"entries": [{"checkout": "/abs/path", "scopes": ["claude/"],
                  "commit_policy": {"branch": "main", "push": false, "style": "rules/commit-style.md"},
                  "visibility": "public"}]}

Every entry needs its commit policy and visibility, so a restarted guardian can reuse the saved
domain without asking the user again. It also records the domain name under the
session's ID, from CLAUDE_CODE_SESSION_ID, in guardians/by-session/. SessionEnd input carries
the session ID but no title, so guardian-session-end.sh finds the domain there and runs `stop`.
`stop` reads the saved domain.json. `--detach` runs it in a new session and returns at once,
with its output in stop.log beside the ledger. The host may kill the SessionEnd hook's process
group when its budget runs out, and a new session leaves that group. Each hook gets the event, the domain name, the session name,
and the entries as one JSON object on stdin.

`saved` runs no hooks. It prints the saved domain and the problems that keep a restarted guardian
from reusing it, such as a missing domain.json, an entry without a commit policy or visibility, or
a checkout that no longer exists. No problems means the guardian reuses the domain as saved.

A failing hook never stops the guardian. The result is JSON on stdout, one item per hook with
its exit status and output. The exit status is 1 only for a usage error or an unreadable domain.
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

EVENTS = ("start", "stop")
COMMANDS = EVENTS + ("saved",)
VISIBILITIES = ("private", "protected", "public")
HOOK_TIMEOUT = 30

# Matches the names name-guardian.sh accepts, so a domain name never escapes the state directory.
DOMAIN_NAME = r"[A-Za-z0-9][A-Za-z0-9._-]*"


def hooks_dir(event: str) -> Path:
    return Path.home() / ".config" / "coding_agent_standards" / "guardian-hooks" / event


def guardians_dir() -> Path:
    return Path.home() / ".local" / "state" / "coding_agent_standards" / "guardians"


def record_session(domain_name: str) -> None:
    session_id = os.environ.get("CLAUDE_CODE_SESSION_ID", "")
    if not re.fullmatch(r"[A-Za-z0-9-]+", session_id):
        return

    by_session = guardians_dir() / "by-session"
    by_session.mkdir(parents=True, exist_ok=True)
    (by_session / session_id).write_text(domain_name + "\n", encoding="utf-8")


def hooks(event: str) -> list[Path]:
    directory = hooks_dir(event)
    if not directory.is_dir():
        return []
    found = []
    for path in sorted(directory.iterdir()):
        if path.name.startswith("."):
            continue
        if path.is_file() and os.access(path, os.X_OK):
            found.append(path)
    return found


def validate(domain: Any, require_settings: bool = False) -> list[dict[str, Any]]:
    """Return the domain's entries, or raise ValueError naming what is malformed.

    Only `start` requires each entry's commit policy and visibility. A domain.json saved before
    they were recorded still drives `stop`, and `saved` reports what it lacks.
    """
    if not isinstance(domain, dict) or not isinstance(domain.get("entries"), list):
        raise ValueError('expected {"entries": [...]}')

    entries = domain["entries"]
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("checkout"), str):
            raise ValueError("each entry needs a checkout path")
        if not os.path.isabs(entry["checkout"]):
            raise ValueError(f"checkout must be absolute: {entry['checkout']}")

        scopes = entry.setdefault("scopes", [])
        if not isinstance(scopes, list) or not all(isinstance(s, str) for s in scopes):
            raise ValueError(f"scopes must be a list of paths: {entry['checkout']}")

        if require_settings:
            missing = missing_settings(entry)
            if missing:
                raise ValueError(f"{entry['checkout']} needs {' and '.join(missing)}")
    return entries


def missing_settings(entry: dict[str, Any]) -> list[str]:
    """Name the settings an entry lacks or holds in the wrong shape."""
    missing = []

    policy = entry.get("commit_policy")
    policy_ok = (
        isinstance(policy, dict)
        and isinstance(policy.get("branch"), str)
        and policy["branch"] != ""
        and isinstance(policy.get("push"), bool)
        and isinstance(policy.get("style"), str)
        and policy["style"] != ""
    )
    if not policy_ok:
        missing.append("a commit_policy with branch, push, and style")

    if entry.get("visibility") not in VISIBILITIES:
        missing.append(f"a visibility of {', '.join(VISIBILITIES)}")
    return missing


def saved_report(path: Path) -> dict[str, Any]:
    """Report the saved domain and every problem that keeps a restart from reusing it."""
    try:
        domain = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"domain": None, "problems": [f"no saved domain at {path}"]}
    except (OSError, ValueError) as e:
        return {"domain": None, "problems": [f"unreadable saved domain at {path}: {e}"]}

    try:
        entries = validate(domain)
    except ValueError as e:
        return {"domain": None, "problems": [f"malformed saved domain at {path}: {e}"]}

    problems = []
    if not entries:
        problems.append("the saved domain has no entries")
    for entry in entries:
        for missing in missing_settings(entry):
            problems.append(f"{entry['checkout']} has no {missing.removeprefix('a ')}")
        if not os.path.isdir(entry["checkout"]):
            problems.append(f"{entry['checkout']} no longer exists")
    return {"domain": {"entries": entries}, "problems": problems}


def run_hooks(event: str, domain_name: str, entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    payload = json.dumps({
        "event": event,
        "domain_name": domain_name,
        "session_name": f"{domain_name}_guardian",
        "entries": entries,
    })

    results = []
    for hook in hooks(event):
        try:
            proc = subprocess.run(
                [hook], input=payload, capture_output=True, text=True, timeout=HOOK_TIMEOUT
            )
            results.append({
                "hook": str(hook),
                "status": proc.returncode,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
            })
        except subprocess.TimeoutExpired:
            results.append({"hook": str(hook), "status": None, "error": f"timed out after {HOOK_TIMEOUT}s"})
        except OSError as e:
            results.append({"hook": str(hook), "status": None, "error": str(e)})
    return results


def detach_stop(domain_name: str) -> int:
    log = guardians_dir() / domain_name / "stop.log"
    try:
        log.parent.mkdir(parents=True, exist_ok=True)
        with open(log, "w", encoding="utf-8") as out:
            subprocess.Popen(
                [sys.executable, __file__, "stop", domain_name],
                stdin=subprocess.DEVNULL,
                stdout=out,
                stderr=out,
                start_new_session=True,
            )
    except OSError as e:
        print(f"guardian_hooks: {e}", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str]) -> int:
    detach = argv[3:] == ["--detach"]
    if detach:
        argv = argv[:3]

    usage_ok = len(argv) == 3 and argv[1] in COMMANDS and re.fullmatch(DOMAIN_NAME, argv[2])
    if not usage_ok or (detach and argv[1] != "stop"):
        print(__doc__.strip(), file=sys.stderr)
        return 1

    event, domain_name = argv[1], argv[2]
    if detach:
        return detach_stop(domain_name)

    saved = guardians_dir() / domain_name / "domain.json"
    if event == "saved":
        json.dump(saved_report(saved), sys.stdout, indent=2)
        print()
        return 0

    try:
        if event == "start":
            entries = validate(json.load(sys.stdin), require_settings=True)
            saved.parent.mkdir(parents=True, exist_ok=True)
            saved.write_text(json.dumps({"entries": entries}, indent=2) + "\n", encoding="utf-8")
            record_session(domain_name)
        elif not hooks(event):
            entries = []
        else:
            entries = validate(json.loads(saved.read_text(encoding="utf-8")))
    except (OSError, ValueError) as e:
        print(f"guardian_hooks: {e}", file=sys.stderr)
        return 1

    json.dump(run_hooks(event, domain_name, entries), sys.stdout, indent=2)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
