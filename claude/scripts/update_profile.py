#!/usr/bin/env python3
"""Add or replace a project's profile imports, and rewrite imports of the old checkout paths.

    python3 update_profile.py plan PROFILE [PROFILE ...] [--cwd DIR]
    python3 update_profile.py apply PROFILE [PROFILE ...] [--cwd DIR] [--target FILE]
                                    [--mode keep|replace] [--per-file collapse|keep]

`plan` reads the instruction files Claude Code loads for DIR and prints, as JSON, what it found
and every line-level edit it would make. `apply` recomputes that plan from the same flags and
writes it, so the plan cannot go stale between the two. The caller asks the user for the target
file, the mode, and the per-file handling, and passes the answers as flags.

Imports go onto the plugin link, `~/.claude/coding-standards-current`, and are checked against
the snapshot the link points at. An import that does not resolve there is skipped and reported.
The script never deletes prose, never edits settings files, and never commits. It reports
whether the project approved external imports and never grants approval.

Exit status: 0 on success, 1 on a failure that stops the run, 3 when `apply` found a file it
cannot write and wrote nothing. Errors go to stderr. Everything else is JSON on stdout.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

import standards_imports as si

EXIT_UNWRITABLE = 3
DEFAULT_MODE = "keep"
DEFAULT_PER_FILE = "collapse"
COPY_IN = (
    "This worktree has no CLAUDE.local.md, so the coding standards it imports in {main} do not load. "
    "List CLAUDE.local.md in {root}/.worktreeinclude so new worktrees get a copy, and copy it into this one."
)


class UpdateError(Exception):
    """A failure that stops the run; the message says what and how to fix it."""


def home_dir() -> Path:
    return Path(os.path.expanduser("~"))


def load_snapshot() -> Path:
    link = home_dir() / ".claude" / "coding-standards-current"
    if link.is_symlink() and not link.exists():
        raise UpdateError(
            f"{link} points at a directory that no longer exists. Update the coding-standards plugin and "
            "start a new session so it repoints the link"
        )
    if not link.is_dir():
        raise UpdateError(
            f"{link} does not exist. Install or update the coding-standards plugin and start a new session "
            "so it creates the link"
        )
    if not (link / "profiles").is_dir():
        raise UpdateError(f"{link} has no profiles/. Update the coding-standards plugin to a version that ships them")
    return link


def available_profiles(snapshot: Path) -> list:
    return sorted(p.stem for p in (snapshot / "profiles").glob("*.md"))


def check_profiles(snapshot: Path, names: list) -> list:
    known = available_profiles(snapshot)
    for name in names:
        if name not in known:
            raise UpdateError(f"unknown profile {name!r}. Available profiles: {', '.join(known)}")
    return list(dict.fromkeys(names))


@dataclass
class Entry:
    path: Path
    text: str
    exists: bool
    main_copy: bool = False
    has_twin: bool = True
    aliases: list = field(default_factory=list)
    refs: list = field(default_factory=list)

    @property
    def real(self) -> Path:
        return self.path.resolve()


def read_entry(path: Path, **kwargs) -> Entry:
    try:
        text = path.read_bytes().decode("utf-8")
    except FileNotFoundError:
        return Entry(path, "", False, **kwargs)
    except (OSError, UnicodeDecodeError) as err:
        raise UpdateError(f"cannot read {path}: {err}") from err
    entry = Entry(path, text, True, **kwargs)
    entry.refs = si.parse_text(text, str(path))
    return entry


def collect(checkout: si.Checkout) -> tuple:
    """Return (entries, pairs). Entries are the loaded files, then the main checkout's CLAUDE.local.md files."""
    entries = [read_entry(group[0], aliases=group[1:]) for group in si.instruction_groups(checkout)]
    loaded = {e.real for e in entries}
    pairs = si.main_copies(checkout)
    for mine, theirs in pairs:
        if theirs.resolve() not in loaded:
            entries.append(read_entry(theirs, main_copy=True, has_twin=mine.resolve() in loaded))
    return entries, pairs


def choose_target(entries: list) -> tuple:
    """Return (target, candidates): the file that already imports the standards, else None."""
    candidates = [e for e in entries if e.refs and not (e.main_copy and e.has_twin)]
    with_profile = [e for e in candidates if any(r.profile for r in e.refs)]
    pool = with_profile or candidates
    return (pool[0] if pool else None), candidates


@dataclass
class Context:
    snapshot: Path
    requested: list
    closure: set
    mode: str
    per_file: str
    is_target: bool


