#!/usr/bin/env python3
"""Resolve what tracker-sync must reconcile, and maintain its config.

    python3 sync_scope.py scope [--since REV] [ARG ...]
    python3 sync_scope.py advance --mapping N --tracker NAME --kind KIND --id ID --commit SHA
    python3 sync_scope.py add-tracker --name NAME --type TYPE --assignee WHO [--site SITE]
    python3 sync_scope.py add-mapping --path P [--path P ...] --group TRACKER KIND ID [...]

Every subcommand acts on the git repository containing --repo-dir (default: the
working directory) and on the config at --config (default:
~/.config/coding_agent_standards/tracker-sync.json). Results are JSON on stdout.
Errors go to stderr with exit status 1.

Mappings are keyed by the normalized origin URL, so every clone and worktree of a
repository shares them. `scope` reads the local default branch and never fetches.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.parse
from pathlib import Path
from typing import Any

DEFAULT_CONFIG = Path.home() / ".config" / "coding_agent_standards" / "tracker-sync.json"

KINDS = {
    "jira": {"epic"},
    "linear": {"project"},
    "github": {"tracking-issue", "milestone", "label"},
}

BARE_KEY = re.compile(r"^[A-Z][A-Z0-9]*-\d+$")
KEY_REF = re.compile(r"\b[A-Z][A-Z0-9]+-\d+\b")
CLOSING_REF = re.compile(
    r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+((?:[\w.-]+/[\w.-]+)?#\d+)",
    re.IGNORECASE,
)
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class SyncError(Exception):
    """A failure the user must act on; the message says what and where."""


# -- git -----------------------------------------------------------------


def _git(root: Path, *args: str, check: bool = True) -> str:
    proc = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=False
    )
    if check and proc.returncode != 0:
        raise SyncError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout.strip() if proc.returncode == 0 else ""


def _git_ok(root: Path, *args: str) -> bool:
    return (
        subprocess.run(["git", "-C", str(root), *args], capture_output=True, check=False).returncode
        == 0
    )


def repo_root(start: Path) -> Path:
    out = _git(start, "rev-parse", "--show-toplevel", check=False)
    if not out:
        raise SyncError(f"{start} is not inside a git repository")
    return Path(out)


def normalize_remote(url: str) -> str:
    """Reduce a clone URL to host/path so SSH and HTTPS forms compare equal."""
    url = url.strip()
    scp = re.match(r"^[\w.-]+@([\w.-]+):(?!//)(.+)$", url)
    if scp:
        host, path = scp.groups()
    else:
        parts = urllib.parse.urlsplit(url)
        if not parts.scheme or not parts.hostname:
            raise SyncError(f"cannot parse remote URL {url!r}")
        host, path = parts.hostname, parts.path
    path = path.strip("/").removesuffix(".git")
    return f"{host.lower()}/{path}"


def repo_id(root: Path) -> str:
    url = _git(root, "remote", "get-url", "origin", check=False)
    if not url:
        raise SyncError("no origin remote; tracker-sync keys mappings by the origin URL")
    return normalize_remote(url)


def default_branch(root: Path) -> str:
    ref = _git(root, "symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD", check=False)
    if ref.startswith("origin/"):
        return ref.removeprefix("origin/")
    for name in ("main", "master"):
        if _git_ok(root, "rev-parse", "--verify", "--quiet", f"refs/heads/{name}"):
            return name
    raise SyncError("cannot determine the default branch (no origin/HEAD, main, or master)")


def behind_origin(root: Path, branch: str) -> int | None:
    if not _git_ok(root, "rev-parse", "--verify", "--quiet", f"refs/remotes/origin/{branch}"):
        return None
    return int(_git(root, "rev-list", "--count", f"{branch}..origin/{branch}"))


def is_commit(root: Path, rev: str) -> bool:
    return _git_ok(root, "cat-file", "-e", f"{rev}^{{commit}}")


def is_ancestor(root: Path, older: str, newer: str) -> bool:
    return _git_ok(root, "merge-base", "--is-ancestor", older, newer)


def resolve_since(root: Path, branch: str, rev: str) -> str:
    """Resolve a commit-ish, or a YYYY-MM-DD date to the last commit before it."""
    if DATE.match(rev):
        sha = _git(root, "rev-list", "-1", f"--before={rev}T00:00:00", branch)
        if not sha:
            raise SyncError(f"no commit on {branch} before {rev}")
        return sha
    if not is_commit(root, rev):
        raise SyncError(f"--since {rev!r} is not a commit")
    return _git(root, "rev-parse", f"{rev}^{{commit}}")


def commits_between(root: Path, since: str, head: str, paths: list[str]) -> list[dict[str, Any]]:
    fmt = "%H%x1f%ad%x1f%s%x1f%b%x1e"
    out = _git(root, "log", f"--format={fmt}", "--date=short", f"{since}..{head}", "--", *paths)
    commits = []
    for record in out.split("\x1e"):
        record = record.strip("\n")
        if not record:
            continue
        sha, date, subject, body = record.split("\x1f", 3)
        text = f"{subject}\n{body}"
        refs = set(KEY_REF.findall(text)) | set(CLOSING_REF.findall(text))
        commits.append({"sha": sha, "date": date, "subject": subject, "refs": sorted(refs)})
    return commits


def changed_files(root: Path, since: str, head: str, paths: list[str]) -> list[str]:
    out = _git(root, "diff", "--name-only", since, head, "--", *paths)
    return [line for line in out.splitlines() if line]


# -- config --------------------------------------------------------------


def load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"trackers": {}, "mappings": []}
    try:
        config = json.loads(path.read_text())
    except json.JSONDecodeError as err:
        raise SyncError(f"{path} is not valid JSON: {err}") from err
    _validate(config, path)
    return config


def _validate(config: Any, path: Path) -> None:
    if not isinstance(config, dict):
        raise SyncError(f"{path}: top level must be an object")
    trackers = config.setdefault("trackers", {})
    mappings = config.setdefault("mappings", [])
    if not isinstance(trackers, dict) or not isinstance(mappings, list):
        raise SyncError(f"{path}: 'trackers' must be an object and 'mappings' a list")
    for name, tracker in trackers.items():
        if not isinstance(tracker, dict) or tracker.get("type") not in KINDS:
            raise SyncError(f"{path}: tracker {name!r} needs a type in {sorted(KINDS)}")
    for i, mapping in enumerate(mappings):
        where = f"{path}: mappings[{i}]"
        if not isinstance(mapping, dict) or not isinstance(mapping.get("repo"), str):
            raise SyncError(f"{where} needs a 'repo' string")
        paths = mapping.get("paths")
        if not isinstance(paths, list) or not paths or not all(isinstance(p, str) for p in paths):
            raise SyncError(f"{where} needs a non-empty 'paths' list of strings")
        groups = mapping.get("groups")
        if not isinstance(groups, list) or not groups:
            raise SyncError(f"{where} needs a non-empty 'groups' list")
        for j, group in enumerate(groups):
            gwhere = f"{where}.groups[{j}]"
            if not isinstance(group, dict):
                raise SyncError(f"{gwhere} must be an object")
            tracker = trackers.get(group.get("tracker"))
            if tracker is None:
                raise SyncError(f"{gwhere} names unknown tracker {group.get('tracker')!r}")
            if group.get("kind") not in KINDS[tracker["type"]]:
                raise SyncError(
                    f"{gwhere} kind {group.get('kind')!r} is not valid for {tracker['type']}"
                )
            if not isinstance(group.get("id"), str) or not group["id"]:
                raise SyncError(f"{gwhere} needs an 'id' string")
            mark = group.get("last_synced_commit")
            if mark is not None and not isinstance(mark, str):
                raise SyncError(f"{gwhere} last_synced_commit must be a string or null")


def save_config(path: Path, config: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w") as fh:
            json.dump(config, fh, indent=2)
            fh.write("\n")
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise


def _same_repo(a: str, b: str) -> bool:
    return a.casefold() == b.casefold()


# -- argument parsing ----------------------------------------------------


def parse_ref(token: str) -> dict[str, str | None] | None:
    """Parse a group reference; None means the token is a path."""
    if token.startswith("jira:"):
        return {"type": "jira", "kind": "epic", "id": token.removeprefix("jira:")}
    if token.startswith("linear:"):
        return {"type": "linear", "kind": "project", "id": token.removeprefix("linear:")}
    if token.startswith("gh:"):
        body = token.removeprefix("gh:")
        issue = re.match(r"^([\w.-]+/[\w.-]+)#(\d+)$", body)
        if issue:
            return {"type": "github", "kind": "tracking-issue", "id": body}
        named = re.match(r"^([\w.-]+/[\w.-]+)/(milestone|label)/(.+)$", body)
        if named:
            repo, kind, name = named.groups()
            return {"type": "github", "kind": kind, "id": f"{repo}/{name}"}
        raise SyncError(
            f"cannot parse {token!r}; use gh:owner/repo#N, "
            "gh:owner/repo/milestone/NAME, or gh:owner/repo/label/NAME"
        )
    if BARE_KEY.match(token):
        return {"type": None, "kind": None, "id": token}
    return None


def normalize_path(root: Path, token: str) -> str:
    rel = token.strip().removeprefix("./").rstrip("/")
    if not rel or rel.startswith("/") or ".." in Path(rel).parts:
        raise SyncError(f"path {token!r} must be relative to the repository root")
    if not (root / rel).exists():
        raise SyncError(f"path {rel!r} does not exist under {root}")
    return rel


def _overlaps(a: str, b: str) -> bool:
    return a == b or a.startswith(f"{b}/") or b.startswith(f"{a}/")


def _ref_matches(ref: dict[str, str | None], group: dict[str, Any], trackers: dict) -> bool:
    if group["id"] != ref["id"]:
        return False
    if ref["type"] and trackers[group["tracker"]]["type"] != ref["type"]:
        return False
    return not ref["kind"] or group["kind"] == ref["kind"]


# -- subcommands ---------------------------------------------------------


def cmd_scope(args: argparse.Namespace, root: Path, config: dict[str, Any]) -> dict[str, Any]:
    rid = repo_id(root)
    branch = default_branch(root)
    head = _git(root, "rev-parse", branch)
    override = resolve_since(root, branch, args.since) if args.since else None

    req_paths, req_refs = [], []
    for token in args.args:
        ref = parse_ref(token)
        if ref is None:
            req_paths.append(normalize_path(root, token))
        else:
            req_refs.append(ref)

    trackers = config["trackers"]
    selected = []
    for index, mapping in enumerate(config["mappings"]):
        if not _same_repo(mapping["repo"], rid):
            continue
        if req_paths and not any(_overlaps(p, m) for p in req_paths for m in mapping["paths"]):
            continue
        for group in mapping["groups"]:
            if req_refs and not any(_ref_matches(r, group, trackers) for r in req_refs):
                continue
            selected.append(_scan(root, head, index, mapping, group, trackers, override))

    covered_paths = [p for s in selected for p in s["paths"]]
    unmapped_paths = [p for p in req_paths if not any(_overlaps(p, c) for c in covered_paths)]
    unmapped_refs = [
        r for r in req_refs if not any(_ref_matches(r, s["group"], trackers) for s in selected)
    ]
    return {
        "repo": rid,
        "root": str(root),
        "default_branch": branch,
        "head": head,
        "behind_origin": behind_origin(root, branch),
        "selected": selected,
        "unmapped": {"paths": unmapped_paths, "refs": unmapped_refs},
    }


def _scan(
    root: Path,
    head: str,
    index: int,
    mapping: dict[str, Any],
    group: dict[str, Any],
    trackers: dict[str, Any],
    override: str | None,
) -> dict[str, Any]:
    mark = group.get("last_synced_commit")
    if override:
        since, source = override, "override"
    elif mark and is_commit(root, mark) and is_ancestor(root, mark, head):
        since, source = mark, "watermark"
    elif mark:
        since, source = None, "invalid-watermark"
    else:
        since, source = None, "none"
    entry = {
        "mapping": index,
        "paths": mapping["paths"],
        "group": {"tracker": group["tracker"], "kind": group["kind"], "id": group["id"]},
        "tracker": trackers[group["tracker"]],
        "since": since,
        "since_source": source,
        "commits": [],
        "changed_files": [],
    }
    if since:
        entry["commits"] = commits_between(root, since, head, mapping["paths"])
        entry["changed_files"] = changed_files(root, since, head, mapping["paths"])
    return entry


def cmd_advance(args: argparse.Namespace, root: Path, config: dict[str, Any]) -> dict[str, Any]:
    rid = repo_id(root)
    mappings = config["mappings"]
    if not 0 <= args.mapping < len(mappings) or not _same_repo(mappings[args.mapping]["repo"], rid):
        raise SyncError(f"mapping {args.mapping} does not belong to {rid}; rerun scope")
    group = next(
        (
            g
            for g in mappings[args.mapping]["groups"]
            if (g["tracker"], g["kind"], g["id"]) == (args.tracker, args.kind, args.id)
        ),
        None,
    )
    if group is None:
        raise SyncError(f"mapping {args.mapping} has no group {args.tracker}/{args.kind}/{args.id}")
    if not is_commit(root, args.commit):
        raise SyncError(f"{args.commit!r} is not a commit")
    new = _git(root, "rev-parse", f"{args.commit}^{{commit}}")
    old = group.get("last_synced_commit")
    if old and is_commit(root, old) and not is_ancestor(root, old, new):
        raise SyncError(f"{new} does not descend from the current watermark {old}")
    group["last_synced_commit"] = new
    return {"mapping": args.mapping, "group": args.id, "from": old, "to": new}


def cmd_add_tracker(args: argparse.Namespace, root: Path, config: dict[str, Any]) -> dict[str, Any]:
    if args.type == "jira" and not args.site:
        raise SyncError("a jira tracker needs --site (for example example.atlassian.net)")
    tracker: dict[str, Any] = {"type": args.type, "assignee": args.assignee}
    if args.site:
        tracker["site"] = args.site
    action = "updated" if args.name in config["trackers"] else "added"
    config["trackers"][args.name] = tracker
    return {"tracker": args.name, "action": action}


def cmd_add_mapping(args: argparse.Namespace, root: Path, config: dict[str, Any]) -> dict[str, Any]:
    rid = repo_id(root)
    paths = sorted({normalize_path(root, p) for p in args.path})
    groups = []
    for tracker, kind, gid in args.group:
        if tracker not in config["trackers"]:
            raise SyncError(f"unknown tracker {tracker!r}; add it with add-tracker first")
        ttype = config["trackers"][tracker]["type"]
        if kind not in KINDS[ttype]:
            raise SyncError(f"kind {kind!r} is not valid for {ttype}; use {sorted(KINDS[ttype])}")
        groups.append({"tracker": tracker, "kind": kind, "id": gid, "last_synced_commit": None})

    for index, mapping in enumerate(config["mappings"]):
        if _same_repo(mapping["repo"], rid) and sorted(mapping["paths"]) == paths:
            have = {(g["tracker"], g["kind"], g["id"]) for g in mapping["groups"]}
            added = [g for g in groups if (g["tracker"], g["kind"], g["id"]) not in have]
            mapping["groups"].extend(added)
            return {"mapping": index, "action": "extended", "added_groups": len(added)}
    config["mappings"].append({"repo": rid, "paths": paths, "groups": groups})
    return {"mapping": len(config["mappings"]) - 1, "action": "added", "added_groups": len(groups)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--repo-dir", type=Path, default=Path.cwd())
    sub = parser.add_subparsers(dest="command", required=True)

    scope = sub.add_parser("scope", help="list selected groups and the commits to reconcile")
    scope.add_argument("--since", help="commit-ish or YYYY-MM-DD overriding the watermark")
    scope.add_argument("args", nargs="*", help="paths and group refs")

    advance = sub.add_parser("advance", help="move one group's watermark")
    advance.add_argument("--mapping", type=int, required=True)
    advance.add_argument("--tracker", required=True)
    advance.add_argument("--kind", required=True)
    advance.add_argument("--id", required=True)
    advance.add_argument("--commit", required=True)

    add_tracker = sub.add_parser("add-tracker", help="add or replace a tracker")
    add_tracker.add_argument("--name", required=True)
    add_tracker.add_argument("--type", required=True, choices=sorted(KINDS))
    add_tracker.add_argument("--assignee", required=True)
    add_tracker.add_argument("--site")

    add_mapping = sub.add_parser("add-mapping", help="map paths in this repo to groups")
    add_mapping.add_argument("--path", action="append", required=True)
    add_mapping.add_argument(
        "--group", nargs=3, action="append", required=True, metavar=("TRACKER", "KIND", "ID")
    )

    args = parser.parse_args(argv)
    handlers = {
        "scope": cmd_scope,
        "advance": cmd_advance,
        "add-tracker": cmd_add_tracker,
        "add-mapping": cmd_add_mapping,
    }
    try:
        root = repo_root(args.repo_dir)
        config = load_config(args.config)
        result = handlers[args.command](args, root, config)
        if args.command != "scope":
            save_config(args.config, config)
    except SyncError as err:
        print(f"sync_scope: {err}", file=sys.stderr)
        return 1
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
