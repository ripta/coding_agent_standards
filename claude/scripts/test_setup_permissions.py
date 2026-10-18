"""Tests for setup_permissions.py. Run: uv run --with pytest pytest claude/scripts"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import setup_permissions

ALLOW = setup_permissions.MANAGED[("permissions", "allow")]
WRITE = setup_permissions.MANAGED[("sandbox", "filesystem", "allowWrite")]


def test_an_empty_file_gets_every_managed_entry() -> None:
    new, changes = setup_permissions.plan({})
    assert new == {"permissions": {"allow": ALLOW}, "sandbox": {"filesystem": {"allowWrite": WRITE}}}
    assert len(changes) == len(ALLOW) + len(WRITE)


def test_other_keys_and_entries_are_kept_in_order() -> None:
    old = {
        "theme": "light",
        "permissions": {"allow": ["Read", "Bash(ls:*)"], "deny": ["Read(~/.aws/**)"]},
        "sandbox": {"enabled": True},
    }
    new, _ = setup_permissions.plan(old)
    assert new["theme"] == "light"
    assert new["permissions"]["allow"] == ["Read", "Bash(ls:*)", *ALLOW]
    assert new["permissions"]["deny"] == ["Read(~/.aws/**)"]
    assert new["sandbox"] == {"enabled": True, "filesystem": {"allowWrite": WRITE}}
    assert old["permissions"]["allow"] == ["Read", "Bash(ls:*)"]


def test_a_settled_file_needs_no_change() -> None:
    settled, _ = setup_permissions.plan({})
    again, changes = setup_permissions.plan(settled)
    assert (again, changes) == (settled, [])


def test_duplicates_are_dropped_keeping_the_first() -> None:
    old = {"permissions": {"allow": ["Read", "WebSearch", "Read", *ALLOW]}, "hooks": {"x": [1, 1]}}
    new, changes = setup_permissions.plan(old)
    assert new["permissions"]["allow"] == ["Read", "WebSearch", *ALLOW]
    assert new["hooks"] == {"x": [1, 1]}
    assert changes[0] == "drop duplicate permissions.allow: Read"


@pytest.mark.parametrize(
    "broad, narrow, expected",
    [
        ("Bash(grep:*)", "Bash(grep -h:*)", True),
        ("Bash(zig build:*)", "Bash(zig build test:*)", True),
        ("Bash(zig-out/bin/1z:*)", "Bash(zig-out/bin/1z)", True),
        ("Bash(git:*)", "Bash(gitk:*)", False),
        ("Bash(grep -h:*)", "Bash(grep:*)", False),
        ("WebFetch(domain:*)", "WebFetch(domain:github.com)", True),
        ("Read", "Read(~/.aws/**)", True),
        ("Read(~/**)", "Read(~/.aws/**)", False),
        ("Bash(sed -e:*)", "Bash(sed -n:*)", False),
        ("Edit", "Read(x)", False),
    ],
)
def test_covers(broad: str, narrow: str, expected: bool) -> None:
    assert setup_permissions.covers(broad, narrow) is expected


def test_covered_rules_are_dropped_within_one_list_only() -> None:
    old = {
        "permissions": {
            "allow": ["Bash(grep -h:*)", "Bash(grep:*)", "WebFetch(domain:*)", "WebFetch(domain:a.com)"],
            "deny": ["Bash(grep -h:*)"],
        }
    }
    new, changes = setup_permissions.plan(old)
    assert new["permissions"]["allow"] == ["Bash(grep:*)", "WebFetch(domain:*)", *ALLOW]
    assert new["permissions"]["deny"] == ["Bash(grep -h:*)"]
    assert "drop permissions.allow: Bash(grep -h:*), covered by Bash(grep:*)" in changes


def test_a_managed_entry_is_never_dropped_as_covered() -> None:
    settled, _ = setup_permissions.plan({"permissions": {"allow": ["Edit"]}})
    assert settled["permissions"]["allow"] == ["Edit", *ALLOW]
    assert setup_permissions.plan(settled)[1] == []


def test_hooks_the_plugin_already_runs_are_dropped(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(Path, "home", lambda: Path("/Users/me"))
    plugin_json = tmp_path / "hooks.json"
    plugin_json.write_text(json.dumps({"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [
        {"type": "command", "command": '"${CLAUDE_PLUGIN_ROOT}"/hooks/block-broad-find.sh'}]}]}}))
    plugin = setup_permissions.plugin_hooks(plugin_json)
    assert plugin == {("PreToolUse", "Bash", "hooks/block-broad-find.sh")}

    def hook(command: str) -> dict[str, str]:
        return {"type": "command", "command": command}

    old = {"hooks": {"PreToolUse": [
        {"matcher": "Bash", "hooks": [
            hook("$HOME/projects/coding_agent_standards/claude/hooks/block-broad-find.sh"),
            hook("$HOME/projects/coding_agent_standards/claude/hooks/block-redirection.sh"),
            hook("echo hi"),
            hook("echo hi"),
        ]},
        {"matcher": "Edit", "hooks": [hook("/Users/me/coding-standards/claude/hooks/block-broad-find.sh")]},
        {"matcher": "Bash", "hooks": [hook("~/.claude/coding-standards-current/hooks/block-broad-find.sh")]},
    ]}}
    new, changes = setup_permissions.plan(old, plugin)
    assert new["hooks"]["PreToolUse"] == [
        {"matcher": "Bash", "hooks": [
            hook("$HOME/projects/coding_agent_standards/claude/hooks/block-redirection.sh"),
            hook("echo hi"),
        ]},
        {"matcher": "Edit", "hooks": [hook("/Users/me/coding-standards/claude/hooks/block-broad-find.sh")]},
    ]
    assert sum(c.startswith("drop hook the plugin already runs") for c in changes) == 2
    assert sum(c.startswith("drop duplicate hook") for c in changes) == 1


def test_retired_entries_are_removed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(setup_permissions, "RETIRED", {("permissions", "allow"): ["Edit(~/old/**)"]})
    new, changes = setup_permissions.plan({"permissions": {"allow": ["Edit(~/old/**)", "Read"]}})
    assert new["permissions"]["allow"] == ["Read", *ALLOW]
    assert "remove retired permissions.allow: Edit(~/old/**)" in changes


def test_a_key_of_the_wrong_shape_is_an_error() -> None:
    with pytest.raises(setup_permissions.SetupError, match="permissions.allow is not a list"):
        setup_permissions.plan({"permissions": {"allow": "Read"}})


def test_check_reports_and_never_writes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "settings.json"
    path.write_text('{"theme": "light"}\n')
    assert setup_permissions.main(["--settings", str(path), "--check"]) == 1
    assert path.read_text() == '{"theme": "light"}\n'
    assert f"needs {len(ALLOW) + len(WRITE)} change(s)" in capsys.readouterr().out


def test_check_exits_3_when_only_cleanup_is_pending(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    settled, _ = setup_permissions.plan({})
    settled["permissions"]["allow"].append("Bash(ls:*)")
    settled["permissions"]["allow"].append("Bash(ls -l:*)")
    path.write_text(json.dumps(settled))
    assert setup_permissions.main(["--settings", str(path), "--check"]) == 3


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
