#!/usr/bin/env python3
"""Run a guardian's optional hooks for one event.

    python3 guardian_hooks.py start DOMAIN_NAME < domain.json
    python3 guardian_hooks.py stop DOMAIN_NAME

Hooks are executables in ~/.config/coding_agent_standards/guardian-hooks/<event>/. They run
in name order. Files that start with a dot, and files that are not executable, are skipped. A
missing directory means no hooks, which is the usual case.

`start` reads the domain on stdin as JSON, `{"entries": [{"checkout": ..., "scopes": [...]}]}`,
and saves it beside the ledger as domain.json. It also records the domain name under the
session's ID, from CLAUDE_CODE_SESSION_ID, in guardians/by-session/. SessionEnd input carries
the session ID but no title, so guardian-session-end.sh finds the domain there and runs `stop`.
`stop` reads the saved domain.json. Each hook gets the event, the domain name, the session name,
and the entries as one JSON object on stdin.

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


def validate(domain: Any) -> list[dict[str, Any]]:
    """Return the domain's entries, or raise ValueError naming what is malformed."""
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
    return entries


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


def main(argv: list[str]) -> int:
    if len(argv) != 3 or argv[1] not in EVENTS or not re.fullmatch(DOMAIN_NAME, argv[2]):
        print(__doc__.strip(), file=sys.stderr)
        return 1

    event, domain_name = argv[1], argv[2]
    saved = guardians_dir() / domain_name / "domain.json"
    try:
        if event == "start":
            entries = validate(json.load(sys.stdin))
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
