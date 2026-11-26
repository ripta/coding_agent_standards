"""Tests for revisit-notice.sh. Run: uv run --with pytest pytest claude/hooks"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

HOOK = Path(__file__).parent / "revisit-notice.sh"
PLUGIN_ROOT = Path(__file__).resolve().parents[1]

PROPOSAL = """# PROJ-001: Title

**Status:** deferred
**Created:** 2020-01-01
**Updated:** 2020-01-01
**Revisit:** on or after 2020-02-01 (a release)

## Milestones

### M1: Step 1

**Status:** NOT STARTED

- Check 1

## Decision Log

- 2020-01-01: Created.
"""


def git(cwd: Path, *args: str) -> None:
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
    config = ["-c", "user.name=t", "-c", "user.email=t@example.com", "-c", "protocol.file.allow=always"]
    subprocess.run(["git", *config, *args], cwd=cwd, env=env, check=True, capture_output=True)


def proposals(directory: Path, name: str = "PROJ-001-a.md", text: str = PROPOSAL) -> Path:
    """Write a proposals directory holding one deferred proposal whose revisit date has passed."""
    directory.mkdir(parents=True)
    (directory / name).write_text(text)
    return directory


def notices(root: Path, plugin_root: Path = PLUGIN_ROOT) -> list[str]:
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(root), "CLAUDE_PLUGIN_ROOT": str(plugin_root)}
    result = subprocess.run([HOOK], env=env, capture_output=True, text=True, check=True)
    return result.stdout.splitlines()


@pytest.fixture
def root(tmp_path: Path) -> Path:
    r = tmp_path / "project"
    r.mkdir()
    return r


def committed(root: Path) -> Path:
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "init", "--allow-empty")
    return root


@pytest.mark.parametrize("parent", ["spec", "docs"])
def test_a_passed_hook_in_the_root_proposals_is_noticed(root: Path, parent: str) -> None:
    proposals(root / parent / "proposals")

    out = notices(root)

    assert len(out) == 1
    assert out[0].startswith("1 revisit hook has passed")
    assert str(root / parent / "proposals") in out[0]


def test_a_project_with_no_hook_prints_nothing(root: Path) -> None:
    proposals(root / "docs" / "proposals", text=PROPOSAL.replace("**Revisit:** on or after 2020-02-01 (a release)\n", ""))

    assert notices(root) == []


def test_a_project_with_no_proposals_prints_nothing(root: Path) -> None:
    (root / "docs").mkdir()

    assert notices(root) == []


def test_a_missing_script_prints_nothing(root: Path, tmp_path: Path) -> None:
    proposals(root / "docs" / "proposals")

    assert notices(root, plugin_root=tmp_path / "no-plugin") == []


@pytest.mark.parametrize("tracked", [True, False])
def test_every_proposals_directory_in_a_monorepo_is_checked(root: Path, tracked: bool) -> None:
    """Catches the loop stopping at the root. Each app keeps its own proposals, and each has its own hooks."""
    proposals(root / "apps" / "x" / "docs" / "proposals")
    proposals(root / "apps" / "y" / "spec" / "proposals")
    proposals(root / "spec" / "proposals")
    if tracked:
        committed(root)
    else:
        git(root, "init", "-q", "-b", "main")

    out = notices(root)

    assert len(out) == 3
    for rel in ("apps/x/docs/proposals", "apps/y/spec/proposals", "spec/proposals"):
        assert sum(str(root / rel) in line for line in out) == 1, f"{rel} is named by one notice"


def test_both_spec_and_docs_at_the_root_are_checked(root: Path) -> None:
    proposals(root / "spec" / "proposals")
    proposals(root / "docs" / "proposals")

    assert len(notices(root)) == 2


def test_an_untracked_proposals_directory_in_a_git_repo_is_checked(root: Path) -> None:
    committed(root)
    proposals(root / "apps" / "x" / "docs" / "proposals")

    assert len(notices(root)) == 1


def test_a_gitignored_directory_is_not_searched(root: Path) -> None:
    """Vendored trees carry docs/proposals of their own, and those belong to someone else."""
    (root / ".gitignore").write_text("node_modules/\n")
    proposals(root / "node_modules" / "pkg" / "docs" / "proposals")
    committed(root)

    assert notices(root) == []


def test_node_modules_is_not_searched_outside_git(root: Path) -> None:
    proposals(root / "node_modules" / "pkg" / "docs" / "proposals")
    proposals(root / "docs" / "proposals")

    out = notices(root)

    assert len(out) == 1
    assert str(root / "node_modules") not in out[0]


# -- a specs directory kept outside the repo and linked in (tracking.md, "Specs Directory") --------


def central(tmp_path: Path, name: str = "central") -> Path:
    return proposals(tmp_path / name / "proposals")


@pytest.mark.parametrize("parent", ["spec", "docs"])
def test_a_symlinked_root_specs_directory_is_checked(root: Path, tmp_path: Path, parent: str) -> None:
    (root / parent).symlink_to(central(tmp_path).parent)

    out = notices(committed(root))

    assert len(out) == 1
    assert str(root / parent / "proposals") in out[0]


def test_a_gitignored_symlink_is_checked(root: Path, tmp_path: Path) -> None:
    """A link to a path on this machine is kept out of the repo, so git ls-files never lists it."""
    (root / "apps" / "x").mkdir(parents=True)
    (root / "apps" / "x" / "spec").symlink_to(central(tmp_path).parent)
    (root / ".gitignore").write_text("spec\n")
    (root / "apps" / "x" / "keep").write_text("x\n")

    out = notices(committed(root))

    assert len(out) == 1
    assert str(root / "apps" / "x" / "spec" / "proposals") in out[0]


def test_a_tracked_symlink_below_the_root_is_checked(root: Path, tmp_path: Path) -> None:
    (root / "apps" / "x").mkdir(parents=True)
    (root / "apps" / "x" / "docs").symlink_to(central(tmp_path).parent)

    out = notices(committed(root))

    assert len(out) == 1
    assert str(root / "apps" / "x" / "docs" / "proposals") in out[0]


def test_one_central_directory_linked_twice_is_noticed_once(root: Path, tmp_path: Path) -> None:
    target = central(tmp_path).parent
    for rel in ("apps/x/spec", "apps/y/spec"):
        (root / rel).parent.mkdir(parents=True)
        (root / rel).symlink_to(target)

    assert len(notices(committed(root))) == 1


def test_a_symlinked_directory_outside_git_is_checked(root: Path, tmp_path: Path) -> None:
    (root / "apps" / "x").mkdir(parents=True)
    (root / "apps" / "x" / "spec").symlink_to(central(tmp_path).parent)

    assert len(notices(root)) == 1


# -- submodules ----------------------------------------------------------------------------------


def test_a_submodule_with_its_own_proposals_is_checked(root: Path, tmp_path: Path) -> None:
    lib = tmp_path / "lib"
    proposals(lib / "docs" / "proposals")
    git(lib, "init", "-q", "-b", "main")
    git(lib, "add", "-A")
    git(lib, "commit", "-qm", "lib")
    git(root, "init", "-q", "-b", "main")
    git(root, "submodule", "add", "-q", str(lib), "apps/lib")
    git(root, "commit", "-qm", "add lib")

    out = notices(root)

    assert len(out) == 1
    assert str(root / "apps" / "lib" / "docs" / "proposals") in out[0]
