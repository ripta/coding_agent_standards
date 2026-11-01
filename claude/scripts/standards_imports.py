#!/usr/bin/env python3
"""Find and resolve the coding-standards imports in a project's instruction files.

    python3 standards_imports.py refs [--cwd DIR] [--snapshot DIR]
    python3 standards_imports.py check --plugin-root DIR --session installed|plugin-dir

`update_profile.py` and `check-setup.sh` share this module, so both read instruction files the
same way. The `refs` command prints, as JSON, the instruction files Claude Code loads for DIR and
every standards path in them. With --snapshot, each path also says whether it resolves there.

The `check` command is what `check-setup.sh` runs. It prints one `warning: TEXT` or `notice: TEXT`
line for each problem it finds in the project at --cwd, and nothing when the project is in order.

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
    def old_dir(self) -> Optional[str]:
        """The first path segment under an old checkout root, or None for a path on the link."""
        for root in OLD_ROOTS:
            if self.path.startswith(root + "/"):
                return self.path[len(root) + 1 :].split("/", 1)[0]
        return None

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
        result = subprocess.run(
            ["git", "-C", str(cwd), *args], capture_output=True, text=True, timeout=GIT_TIMEOUT
        )
    except (OSError, subprocess.TimeoutExpired):
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


HOOK_ROOTS = tuple(root[len("~/") :] for root in OLD_ROOTS)
GIT_TIMEOUT = 2.0


def _lines(refs: list, limit: int = 3) -> str:
    numbers = sorted({r.line for r in refs})
    shown = ", ".join(str(n) for n in numbers[:limit])
    more = f", and {len(numbers) - limit} more" if len(numbers) > limit else ""
    return ("line " if len(numbers) == 1 else "lines ") + shown + more


def _examples(refs: list, limit: int = 3) -> str:
    texts = []
    for ref in refs:
        if ref.path not in texts:
            texts.append(ref.path)
    shown = ", ".join(texts[:limit])
    return shown + (f", and {len(texts) - limit} more" if len(texts) > limit else "")


FIXABLE_OLD = {
    "moved": "The checkout moved that directory under claude/, so the path loads nothing once the checkout is current.",
    "tree": (
        "The path reads the checkout's working tree, not the installed plugin, so it follows whatever the "
        "checkout has checked out."
    ),
}
UNRESOLVED_OLD = {
    "moved": "The checkout moved that directory under claude/, so it loads nothing once the checkout is current.",
    "tree": (
        "It reads the checkout's working tree, not the installed plugin, so it follows whatever the checkout "
        "has checked out."
    ),
}


def _old_kind(ref: Ref) -> str:
    """Name what an old path reaches: a directory that moved under claude/, or the checkout's own tree."""
    if ref.old_dir in MAPPED_DIRS:
        return "moved"
    return "tree"


def _by_kind(refs: list) -> dict:
    """Group old-path refs by (file, kind), so each warning's claim holds for every path it lists."""
    groups: dict = {}
    for ref in refs:
        groups.setdefault((ref.file, _old_kind(ref)), []).append(ref)
    return groups


def _by_file(refs: list) -> dict:
    grouped: dict = {}
    for ref in refs:
        grouped.setdefault(ref.file, []).append(ref)
    return grouped


def _command_strings(node: object) -> Iterator[str]:
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "command" and isinstance(value, str):
                yield value
            else:
                yield from _command_strings(value)
    elif isinstance(node, list):
        for item in node:
            yield from _command_strings(item)


def old_hook_paths(command: str, home: Path) -> list:
    """Return (old path, link path) for each plugin file a command reaches through the checkout.

    The checkout's working tree is whatever its owner last edited, so a command wired to it runs
    unreleased code in every project that uses the command.
    """
    homes = "|".join(re.escape(h) for h in ("${HOME}", "$HOME", "~", str(home)))
    roots = "|".join(re.escape(r) for r in HOOK_ROOTS)
    pattern = re.compile(rf"(?:{homes})/(?:{roots})/(?P<rest>[\w.+/-]+)")
    found = []
    for match in pattern.finditer(command):
        rest = match.group("rest")
        if rest.startswith("claude/"):
            rest = rest[len("claude/") :]
        elif rest.split("/", 1)[0] not in MAPPED_DIRS:
            continue
        found.append((match.group(0), f"$HOME/.claude/coding-standards-current/{rest}"))
    return found


def _settings_warnings(root: Path, home: Path) -> list:
    warnings = []
    for name in ("settings.json", "settings.local.json"):
        path = root / ".claude" / name
        try:
            data = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        for command in _command_strings(data):
            for old, new in old_hook_paths(command, home):
                warnings.append(
                    f"{path} runs {old}, which is the checkout's working tree. Use {new} instead, "
                    "so the command runs the installed plugin."
                )
    return warnings


