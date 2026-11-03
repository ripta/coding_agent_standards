"""Tests for link-current.sh. Run: uv run --with pytest pytest claude/hooks"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

HOOK = Path(__file__).parent / "link-current.sh"
KEY = "coding-standards@market"


def snapshot(home: Path, version: str) -> Path:
    """Create an installed plugin snapshot under home's plugin cache."""
    root = home / ".claude" / "plugins" / "cache" / "market" / "coding-standards" / version
    root.mkdir(parents=True)
    return root


def record(home: Path, content: object) -> None:
    """Write the plugin install record. A str is written as is, anything else as JSON."""
    path = home / ".claude" / "plugins" / "installed_plugins.json"
    path.write_text(content if isinstance(content, str) else json.dumps(content))


def installed(*paths: Path) -> dict:
    return {"version": 2, "plugins": {KEY: [{"scope": "user", "installPath": str(p)} for p in paths]}}


def run(home: Path, root: Path) -> Path | None:
    """Run the hook as a session whose plugin root is root. Return where the link points."""
    env = {**os.environ, "HOME": str(home), "CLAUDE_PLUGIN_ROOT": str(root)}
    subprocess.run([HOOK], env=env, capture_output=True, text=True, check=True)
    link = home / ".claude" / "coding-standards-current"
    return Path(os.readlink(link)) if link.is_symlink() else None


def test_no_record_links_the_session_snapshot(tmp_path: Path) -> None:
    old = snapshot(tmp_path, "old")

    assert run(tmp_path, old) == old


def test_a_listed_snapshot_links_itself(tmp_path: Path) -> None:
    new = snapshot(tmp_path, "new")
    record(tmp_path, installed(new))

    assert run(tmp_path, new) == new


def test_a_stale_session_links_the_installed_snapshot(tmp_path: Path) -> None:
    old, new = snapshot(tmp_path, "old"), snapshot(tmp_path, "new")
    record(tmp_path, installed(new))
    run(tmp_path, new)

    assert run(tmp_path, old) == new


def test_any_listed_scope_counts_as_installed(tmp_path: Path) -> None:
    user, project = snapshot(tmp_path, "user"), snapshot(tmp_path, "project")
    record(tmp_path, installed(user, project))

    assert run(tmp_path, project) == project


def test_a_missing_installed_snapshot_falls_back_to_the_session(tmp_path: Path) -> None:
    old = snapshot(tmp_path, "old")
    record(tmp_path, installed(old.with_name("gone")))

    assert run(tmp_path, old) == old


def test_an_installed_path_outside_the_cache_is_ignored(tmp_path: Path) -> None:
    old = snapshot(tmp_path, "old")
    elsewhere = tmp_path / "checkout"
    elsewhere.mkdir()
    record(tmp_path, installed(elsewhere))

    assert run(tmp_path, old) == old


def test_an_unreadable_record_falls_back_to_the_session(tmp_path: Path) -> None:
    old = snapshot(tmp_path, "old")
    record(tmp_path, "{not json")

    assert run(tmp_path, old) == old


def test_a_working_tree_is_never_linked(tmp_path: Path) -> None:
    new = snapshot(tmp_path, "new")
    record(tmp_path, installed(new))
    tree = tmp_path / "checkout"
    tree.mkdir()

    assert run(tmp_path, tree) is None