@dataclass
class Result:
    entry: Entry
    new_text: str
    edits: list = field(default_factory=list)
    skipped: list = field(default_factory=list)
    flagged: list = field(default_factory=list)
    collapsible: int = 0

    @property
    def changed(self) -> bool:
        return self.new_text != self.entry.text or not self.entry.exists


def link_import(rel: str) -> str:
    return f"@{si.LINK}/{rel}"


def decide(ref: si.Ref, ctx: Context, placed: set, result: Result) -> tuple:
    """Return (action, fresh profile). Actions: keep, rewrite, convert, collapse, swap, drop."""
    where = {"file": ref.file, "line": ref.line, "text": ("@" if ref.at else "") + ref.path}
    if ref.rel is None:
        result.skipped.append({**where, "reason": "no mapping for this path under the old prefix"})
        return "keep", None

    name = ref.profile
    if ctx.is_target and ctx.mode == "replace" and name is not None and name not in ctx.requested:
        fresh = next((p for p in ctx.requested if p not in placed), None)
        if fresh:
            placed.add(fresh)
            return "swap", fresh
        return "drop", None

    if not si.in_snapshot(ctx.snapshot, ref.rel):
        result.skipped.append({**where, "reason": f"{ref.rel} is not in the snapshot"})
        return "keep", None

    if ref.kind == "linktarget":
        return ("retarget" if ref.origin == "old" else "keep"), None
    if ref.kind == "plain":
        return "convert", None
    if ctx.is_target and name is None and ref.rel in ctx.closure:
        result.collapsible += 1
        if ctx.per_file == "collapse":
            return "collapse", None
    return ("rewrite" if ref.kind == "old" else "keep"), None


REASONS = {
    "rewrite": "old checkout path moved onto the link",
    "retarget": "old checkout path in a link target moved onto the link",
    "convert": "plain-text standards path made an import",
    "collapse": "the chosen profile already includes this file",
    "swap": "replaces a different profile import",
    "drop": "different profile import removed by replace",
}


def process(entry: Entry, ctx: Context) -> Result:
    result = Result(entry, entry.text)
    lines = entry.text.splitlines(keepends=True)
    by_line: dict = {}
    for ref in entry.refs:
        by_line.setdefault(ref.line, []).append(ref)

    placed = {r.profile for r in entry.refs if ctx.is_target and r.profile in ctx.requested}
    out: list = []
    anchor = None
    anchor_line = 0
    where = str(entry.path)

    for number, raw in enumerate(lines, 1):
        refs = by_line.get(number)
        if not refs:
            out.append(raw)
            continue

        body = raw.rstrip("\r\n")
        eol = raw[len(body) :]
        decisions = [decide(ref, ctx, placed, result) for ref in refs]
        actions = [d[0] for d in decisions]

        if all(a in ("collapse", "drop") for a in actions) and si.is_import_only(body, refs):
            why = REASONS[actions[0]]
            result.edits.append({"file": where, "line": number, "action": "remove", "before": body, "after": None,
                                 "reason": why})
            continue

        new_body = body
        for ref, (action, fresh) in reversed(list(zip(refs, decisions))):
            if action == "keep":
                continue
            if action == "swap":
                replacement = link_import(f"profiles/{fresh}.md")
            elif action == "retarget":
                replacement = f"{si.LINK}/{ref.rel}"
            elif si.in_snapshot(ctx.snapshot, ref.rel):
                replacement = link_import(ref.rel)
            else:
                continue
            new_body = new_body[: ref.start] + replacement + new_body[ref.end :]

        if new_body != body:
            reason = "; ".join(dict.fromkeys(REASONS[a] for a in actions if a in REASONS))
            result.edits.append({"file": where, "line": number, "action": "replace", "before": body,
                                 "after": new_body, "reason": reason})

        prose = not si.is_import_only(body, refs)
        left = [a for a in actions if a in ("collapse", "drop")]
        touched = [a for a in actions if a not in ("keep", "retarget")]
        if prose and ((touched and new_body != body) or left):
            note = "import inside a prose line, kept in place. Trim the line by hand if it is redundant"
            result.flagged.append({"file": where, "line": number, "text": new_body, "reason": note})

        out.append(new_body + eol)
        if any(ref.kind != "linktarget" for ref in refs):
            anchor = len(out)
            anchor_line = number

    if ctx.is_target:
        missing = [p for p in ctx.requested if p not in placed]
        if missing:
            insert(out, anchor, missing, entry.text)
            result.edits.append({
                "file": where,
                "line": anchor_line if anchor is not None else len(lines),
                "action": "insert",
                "before": None,
                "after": "\n".join(link_import(f"profiles/{p}.md") for p in missing),
                "reason": "adds the requested profile" + ("s" if len(missing) > 1 else ""),
            })

    result.new_text = "".join(out)
    return result