def _approval(config: Path, root: Path) -> Optional[bool]:
    """Return whether the project approved external imports, or None when ~/.claude.json cannot say."""
    try:
        data = json.loads(config.read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    projects = data.get("projects")
    entry = projects.get(str(root)) if isinstance(projects, dict) else None
    return isinstance(entry, dict) and entry.get("hasClaudeMdExternalIncludesApproved") is True


def _link_problem(link: Path) -> Optional[str]:
    if link.is_symlink() and not link.exists():
        return f"{LINK} points at {os.readlink(link)}, which does not exist."
    if not link.exists():
        return f"{LINK} does not exist."
    if not link.is_dir():
        return f"{LINK} is not a directory."
    return None


def check(cwd: Path, plugin_root: Path, session: str, link: Path, home: Path, config: Path) -> list:
    """Return (level, text) pairs for a project's standards setup, level "warning" or "notice".

    An installed session resolves imports against the plugin root, which `link-current.sh` points
    the link at in the same SessionStart. A plugin-dir session resolves them against the link's
    current target, since that is what the session's imports read. The link is checked only in a
    plugin-dir session, because in an installed session `link-current.sh` owns it and may not
    have created it yet.
    """
    checkout = locate(cwd)
    out: list = []
    snapshot: Optional[Path] = plugin_root
    if session == "plugin-dir":
        problem = _link_problem(link)
        if problem:
            out.append((
                "warning",
                f"{problem} This is a --plugin-dir session, which does not refresh the link, so imports "
                "through it load nothing. Start one session with the plugin installed, so link-current.sh creates it.",
            ))
            snapshot = None
        else:
            snapshot = link.resolve()

    refs = []
    for path in find_instruction_files(checkout):
        refs.extend(parse_file(path))

    imports = [r for r in refs if r.at]
    plain = [r for r in refs if r.kind == "plain"]
    old = [r for r in imports if r.origin == "old"]
    unresolved = [r for r in imports if snapshot is not None and not in_snapshot(snapshot, r.rel)]
    unresolved_old = [r for r in unresolved if r.origin == "old"]
    unresolved_link = [r for r in unresolved if r.origin == "link"]
    fixable_old = [r for r in old if r not in unresolved]

    if not imports and not plain:
        copies = [
            theirs
            for mine, theirs in main_copies(checkout)
            if not mine.is_file() and any(r.at for r in parse_file(theirs))
        ]
        if copies:
            out.append((
                "warning",
                f"This worktree has no CLAUDE.local.md, so the coding standards it imports in {copies[0]} do not "
                f"load. List CLAUDE.local.md in {checkout.main_root}/.worktreeinclude so new worktrees get a "
                "copy, and copy it into this one.",
            ))
        else:
            out.append((
                "warning",
                "This project does not import the coding standards. Run /update-profile <profile> to add "
                f"@{LINK}/profiles/<profile>.md to CLAUDE.md or CLAUDE.local.md.",
            ))

    for (file, kind), group in _by_kind(fixable_old).items():
        out.append((
            "warning",
            f"{file} imports the old standards path {_examples(group)} ({_lines(group)}). {FIXABLE_OLD[kind]} "
            "Run /update-profile to point it at the plugin link.",
        ))
    for (file, kind), group in _by_kind(unresolved_old).items():
        out.append((
            "warning",
            f"{file} imports the old standards path {_examples(group)} ({_lines(group)}), which does not resolve "
            f"in the plugin snapshot. {UNRESOLVED_OLD[kind]} "
            "Run /update-profile to rewrite what it can and report the rest.",
        ))
    for file, group in _by_file(unresolved_link).items():
        out.append((
            "warning",
            f"{file} imports {_examples(group)} ({_lines(group)}), which is not in the standards snapshot, so it "
            "loads nothing. Run /update-profile to rewrite what it can and report the rest.",
        ))
    for file, group in _by_file(plain).items():
        out.append((
            "warning",
            f"{file} names {_examples(group)} ({_lines(group)}) without a leading @, so it loads nothing. "
            "Run /update-profile to make it an import.",
        ))

    if imports and _approval(config, checkout.root) is False:
        out.append((
            "warning",
            "This project imports the coding standards but has not approved external imports, so none of them "
            "load. Start an interactive session here and accept the external imports prompt.",
        ))

    out.extend(("warning", text) for text in _settings_warnings(checkout.root, home))

    if session == "plugin-dir" and snapshot is not None and snapshot != plugin_root.resolve():
        if any(r.origin == "link" for r in imports):
            out.append((
                "notice",
                f"This is a --plugin-dir session. This project's standards imports read the installed snapshot at "
                f"{snapshot} through {LINK}, while its tools and hooks come from {plugin_root}. Edits in "
                "that working tree do not show up in the instructions.",
            ))
    return out


def main(argv: list) -> int:
    parser = argparse.ArgumentParser(
        prog="standards_imports.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    cmd = sub.add_parser("refs", help="list instruction files and their standards paths")
    cmd.add_argument("--cwd", type=Path, default=Path.cwd())
    cmd.add_argument("--snapshot", type=Path, help="a snapshot directory to resolve paths against")
    cmd.add_argument("--json", action="store_true", help="accepted for symmetry; output is always JSON")
    cmd = sub.add_parser("check", help="print the warnings check-setup.sh shows for a project")
    cmd.add_argument("--cwd", type=Path, default=Path.cwd())
    cmd.add_argument("--plugin-root", type=Path, required=True)
    cmd.add_argument("--session", choices=("installed", "plugin-dir"), required=True)
    cmd.add_argument("--home", type=Path, default=Path.home())
    cmd.add_argument("--link", type=Path, help="defaults to the plugin link under --home")
    cmd.add_argument("--claude-json", type=Path, help="defaults to .claude.json under --home")
    args = parser.parse_args(argv)
    if args.command == "check":
        return run_check(args)
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


def run_check(args: argparse.Namespace) -> int:
    home = args.home
    link = args.link or home / ".claude" / "coding-standards-current"
    config = args.claude_json or home / ".claude.json"
    try:
        results = check(args.cwd, args.plugin_root, args.session, link, home, config)
    except ImportsError as err:
        print(f"standards_imports.py: {err}", file=sys.stderr)
        return 1
    for level, text in results:
        print(f"{level}: {' '.join(text.split())}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
