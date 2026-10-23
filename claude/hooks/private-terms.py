#!/usr/bin/env python3
"""Block commits that carry private terms into a public repo.

    private-terms.py pretooluse         PreToolUse hook on Bash; reads the hook payload on stdin
    private-terms.py pre-commit         git pre-commit hook; checks the staged diff
    private-terms.py commit-msg FILE    git commit-msg hook; checks the message in FILE

Terms come from ~/.config/coding_agent_standards/private-terms.txt, one per line, with blank
lines and # comments ignored. A term matches as a whole word, case-insensitively. Without the
file, every mode allows everything.

Only repos whose visibility is public or unknown are checked. Visibility comes from
`git config codingstandards.visibility`, then from the host through `gh repo view`.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path

TERMS = Path.home() / ".config" / "coding_agent_standards" / "private-terms.txt"
CACHE = Path.home() / ".local" / "state" / "coding_agent_standards" / "term-guard" / "visibility.json"

# A public result is kept forever, since a public repo going private only costs extra checks. A
# private one expires so that a repo made public is caught within a day.
PRIVATE_TTL = 24 * 60 * 60

HOST_VISIBILITY = {"PUBLIC": "public", "PRIVATE": "private", "INTERNAL": "protected"}
LEVELS = ("private", "protected", "public")

GIT_COMMIT = re.compile(r"\bgit\b[^\n;&|]*\bcommit\b")


def load_terms() -> list[str]:
    try:
        lines = TERMS.read_text().splitlines()
    except OSError:
        return []

    return [t.strip() for t in lines if t.strip() and not t.strip().startswith("#")]


def matcher(terms: list[str]) -> re.Pattern:
    alternatives = "|".join(re.escape(t) for t in sorted(terms, key=len, reverse=True))
    return re.compile(rf"(?<![A-Za-z0-9])(?:{alternatives})(?![A-Za-z0-9])", re.IGNORECASE)


def git(repo: str, *args: str) -> str | None:
    result = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)
    if result.returncode != 0:
        return None
    return result.stdout


def remote_url(repo: str) -> str | None:
    upstream = git(repo, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    names = (git(repo, "remote") or "").split()
    candidates = []
    if upstream and "/" in upstream:
        candidates.append(upstream.strip().split("/", 1)[0])
    candidates += ["origin"] + names

    for name in candidates:
        if name in names:
            url = git(repo, "remote", "get-url", "--push", name)
            if url:
                return url.strip()
    return None


def read_cache() -> dict:
    try:
        return json.loads(CACHE.read_text())
    except (OSError, ValueError):
        return {}


def write_cache(cache: dict) -> None:
    try:
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        tmp = CACHE.with_suffix(f".tmp.{os.getpid()}")
        tmp.write_text(json.dumps(cache, indent=2, sort_keys=True) + "\n")
        tmp.replace(CACHE)
    except OSError:
        pass


def host_visibility(url: str) -> str | None:
    cache = read_cache()
    hit = cache.get(url)
    if hit and (hit["visibility"] == "public" or time.time() - hit["checked"] < PRIVATE_TTL):
        return hit["visibility"]

    try:
        result = subprocess.run(
            ["gh", "repo", "view", url, "--json", "visibility", "--jq", ".visibility"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None

    visibility = HOST_VISIBILITY.get(result.stdout.strip()) if result.returncode == 0 else None
    if visibility is None:
        return None

    cache[url] = {"visibility": visibility, "checked": int(time.time())}
    write_cache(cache)
    return visibility


def visibility(repo: str) -> str | None:
    declared = (git(repo, "config", "--get", "codingstandards.visibility") or "").strip().lower()
    if declared in LEVELS:
        return declared

    url = remote_url(repo)
    return host_visibility(url) if url else None


def added_lines(diff: str) -> list[tuple[str, int, str]]:
    """Return (path, line number, text) for every added line in a unified diff."""
    out = []
    path, line = "", 0
    for raw in diff.splitlines():
        if raw.startswith("+++ "):
            path = raw[4:].removeprefix("b/")
        elif raw.startswith("@@"):
            m = re.search(r"\+(\d+)", raw)
            line = int(m.group(1)) if m else 0
        elif raw.startswith("+"):
            out.append((path, line, raw[1:]))
            line += 1
        elif not raw.startswith("-"):
            line += 1
    return out


def commit_scope(command: str) -> tuple[str | None, list[str], bool]:
    """Pull `-C <dir>`, the pathspecs after `--`, and `-a` out of the git commit in a command."""
    match = GIT_COMMIT.search(command)
    segment = command[match.start() :].split("\n", 1)[0] if match else ""
    segment = re.split(r"&&|\|\||;|\|", segment, maxsplit=1)[0]
    try:
        words = shlex.split(segment)
    except ValueError:
        return None, [], False
    if "commit" not in words:
        return None, [], False

    at = words.index("commit")
    before, after = words[:at], words[at + 1 :]

    # Before the subcommand, -C names the repo. After it, -C reuses a commit's message.
    directory = None
    if "-C" in before and before.index("-C") + 1 < len(before):
        directory = before[before.index("-C") + 1]

    paths = after[after.index("--") + 1 :] if "--" in after else []
    commit_all = any(w == "--all" or re.fullmatch(r"-[A-Za-z]*a[A-Za-z]*", w) for w in after)
    return directory, paths, commit_all


def diff_hits(repo: str, pattern: re.Pattern, paths: list[str], commit_all: bool) -> list[str]:
    diffs = [git(repo, "diff", "--cached", "--no-color", "--no-ext-diff", "-U0") or ""]
    if paths or commit_all:
        # A commit by path or with -a takes the working tree, not the index.
        diffs.append(git(repo, "diff", "HEAD", "--no-color", "--no-ext-diff", "-U0", "--", *paths) or "")

    hits = []
    for diff in diffs:
        for path, line, text in added_lines(diff):
            for term in pattern.findall(text):
                hit = f"{term} ({path}:{line})"
                if hit not in hits:
                    hits.append(hit)
    return hits


def text_hits(text: str, pattern: re.Pattern, where: str) -> list[str]:
    seen = []
    for term in pattern.findall(text):
        if term.lower() not in (s.lower() for s in seen):
            seen.append(term)
    return [f"{t} ({where})" for t in seen]


def reason(repo: str, level: str | None, hits: list[str]) -> str:
    audience = "a public repo" if level == "public" else "a repo whose visibility is unknown"
    lines = [
        f"This commit goes to {audience} and contains private terms: {', '.join(hits)}.",
        "Generalize or remove them, then commit again. See rules/disclosure.md.",
    ]
    if level is None:
        lines.append(
            "If the repo is private, the user declares it once by running: "
            f"git -C {shlex.quote(repo)} config codingstandards.visibility private"
        )
    return " ".join(lines)


def checked(repo: str) -> tuple[bool, str | None]:
    level = visibility(repo)
    return level in ("public", None), level


def pretooluse(payload: dict) -> int:
    if payload.get("tool_name") != "Bash":
        return 0
    command = payload.get("tool_input", {}).get("command", "")
    if not GIT_COMMIT.search(command):
        return 0

    terms = load_terms()
    if not terms:
        return 0

    directory, paths, commit_all = commit_scope(command)
    cwd = payload.get("cwd") or os.getcwd()
    repo = os.path.join(cwd, os.path.expanduser(directory)) if directory else cwd
    top = git(repo, "rev-parse", "--show-toplevel")
    if top is None:
        return 0
    repo = top.strip()

    check, level = checked(repo)
    if not check:
        return 0

    pattern = matcher(terms)
    hits = text_hits(command, pattern, "commit command") + diff_hits(repo, pattern, paths, commit_all)
    if hits:
        decision = {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason(repo, level, hits),
        }
        print(json.dumps({"hookSpecificOutput": decision}))
    return 0


def git_hook(mode: str, args: list[str]) -> int:
    terms = load_terms()
    if not terms:
        return 0

    top = git(os.getcwd(), "rev-parse", "--show-toplevel")
    if top is None:
        return 0
    repo = top.strip()

    check, level = checked(repo)
    if not check:
        return 0

    pattern = matcher(terms)
    if mode == "pre-commit":
        hits = diff_hits(repo, pattern, [], False)
    else:
        message = "\n".join(l for l in Path(args[0]).read_text().splitlines() if not l.startswith("#"))
        hits = text_hits(message, pattern, "commit message")

    if hits:
        print(reason(repo, level, hits), file=sys.stderr)
        print("A false positive can be committed with --no-verify.", file=sys.stderr)
        return 1
    return 0


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "pretooluse":
        return pretooluse(json.load(sys.stdin))
    if mode == "pre-commit" or (mode == "commit-msg" and len(sys.argv) == 3):
        return git_hook(mode, sys.argv[2:])
    sys.exit(__doc__)


if __name__ == "__main__":
    sys.exit(main())