def insert(out: list, anchor: Optional[int], names: list, original: str) -> None:
    eol = "\r\n" if "\r\n" in original else "\n"
    new = [link_import(f"profiles/{p}.md") + eol for p in names]
    if anchor is None:
        position = len(out)
        if out and out[-1].strip():
            new.insert(0, eol)
    else:
        position = anchor
    if position > 0 and not out[position - 1].endswith(("\n", "\r")):
        out[position - 1] += eol
    out[position:position] = new


@dataclass
class Setup:
    checkout: si.Checkout
    snapshot: Path
    requested: list
    entries: list
    pairs: list
    target: Optional[Entry]
    candidates: list
    default_target: Path


def setup(profiles: list, cwd: Path) -> Setup:
    snapshot = load_snapshot()
    requested = check_profiles(snapshot, profiles)
    checkout = si.locate(cwd)
    entries, pairs = collect(checkout)
    target, candidates = choose_target(entries)
    name = "CLAUDE.local.md" if "oss-contrib" in requested else "CLAUDE.md"
    return Setup(checkout, snapshot, requested, entries, pairs, target, candidates, checkout.cwd / name)


def with_target(state: Setup, override: Optional[Path]) -> Entry:
    """Return the entry that receives the profile imports, adding it to the entries when it is new."""
    if override is not None:
        path = override if override.is_absolute() else state.checkout.cwd / override
        if not path.parent.is_dir():
            raise UpdateError(f"the directory {path.parent} does not exist, so {path.name} cannot be created there")
        path = path.parent.resolve() / path.name
        for entry in state.entries:
            if entry.real == path.resolve():
                return entry
        entry = read_entry(path)
        state.entries.append(entry)
        return entry
    if state.target is not None:
        return state.target
    for entry in state.entries:
        if entry.real == state.default_target.resolve():
            return entry
    entry = read_entry(state.default_target)
    state.entries.append(entry)
    return entry


def build(state: Setup, target: Entry, mode: str, per_file: str) -> list:
    mirrors = {theirs.resolve() for mine, theirs in state.pairs if mine.resolve() == target.real}
    mirrors |= {mine.resolve() for mine, theirs in state.pairs if theirs.resolve() == target.real}
    closure = si.profile_files(state.snapshot, state.requested)
    results = []
    for entry in state.entries:
        is_target = entry is target or entry.real in mirrors
        results.append(process(entry, Context(state.snapshot, state.requested, closure, mode, per_file, is_target)))
    return results


def notes_for(state: Setup, target: Entry) -> list:
    notes = []
    if target.main_copy and not target.has_twin and state.checkout.main_root is not None:
        main = state.checkout.main_root
        notes.append(COPY_IN.format(main=target.path, root=main))
    return notes


def check_writable(results: list) -> list:
    problems = []
    for result in results:
        if not result.changed:
            continue
        real = result.entry.real
        try:
            if result.entry.exists:
                with open(real, "r+b"):
                    pass
            with tempfile.NamedTemporaryFile(dir=real.parent):
                pass
        except OSError as err:
            problems.append({"path": str(result.entry.path), "error": err.strerror or str(err)})
    return problems


