#!/usr/bin/env python3
"""Find and resolve the coding-standards imports in a project's instruction files.

    python3 standards_imports.py refs [--cwd DIR] [--snapshot DIR]

`update_profile.py` and `check-setup.sh` share this module, so both read instruction files the
same way. The `refs` command prints, as JSON, the instruction files Claude Code loads for DIR and
every standards path in them. With --snapshot, each path also says whether it resolves there.

A standards path is a path that ends in `.md` and sits under the plugin link or an old
checkout prefix. Prose that only names the checkout does not match. Claude Code expands `@`
imports outside fenced code blocks and inline code spans, so those are never parsed. A path
with no `@` is a plain-text path. It loads nothing.

Errors go to stderr with exit status 1.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional

LINK = "~/.claude/coding-standards-current"
OLD_ROOTS = ("~/projects/coding_agent_standards", "~/coding-standards")
MAPPED_DIRS = ("practices", "languages", "profiles", "project-management", "knowledge")
INSTRUCTION_NAMES = ("CLAUDE.md", "CLAUDE.local.md", ".claude/CLAUDE.md")

_PREFIXES = "|".join(re.escape(p) for p in (LINK, *OLD_ROOTS))
STANDARDS_PATH = re.compile(rf"(?<![\w/])(?P<at>(?<!\w)@)?(?P<path>(?:{_PREFIXES})/[\w.+/-]*?\.md)(?![\w/-])")
RELATIVE_IMPORT = re.compile(r"(?<!\w)@(?P<path>\.{1,2}/[\w.+/-]*?\.md)(?![\w/-])")
PROFILE_REL = re.compile(r"^profiles/([^/]+)\.md$")

OPEN_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
CODE_SPAN = re.compile(r"(`+)(.+?)\1")
LINK_TARGET_PREFIX = re.compile(r"(?:\]\(|^\s*\[[^\]]+\]:\s*)$")
LEAD = re.compile(r"^\s*(?:(?:[-*+]|\d+[.)])\s+)?(?:[A-Za-z]{1,10}:?\s+)?$")


class ImportsError(Exception):
    """A failure the caller must report; the message says what and where."""


@dataclass(frozen=True)
class Ref:
    """One standards path in an instruction file.

    `rel` is the path inside the snapshot, as the link would name it. It is None when the path
    sits under an old prefix but no mapping covers it. `start` and `end` are offsets into the
    original line and include the `@`.
    """

    file: str
    line: int
    start: int
    end: int
    at: bool
    path: str
    origin: str
    rel: Optional[str]
    linked: bool = False

    @property
    def kind(self) -> str:
        if self.at:
            return self.origin
        return "linktarget" if self.linked else "plain"

    @property
    def link_path(self) -> Optional[str]:
        return f"{LINK}/{self.rel}" if self.rel else None

    @property
    def profile(self) -> Optional[str]:
        match = PROFILE_REL.match(self.rel or "")
        return match.group(1) if match else None

    def to_json(self) -> dict:
        return {
            "file": self.file,
            "line": self.line,
            "text": ("@" if self.at else "") + self.path,
            "kind": self.kind,
            "rel": self.rel,
            "profile": self.profile,
        }


def map_path(path: str) -> tuple:
    """Return (origin, rel) for a standards path.

    origin is "link" or "old". rel is None when an old path has no mapping.
    """
    if path.startswith(LINK + "/"):
        return "link", path[len(LINK) + 1 :]
    for root in OLD_ROOTS:
        if path.startswith(root + "/"):
            rest = path[len(root) + 1 :]
            if rest.startswith("claude/"):
                return "old", rest[len("claude/") :]
            if rest.split("/", 1)[0] in MAPPED_DIRS:
                return "old", rest
            return "old", None
    raise ImportsError(f"not a standards path: {path}")


def scan_lines(text: str) -> Iterator[tuple]:
    """Yield (line number, line, masked line) for lines outside fences, with code spans blanked.

    The masked line keeps the original's length, so offsets in it index the original.
    """
    fence = None
    for number, line in enumerate(text.splitlines(), 1):
        opening = OPEN_FENCE.match(line)
        if fence is None and opening:
            fence = opening.group(1)
            continue
        if fence is not None:
            stripped = line.strip()
            if stripped and set(stripped) == {fence[0]} and len(stripped) >= len(fence):
                fence = None
            continue
        yield number, line, CODE_SPAN.sub(lambda m: " " * len(m.group(0)), line)


def parse_text(text: str, file: str = "") -> list:
    refs = []
    for number, line, masked in scan_lines(text):
        for match in STANDARDS_PATH.finditer(masked):
            path = match.group("path")
            origin, rel = map_path(path)
            at = match.group("at") is not None
            linked = not at and bool(LINK_TARGET_PREFIX.search(masked[: match.start()]))
            refs.append(Ref(file, number, match.start(), match.end(), at, path, origin, rel, linked))
    return refs


def parse_file(path: Path) -> list:
    try:
        text = path.read_text()
    except OSError as err:
        raise ImportsError(f"cannot read {path}: {err.strerror or err}") from err
    return parse_text(text, str(path))


def is_import_only(line: str, refs: list) -> bool:
    """True when the line holds only the given paths, with at most a list marker or a short lead."""
    rest = line
    for ref in sorted(refs, key=lambda r: r.start, reverse=True):
        rest = rest[: ref.start] + " " + rest[ref.end :]
    return bool(LEAD.match(rest.strip() + " "))


def in_snapshot(snapshot: Path, rel: Optional[str]) -> bool:
    """True when rel names a file inside the snapshot."""
    if not rel:
        return False
    clean = os.path.normpath(rel)
    if clean.startswith("..") or os.path.isabs(clean):
        return False
    return (snapshot / clean).is_file()


def included_files(snapshot: Path, rel: str) -> set:
    """Return every snapshot file that `rel` includes, itself too, following `@` imports.

    Link-form imports resolve against the snapshot. Relative imports resolve against the
    importing file's directory.
    """
    seen: set = set()
    queue = [os.path.normpath(rel)]
    while queue:
        current = queue.pop()
        if current in seen or not in_snapshot(snapshot, current):
            continue
        seen.add(current)
        text = (snapshot / current).read_text()
        for ref in parse_text(text):
            if ref.at and ref.origin == "link" and ref.rel:
                queue.append(os.path.normpath(ref.rel))
        for _, _, masked in scan_lines(text):
            for match in RELATIVE_IMPORT.finditer(masked):
                joined = os.path.normpath(os.path.join(os.path.dirname(current), match.group("path")))
                if not joined.startswith(".."):
                    queue.append(joined)
    return seen


def profile_files(snapshot: Path, profiles: list) -> set:
    """Return the files the named profiles include, the profiles themselves too."""
    files: set = set()
    for name in profiles:
        files |= included_files(snapshot, f"profiles/{name}.md")
    return files


def _git(cwd: Path, *args: str) -> Optional[str]:
    try:
        result = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True)
    except OSError:
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def git_path(cwd: Path, flag: str) -> Optional[Path]:
    """Return the absolute path `git rev-parse FLAG` names.

    `--path-format=absolute` needs git 2.31, so the plain output is resolved against cwd instead.
    """
    out = _git(cwd, "rev-parse", flag)
    if not out:
        return None
    path = Path(out)
    return path if path.is_absolute() else Path(os.path.normpath(cwd / path))


@dataclass(frozen=True)
class Checkout:
    """Where the current directory sits: its project root, and the main checkout of a linked worktree."""

    cwd: Path
    root: Path
    main_root: Optional[Path]


def locate(cwd: Path) -> Checkout:
    cwd = cwd.resolve()
    top = git_path(cwd, "--show-toplevel")
    if top is None:
        return Checkout(cwd, cwd, None)
    root = top.resolve()
    git_dir = git_path(cwd, "--git-dir")
    common = git_path(cwd, "--git-common-dir")
    main_root = None
    if git_dir and common and git_dir.resolve() != common.resolve():
        if common.resolve().name == ".git":
            main_root = common.resolve().parent
    return Checkout(cwd, root, main_root)


def directories(checkout: Checkout) -> list:
    """Return the directories Claude Code reads instruction files from, nearest first."""
    found = [checkout.cwd]
    while found[-1] != checkout.root and checkout.root in found[-1].parents:
        found.append(found[-1].parent)
    return found


def instruction_groups(checkout: Checkout) -> list:
    """Return the instruction files, nearest first, with names for one real file grouped together.

    A `.claude/CLAUDE.md` symlinked to `../CLAUDE.md` is one file. The first name in a group is
    the one found first.
    """
    groups: dict = {}
    for directory in directories(checkout):
        for name in INSTRUCTION_NAMES:
            path = directory / name
            if path.is_file():
                groups.setdefault(path.resolve(), []).append(path)
    return list(groups.values())


def find_instruction_files(checkout: Checkout) -> list:
    return [group[0] for group in instruction_groups(checkout)]


def main_copies(checkout: Checkout) -> list:
    """Return (worktree path, main checkout path) for each CLAUDE.local.md the main checkout has.

    The worktree path may not exist. Only a worktree's own CLAUDE.local.md loads there.
    """
    if checkout.main_root is None:
        return []
    pairs = []
    for directory in directories(checkout):
        mine = directory / "CLAUDE.local.md"
        theirs = checkout.main_root / directory.relative_to(checkout.root) / "CLAUDE.local.md"
        if theirs.is_file():
            pairs.append((mine, theirs))
    return pairs


def main(argv: list) -> int:
    parser = argparse.ArgumentParser(
        prog="standards_imports.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    cmd = sub.add_parser("refs", help="list instruction files and their standards paths")
    cmd.add_argument("--cwd", type=Path, default=Path.cwd())
    cmd.add_argument("--snapshot", type=Path, help="a snapshot directory to resolve paths against")
    cmd.add_argument("--json", action="store_true", help="accepted for symmetry; output is always JSON")
    args = parser.parse_args(argv)
    try:
        checkout = locate(args.cwd)
        files = []
        for path in find_instruction_files(checkout):
            refs = []
            for ref in parse_file(path):
                entry = ref.to_json()
                if args.snapshot is not None:
                    entry["resolves"] = in_snapshot(args.snapshot, ref.rel)
                refs.append(entry)
            files.append({"path": str(path), "refs": refs})
    except ImportsError as err:
        print(f"standards_imports.py: {err}", file=sys.stderr)
        return 1
    print(json.dumps({"root": str(checkout.root), "files": files}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
