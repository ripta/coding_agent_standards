"""Tests for check-setup.sh. Run: uv run --with pytest pytest claude/hooks"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

HOOK = Path(__file__).parent / "check-setup.sh"


def run(tmp_path: Path, stub: str) -> str:
    """Run the hook against a plugin root whose setup_permissions.py is stub, outside any git repo."""
    root = tmp_path / "plugin"
    (root / "scripts").mkdir(parents=True)
    (root / "scripts" / "setup_permissions.py").write_text(stub)

    home = tmp_path / "home"
    home.mkdir()
    env = {**os.environ, "HOME": str(home), "CLAUDE_PLUGIN_ROOT": str(root)}
    env.pop("GIT_DIR", None)

    result = subprocess.run([HOOK], cwd=tmp_path, env=env, capture_output=True, text=True, check=True)
    return result.stdout


@pytest.mark.parametrize("code", [0, 3])
def test_complete_settings_print_nothing(tmp_path: Path, code: int) -> None:
    assert run(tmp_path, f"import sys; sys.exit({code})") == ""


def test_missing_entries_ask_for_setup(tmp_path: Path) -> None:
    out = run(tmp_path, "import sys; sys.exit(5)")

    assert "lacks entries" in out


def test_a_crash_is_not_reported_as_missing_entries(tmp_path: Path) -> None:
    out = run(tmp_path, "raise TypeError(\"unsupported operand type(s) for |\")")

    assert "lacks entries" not in out
    assert "could not run" in out
    assert "TypeError: unsupported operand type(s) for |" in out


# -- project section: the bash glue around standards_imports.py check -------------------------
# Which warnings a project earns is owned by test_standards_imports.py. These tests prove only
# what the script adds: the output format, the prefix split, the degraded paths, and the guards.

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
LINK = "~/.claude/coding-standards-current"
CHECKOUT = "~/projects/coding_agent_standards"
SNAPSHOT = {"profiles/p.md": "p\n", "rules/a.md": "a\n"}
GOOD = f"@{LINK}/profiles/p.md\n"
OLD = f"@{CHECKOUT}/claude/rules/a.md\n"


def git(cwd: Path, *args: str) -> None:
    env = {**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null"}
    config = ["-c", "user.name=t", "-c", "user.email=t@example.com", "-c", "commit.gpgsign=false"]
    subprocess.run(["git", *config, *args], cwd=cwd, env=env, check=True, capture_output=True)


def snapshot(path: Path) -> Path:
    for rel, text in SNAPSHOT.items():
        (path / rel).parent.mkdir(parents=True, exist_ok=True)
        (path / rel).write_text(text)
    return path


class World:
    """A fake HOME, an installed snapshot, a --plugin-dir tree, a link, and a git project."""

    def __init__(self, tmp: Path) -> None:
        self.tmp = tmp.resolve()
        self.home = self.tmp / "home"
        (self.home / ".claude").mkdir(parents=True)
        self.installed = snapshot(self.home / ".claude" / "plugins" / "cache" / "m" / "coding-standards" / "1.0")
        self.dev = snapshot(self.tmp / "dev" / "claude")
        for root in (self.installed, self.dev):
            (root / "scripts").mkdir(exist_ok=True)
            (root / "scripts" / "standards_imports.py").write_text((SCRIPTS / "standards_imports.py").read_text())
            (root / "scripts" / "setup_permissions.py").write_text("import sys; sys.exit(0)")
        self.link = self.home / ".claude" / "coding-standards-current"
        self.project = self.tmp / "project"
        self.project.mkdir()
        git(self.project, "init", "-q")
        git(self.project, "commit", "-q", "--allow-empty", "-m", "init")
        self.approve()

    def write(self, files: dict) -> None:
        for rel, text in files.items():
            path = self.project / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)

    def approve(self) -> None:
        entry = {"hasClaudeMdExternalIncludesApproved": True}
        (self.home / ".claude.json").write_text(json.dumps({"projects": {str(self.project): entry}}))

    def run(self, session: str = "installed", cwd: Path | None = None, **env_overrides: str) -> str:
        env = {**os.environ, "HOME": str(self.home), "CLAUDE_PLUGIN_ROOT": str(self.installed if session == "installed" else self.dev)}
        env.pop("GIT_DIR", None)
        env.update(env_overrides)
        result = subprocess.run([HOOK], cwd=cwd or self.project, env=env, capture_output=True, text=True, check=True)
        return result.stdout


@pytest.fixture
def world(tmp_path: Path) -> World:
    return World(tmp_path)


def test_a_project_in_order_prints_nothing(world: World) -> None:
    """The hook runs at every session start, so a good project must cost the user no context."""
    world.write({"CLAUDE.md": GOOD})

    assert world.run() == ""


def test_a_warning_is_listed_under_the_setup_header(world: World) -> None:
    """Catches the python output reaching Claude unformatted, or in place of the list."""
    world.write({"CLAUDE.md": OLD})

    out = world.run().splitlines()

    assert out[0] == "CODING STANDARDS SETUP:"
    assert out[1].startswith("  - ") and "old standards path" in out[1]
    assert len(out) == 2


def test_a_notice_prints_before_the_setup_list_and_not_in_it(world: World) -> None:
    """A notice is not a setup problem. Catches the prefix split putting it in the list or dropping it."""
    world.link.symlink_to(snapshot(world.tmp / "other"))
    world.write({"CLAUDE.md": GOOD + OLD})

    out = world.run("plugin-dir").splitlines()

    assert out[0].startswith("coding-standards: This is a --plugin-dir session")
    assert out[1] == "CODING STANDARDS SETUP:"
    assert len(out) == 3 and "old standards path" in out[2]


def test_this_repo_prints_nothing(world: World) -> None:
    """This repo imports its working tree by relative path, so the checks and the notice do not apply."""
    world.link.symlink_to(snapshot(world.tmp / "other"))
    world.write({"claude/.claude-plugin/plugin.json": "{}", "CLAUDE.md": OLD})

    assert world.run("plugin-dir") == ""


def test_a_worktree_of_the_standards_repo_prints_nothing(world: World) -> None:
    """The guard reads the main checkout, so a linked worktree of this repo is skipped too."""
    world.write({"claude/.claude-plugin/plugin.json": "{}"})
    git(world.project, "add", "claude")
    git(world.project, "commit", "-q", "-m", "plugin")
    tree = world.tmp / "tree"
    git(world.project, "worktree", "add", "-q", str(tree), "-b", "tree")
    (tree / "CLAUDE.md").write_text(OLD)

    assert world.run(cwd=tree) == ""


def test_a_worktree_without_the_local_file_is_told_to_copy_it(world: World) -> None:
    """Only a worktree's own CLAUDE.local.md loads, so the main checkout's import does nothing there."""
    world.write({"CLAUDE.local.md": GOOD})
    tree = world.tmp / "tree"
    git(world.project, "worktree", "add", "-q", str(tree), "-b", "tree")

    out = world.run(cwd=tree)

    assert ".worktreeinclude" in out
    assert "does not import" not in out


def test_outside_a_git_checkout_nothing_is_checked(world: World) -> None:
    """The project section runs only inside a work tree."""
    plain = world.tmp / "plain"
    plain.mkdir()

    assert world.run(cwd=plain) == ""


def test_old_git_without_path_format_still_finds_this_repo(world: World, tmp_path: Path) -> None:
    """git before 2.31 echoes --path-format back as an argument and prints a relative path.

    The guard then read a garbage main checkout and stopped recognizing this repo, so its sessions
    got import warnings about their own standards.
    """
    real = shutil.which("git")
    bin_dir = tmp_path / "fakebin"
    bin_dir.mkdir()
    fake = bin_dir / "git"
    fake.write_text(
        '#!/bin/sh\n'
        'case "$1" in rev-parse) shift; if [ "$1" = "--path-format=absolute" ]; then echo "$1"; shift; fi; '
        f'exec {real} rev-parse "$@" ;; esac\n'
        f'exec {real} "$@"\n'
    )
    fake.chmod(0o755)
    world.write({"claude/.claude-plugin/plugin.json": "{}", "CLAUDE.md": OLD})

    assert world.run(PATH=f"{bin_dir}:{os.environ['PATH']}") == ""


# -- degradation ----------------------------------------------------------------------------


def test_missing_python_warns_once_and_the_hook_still_exits_zero(world: World, tmp_path: Path) -> None:
    """The hook runs on every session start. A machine without python3 gets one short line, not a failed hook."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name in ("bash", "git", "dirname", "mkdir"):
        (bin_dir / name).symlink_to(shutil.which(name))
    world.write({"CLAUDE.md": GOOD})

    out = world.run(PATH=str(bin_dir))

    assert out.count("\n  - ") == 1
    assert "python3" in out


def test_an_empty_plugin_root_warns_once_and_the_hook_still_exits_zero(world: World) -> None:
    """With no root the script cannot be found. That is one short warning, not a crash on a missing path."""
    world.write({"CLAUDE.md": GOOD})

    out = world.run(CLAUDE_PLUGIN_ROOT="")

    assert out.count("\n  - ") == 1
    assert "CLAUDE_PLUGIN_ROOT" in out


def test_a_crashing_check_warns_with_the_error_and_the_hook_still_exits_zero(world: World) -> None:
    """A crash in the import check must be visible, and must not fail the hook."""
    (world.installed / "scripts" / "standards_imports.py").write_text('raise RuntimeError("boom")\n')
    world.write({"CLAUDE.md": GOOD})

    out = world.run()

    assert "could not run" in out
    assert "RuntimeError: boom" in out


def test_session_test_matches_link_current() -> None:
    """Drift guard. Both hooks must call the same roots installed, or this one checks a link it does not own."""
    line = '"$HOME"/.claude/plugins/cache/*) '
    assert line in HOOK.read_text()
    assert line in (HOOK.parent / "link-current.sh").read_text()