def write_atomically(entry: Entry, text: str) -> None:
    """Replace the real file with a temp file from its own directory, so a failure keeps the original.

    A symlink is followed, so it stays a symlink. The mode is copied from the original.
    """
    real = entry.real
    descriptor, name = tempfile.mkstemp(dir=real.parent, prefix=f".{real.name}.", suffix=".tmp")
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(text.encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        if entry.exists:
            shutil.copymode(real, name)
        else:
            umask = os.umask(0)
            os.umask(umask)
            os.chmod(name, 0o666 & ~umask)
        os.replace(name, real)
    except BaseException:
        try:
            os.unlink(name)
        except OSError:
            pass
        raise


def external_imports(root: Path) -> dict:
    config = home_dir() / ".claude.json"
    info = {"project_root": str(root), "approved": None}
    try:
        data = json.loads(config.read_text())
    except (OSError, ValueError):
        info["note"] = f"{config} is missing or unreadable, so approval is unknown"
        return info
    project = (data.get("projects") or {}).get(str(root)) or {}
    info["approved"] = bool(project.get("hasClaudeMdExternalIncludesApproved"))
    if not info["approved"]:
        info["note"] = (
            "This project has not approved external imports, so none of the standards load. Start an "
            "interactive session here and accept the external imports prompt. Only the user can approve it."
        )
    return info


def summarize(results: list) -> dict:
    return {
        "edits": [e for r in results for e in r.edits],
        "skipped": [s for r in results for s in r.skipped],
        "flagged_prose": [f for r in results for f in r.flagged],
    }


def plan(args: argparse.Namespace) -> dict:
    state = setup(args.profiles, args.cwd)
    target = with_target(state, None)
    files = [
        {"path": str(e.path), "aliases": [str(a) for a in e.aliases], "main_copy": e.main_copy,
         "has_worktree_copy": e.has_twin,
         "refs": [r.to_json() for r in e.refs]}
        for e in state.entries
        if e.exists
    ]
    all_refs = [r for e in state.entries for r in e.refs]
    existing = [r.to_json() for r in all_refs if r.profile]
    different = [r.to_json() for r in target.refs if r.profile and r.profile not in state.requested]

    base = build(state, target, "keep", DEFAULT_PER_FILE)
    collapsible = sum(r.collapsible for r in base)
    modes = ["keep", "replace"] if different else ["keep"]
    per_files = ["collapse", "keep"] if collapsible else ["collapse"]
    variants = []
    for mode in modes:
        for per_file in per_files:
            results = base if (mode, per_file) == ("keep", DEFAULT_PER_FILE) else build(state, target, mode, per_file)
            variants.append({"mode": mode, "per_file": per_file, **summarize(results)})

    chosen = state.target
    return {
        "project_root": str(state.checkout.root),
        "main_checkout": str(state.checkout.main_root) if state.checkout.main_root else None,
        "link": si.LINK,
        "snapshot": str(state.snapshot),
        "profiles": state.requested,
        "instruction_files": files,
        "target": str(chosen.path) if chosen else None,
        "target_candidates": [str(e.path) for e in state.candidates],
        "default_target": str(state.default_target),
        "questions": {"target": chosen is None, "mode": bool(different), "per_file": bool(collapsible)},
        "existing_profile_imports": existing,
        "different_profile_imports": different,
        "old_paths": [r.to_json() for r in all_refs if r.kind == "old"],
        "plain_text_paths": [r.to_json() for r in all_refs if r.kind == "plain"],
        "variants": variants,
        "notes": notes_for(state, target),
    }


def apply(args: argparse.Namespace) -> tuple:
    state = setup(args.profiles, args.cwd)
    target = with_target(state, args.target)
    results = build(state, target, args.mode, args.per_file)

    problems = check_writable(results)
    if problems:
        return EXIT_UNWRITABLE, {"applied": False, "unwritable": problems, "written": []}

    written = []
    for result in results:
        if not result.changed:
            continue
        try:
            write_atomically(result.entry, result.new_text)
        except OSError as err:
            raise UpdateError(
                f"wrote {len(written)} file(s) before failing on {result.entry.path}: {err.strerror or err}. "
                f"Written so far: {', '.join(written) or 'none'}"
            ) from err
        written.append(str(result.entry.path))

    return 0, {
        "applied": True,
        "target": str(target.path),
        "mode": args.mode,
        "per_file": args.per_file,
        "written": written,
        "aliases": {str(r.entry.path): [str(a) for a in r.entry.aliases] for r in results if r.entry.aliases},
        **summarize(results),
        "notes": notes_for(state, target),
        "external_imports": external_imports(state.checkout.root),
    }


def main(argv: list) -> int:
    parser = argparse.ArgumentParser(
        prog="update_profile.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("plan", "apply"):
        cmd = sub.add_parser(name)
        cmd.add_argument("profiles", nargs="+", metavar="PROFILE")
        cmd.add_argument("--cwd", type=Path, default=Path.cwd(), help="the project directory; defaults to the current one")
        cmd.add_argument("--json", action="store_true", help="accepted for symmetry; output is always JSON")
    apply_cmd = sub.choices["apply"]
    apply_cmd.add_argument("--target", type=Path, help="the file that receives the profile imports")
    apply_cmd.add_argument(
        "--mode", choices=("keep", "replace"), default=DEFAULT_MODE,
        help="keep different profile imports, or replace them with the requested ones; defaults to keep",
    )
    apply_cmd.add_argument(
        "--per-file", choices=("collapse", "keep"), default=DEFAULT_PER_FILE,
        help="drop import-only lines the profile already includes, or keep every file import; defaults to collapse",
    )
    args = parser.parse_args(argv)
    if not re.search(r"\S", " ".join(args.profiles)):
        parser.error("name at least one profile")
    try:
        if args.command == "plan":
            status, result = 0, plan(args)
        else:
            status, result = apply(args)
    except (UpdateError, si.ImportsError) as err:
        print(f"update_profile.py: {err}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
