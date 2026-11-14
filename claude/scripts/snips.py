#!/usr/bin/env python3
"""Find and drop snip commits on a branch.

    python3 snips.py list --base REV [--tip REV]
    python3 snips.py drop --base REV (--redundant | --all)

A snip commit marks the end of a run of work. It has the subject `8< --- snip ---` and no change of
its own: its tree equals its parent's tree. A commit with that subject and a change is not a snip.
`list` reports it under `not_empty` so a person can look at it.

A snip is redundant when the commit right before it on the range is also a snip. A rebase that
drops landed work can leave snips next to each other, and only the first of each run marks
anything. A snip with other commits before it, or one sitting directly on the base, is not
redundant.

`list` prints `{"snips", "redundant", "not_empty"}` for `base..tip`, oldest first, as full hashes.

`drop` rewrites the checked-out branch over `base..HEAD`. `--redundant` drops the redundant snips,
and `--all` drops every snip. It runs a non-interactive rebase onto `base` that turns the chosen
commits into `drop` lines and leaves every other commit in place. Autosquash and ref updates are
off, so no other commit moves and no other branch changes. Commits before the first dropped one
keep their hashes. It prints `{"dropped", "previous_head", "head", "tree_matches"}`. Since only
empty commits go, the tree of HEAD must not change. `tree_matches` false means it did, and
`previous_head` is the commit to recover from.

Both refuse a range with merge commits, since a linear rebase would flatten them. Errors go to
stderr with exit status 1. A drop that changed the tree exits 3.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

SUBJECT = "8< --- snip ---"


class SnipError(Exception):
    pass


def git(args: list[str], env: dict[str, str] | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(["git", *args], capture_output=True, text=True, env=env)
    if check and result.returncode != 0:
        raise SnipError(f"git {' '.join(args)}: {result.stderr.strip()}")
    return result


def resolve(rev: str) -> str:
    return git(["rev-parse", "--verify", f"{rev}^{{commit}}"]).stdout.strip()


def tree_of(rev: str) -> str:
    return git(["rev-parse", f"{rev}^{{tree}}"]).stdout.strip()


def range_commits(base: str, tip: str) -> list[dict[str, Any]]:
    """Return `base..tip` oldest first, each with its hash, tree, parents, and subject."""
    out = git(["log", "--reverse", "--format=%H%x00%T%x00%P%x00%s", f"{base}..{tip}"]).stdout
    commits = []
    for line in out.splitlines():
        sha, tree, parents, subject = line.split("\0", 3)
        commits.append({"sha": sha, "tree": tree, "parents": parents.split(), "subject": subject})

    merges = [c["sha"] for c in commits if len(c["parents"]) > 1]
    if merges:
        raise SnipError(f"the range holds merge commits, which a linear rebase would flatten: {merges}")
    return commits


def list_snips(base: str, tip: str = "HEAD") -> dict[str, list[str]]:
    commits = range_commits(resolve(base), resolve(tip))
    trees = {c["sha"]: c["tree"] for c in commits}

    snips: list[str] = []
    redundant: list[str] = []
    not_empty: list[str] = []
    previous_was_snip = False
    for commit in commits:
        is_snip = False
        if commit["subject"] == SUBJECT:
            parent = commit["parents"][0] if commit["parents"] else None
            parent_tree = trees.get(parent) if parent else None
            if parent and parent_tree is None:
                parent_tree = tree_of(parent)
            if parent_tree == commit["tree"]:
                is_snip = True
            else:
                not_empty.append(commit["sha"])

        if is_snip:
            snips.append(commit["sha"])
            if previous_was_snip:
                redundant.append(commit["sha"])
        previous_was_snip = is_snip

    return {"snips": snips, "redundant": redundant, "not_empty": not_empty}


def edit_todo(drop_file: Path, todo: Path) -> int:
    """Act as the sequence editor: turn the pick line of each listed commit into a drop line."""
    targets = [t for t in drop_file.read_text().split() if t]
    lines = todo.read_text().splitlines(keepends=True)
    matched: set[str] = set()

    for i, line in enumerate(lines):
        words = line.split(None, 2)
        if len(words) < 2 or words[0] not in ("pick", "p"):
            continue
        hits = [t for t in targets if t.startswith(words[1])]
        if len(hits) == 1:
            matched.add(hits[0])
            lines[i] = "drop " + line.split(None, 1)[1]

    if matched != set(targets):
        print(f"snips: the rebase todo lacks {sorted(set(targets) - matched)}", file=sys.stderr)
        return 1
    todo.write_text("".join(lines))
    return 0


def drop(base: str, mode: str) -> dict[str, Any]:
    base = resolve(base)
    previous_head = resolve("HEAD")
    found = list_snips(base, previous_head)
    targets = found["redundant"] if mode == "redundant" else found["snips"]
    if not targets:
        return {"dropped": [], "previous_head": previous_head, "head": previous_head, "tree_matches": True}

    before = tree_of(previous_head)
    with tempfile.TemporaryDirectory() as tmp:
        drop_file = Path(tmp) / "drop"
        drop_file.write_text("\n".join(targets) + "\n")
        editor = " ".join(shlex.quote(p) for p in (sys.executable, str(Path(__file__).resolve()), "_edit-todo",
                                                    str(drop_file)))
        env = {**os.environ, "GIT_SEQUENCE_EDITOR": editor, "GIT_EDITOR": "true"}
        rebased = git(["-c", "rebase.autoSquash=false", "-c", "rebase.updateRefs=false",
                       "-c", "rebase.abbreviateCommands=false", "rebase", "-i", "--keep-empty", "--empty=keep",
                       "--no-autosquash", base], env=env, check=False)

    if rebased.returncode != 0:
        git(["rebase", "--abort"], check=False)
        raise SnipError(f"the rebase failed and was aborted, so HEAD is unchanged: {rebased.stderr.strip()}")

    head = resolve("HEAD")
    return {"dropped": targets, "previous_head": previous_head, "head": head, "tree_matches": tree_of(head) == before}


def main(argv: list[str]) -> int:
    if len(argv) == 4 and argv[1] == "_edit-todo":
        return edit_todo(Path(argv[2]), Path(argv[3]))

    parser = argparse.ArgumentParser(prog="snips.py", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("list", help="list the snips, redundant snips, and non-empty snip subjects on a range")
    p.add_argument("--base", required=True, help="the commit the range starts after")
    p.add_argument("--tip", default="HEAD", help="the commit the range ends at, HEAD by default")
    p = sub.add_parser("drop", help="rebase the checked-out branch onto --base without the chosen snips")
    p.add_argument("--base", required=True, help="the commit the range starts after")
    which = p.add_mutually_exclusive_group(required=True)
    which.add_argument("--redundant", action="store_const", const="redundant", dest="mode",
                       help="drop each snip that directly follows another snip")
    which.add_argument("--all", action="store_const", const="all", dest="mode", help="drop every snip")
    args = parser.parse_args(argv[1:])

    try:
        if args.command == "list":
            print(json.dumps(list_snips(args.base, args.tip), indent=2))
            return 0
        result = drop(args.base, args.mode)
    except SnipError as e:
        print(f"snips: {e}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0 if result["tree_matches"] else 3


if __name__ == "__main__":
    sys.exit(main(sys.argv))
