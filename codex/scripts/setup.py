#!/usr/bin/env python3
"""Check or repair baseline setup using only the installed Codex plugin."""

import argparse
import fcntl
import os
import runpy
import shlex
import sys
from pathlib import Path


def has_reference(text, home):
    paths = [str(home / "coding-standards-current" / "baseline.md")]
    if home == (Path.home() / ".codex").resolve():
        paths.append("~/.codex/coding-standards-current/baseline.md")
    return any(path in text for path in paths)


def instruction_file(directory):
    override = directory / "AGENTS.override.md"
    return override if override.is_file() and override.stat().st_size else directory / "AGENTS.md"


def instruction_files(home, project):
    directories = []
    for directory in (project, *project.parents):
        directories.append(directory)
        if (directory / ".git").exists():
            break
    for directory in (home, *reversed(directories)):
        yield instruction_file(directory)


def check(root, home, project):
    issues = []
    link = home / "coding-standards-current"
    if not link.is_symlink() or link.resolve() != root:
        issues.append(f"{link} does not point to this installed plugin")
    if not (root / "baseline.md").is_file():
        issues.append(f"{root} is missing baseline.md; reinstall the plugin")
    if not any(has_reference(path.read_text(), home)
               for path in instruction_files(home, project) if path.is_file()):
        issues.append("Active AGENTS.md instructions do not reference the installed baseline")
        override = home / "AGENTS.override.md"
        if override.is_file():
            issues.append(f"{override} hides global AGENTS.md; add the baseline reference there or in the project")
    return issues


def apply(root, home):
    runpy.run_path(str(root / "hooks" / "link-current.py"))["link_current"](root, home)
    instructions = instruction_file(home)
    baseline = home / "coding-standards-current" / "baseline.md"
    # Serialize repeated setup runs without replacing the user's instruction file.
    with instructions.open("a+") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        stream.seek(0)
        existing = stream.read()
        if not has_reference(existing, home):
            stream.write(
                ("\n\n" if existing else "")
                + "## Shared coding standards\n\n"
                + f"Read and follow `{baseline}`, including every document it lists,\n"
                + "before working on any project. If the file is missing, report the missing standards\n"
                + "and repair the plugin installation before proceeding.\n"
            )
    print(f"Baseline enabled in {instructions}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="report missing setup without writing")
    args = parser.parse_args()
    home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")).expanduser().resolve()
    root = Path(__file__).resolve().parents[1]
    if not args.check:
        apply(root, home)
    issues = check(root, home, Path.cwd())
    if issues:
        print("CODING STANDARDS SETUP:")
        for issue in issues:
            print(f"  - {issue}")
        print(f"Run: python3 {shlex.quote(str(root / 'scripts' / 'setup.py'))}")
        return 1
    if args.check:
        print("Coding standards setup is complete.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError) as error:
        sys.exit(f"coding-standards setup: {error}")
