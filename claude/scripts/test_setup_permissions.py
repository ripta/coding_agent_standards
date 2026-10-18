"""Tests for setup_permissions.py. Run: uv run --with pytest pytest claude/scripts"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import setup_permissions

EDIT_RULE = "Edit(~/.local/state/coding_agent_standards/**)"
STATE_DIR = "~/.local/state/coding_agent_standards"


def test_an_empty_file_gets_every_managed_entry() -> None:
    new, changes = setup_permissions.plan({})
    assert new == {"permissions": {"allow": [EDIT_RULE]}, "sandbox": {"filesystem": {"allowWrite": [STATE_DIR]}}}
    assert len(changes) == 2


def test_other_keys_and_entries_are_kept_in_order() -> None:
    old = {
        "theme": "light",
        "permissions": {"allow": ["Read", "Bash(ls:*)"], "deny": ["Read(~/.aws/**)"]},
        "sandbox": {"enabled": True},
    }
    new, _ = setup_permissions.plan(old)
    assert new["theme"] == "light"
    assert new["permissions"]["allow"] == ["Read", "Bash(ls:*)", EDIT_RULE]
    assert new["permissions"]["deny"] == ["Read(~/.aws/**)"]
    assert new["sandbox"] == {"enabled": True, "filesystem": {"allowWrite": [STATE_DIR]}}
    assert old["permissions"]["allow"] == ["Read", "Bash(ls:*)"]


def test_a_settled_file_needs_no_change() -> None:
    settled, _ = setup_permissions.plan({})
    again, changes = setup_permissions.plan(settled)
    assert (again, changes) == (settled, [])


def test_duplicates_are_dropped_keeping_the_first() -> None:
    old = {"permissions": {"allow": ["Read", "WebSearch", "Read", EDIT_RULE]}, "hooks": {"x": [1, 1]}}
    new, changes = setup_permissions.plan(old)
    assert new["permissions"]["allow"] == ["Read", "WebSearch", EDIT_RULE]
    assert new["hooks"] == {"x": [1, 1]}
    assert changes[0] == "drop duplicate permissions.allow: Read"


def test_retired_entries_are_removed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(setup_permissions, "RETIRED", {("permissions", "allow"): ["Edit(~/old/**)"]})
    new, changes = setup_permissions.plan({"permissions": {"allow": ["Edit(~/old/**)", "Read"]}})
    assert new["permissions"]["allow"] == ["Read", EDIT_RULE]
    assert "remove retired permissions.allow: Edit(~/old/**)" in changes


def test_a_key_of_the_wrong_shape_is_an_error() -> None:
    with pytest.raises(setup_permissions.SetupError, match="permissions.allow is not a list"):
        setup_permissions.plan({"permissions": {"allow": "Read"}})


def test_check_reports_and_never_writes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "settings.json"
    path.write_text('{"theme": "light"}\n')
    assert setup_permissions.main(["--settings", str(path), "--check"]) == 1
    assert path.read_text() == '{"theme": "light"}\n'
    assert "needs 2 change(s)" in capsys.readouterr().out


def test_writing_refuses_inside_a_coding_agent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "settings.json"
    path.write_text("{}\n")
    monkeypatch.setenv("CLAUDECODE", "1")
    assert setup_permissions.main(["--settings", str(path)]) == 2
    assert path.read_text() == "{}\n"


def test_write_keeps_a_backup_and_the_mode(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text("{}\n")
    path.chmod(0o600)
    backup = setup_permissions.write(path, setup_permissions.render({"a": 1}))
    assert json.loads(path.read_text()) == {"a": 1}
    assert backup is not None and backup.read_text() == "{}\n"
    assert path.stat().st_mode & 0o777 == 0o600
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted(["settings.json", backup.name])


def test_invalid_json_is_an_error(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text("{")
    assert setup_permissions.main(["--settings", str(path), "--check"]) == 2
