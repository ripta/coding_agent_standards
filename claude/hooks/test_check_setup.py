"""Tests for check-setup.sh. Run: uv run --with pytest pytest claude/hooks"""

from __future__ import annotations

import os
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
