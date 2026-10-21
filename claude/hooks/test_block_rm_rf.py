"""Tests for block-rm-rf.sh. Run: uv run --with pytest pytest claude/hooks"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from hooktest import run_hook


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    """A working directory with a full and an empty directory, two files, and a symlink."""
    (tmp_path / "full" / "sub").mkdir(parents=True)
    (tmp_path / "full" / "a").touch()
    (tmp_path / "empty").mkdir()
    (tmp_path / "file.txt").touch()
    (tmp_path / "it's.txt").touch()
    (tmp_path / "link").symlink_to(tmp_path / "full")
    return tmp_path


def run(command: str, tree: Path) -> str | None:
    return run_hook("block-rm-rf.sh", command, cwd=tree, home=tree)


@pytest.mark.parametrize(
    "command",
    [
        "rm -rf full",
        "rm -fr full",
        "rm -Rf full",
        "rm -rfv full",
        "rm -r -f full",
        "rm --recursive --force full",
        "rm -r --force -- full",
        "sudo rm -rf full",
        "/bin/rm -rf full",
        "cd x && rm -rf full",
        "ls foo/ && rm -rf /whatever",
        "ls foo/; rm -rf /whatever",
        "ls foo/ || rm -rf /whatever",
        "ls foo/ & rm -rf /whatever",
        "ls foo/\nrm -rf /whatever",
        "rm -rf /whatever && ls foo/",
        "find . -name x | xargs rm -rf",
        "rm -rf full >/dev/null",
    ],
)
def test_every_spelling_of_recursive_and_force_is_denied(command: str, tree: Path) -> None:
    assert run(command, tree) is not None


@pytest.mark.parametrize(
    "command",
    [
        "rm -r full",
        "rm -f file.txt",
        "rm file.txt && ls -R -f",
        "grep -rn 'rm -rf' .",
        "git rm -r --cached x",
        "unlink file.txt",
        "rmdir empty",
    ],
)
def test_commands_without_both_flags_on_one_rm_are_allowed(command: str, tree: Path) -> None:
    assert run(command, tree) is None


def test_other_tools_are_ignored(tree: Path) -> None:
    assert run_hook("block-rm-rf.sh", "rm -rf full", tool="Edit", cwd=tree) is None


@pytest.mark.parametrize(
    ("operand", "advice"),
    [
        ("file.txt", "file.txt is a file. Use unlink file.txt."),
        ("it's.txt", "it's.txt is a file. Use unlink it's.txt."),
        ("link", "link is a symlink. Use unlink link."),
        ("empty", "empty is an empty directory. Use rmdir empty."),
        ("full", "full is a directory with 2 entries."),
        ("missing", "missing does not exist."),
        ("build/*", "build/* is a pattern or variable."),
        ("$TMPDIR/x", "$TMPDIR/x is a pattern or variable."),
        ("~/file.txt", "~/file.txt is a file. Use unlink ~/file.txt."),
    ],
)
def test_the_reason_advises_on_each_operand(operand: str, advice: str, tree: Path) -> None:
    reason = run(f"rm -rf {operand}", tree)
    assert reason is not None
    assert advice in reason


def test_absolute_operands_ignore_cwd(tree: Path) -> None:
    reason = run(f"rm -rf {tree / 'empty'}", tree)
    assert reason is not None
    assert "is an empty directory" in reason


def test_operands_after_double_dash_are_not_flags(tree: Path) -> None:
    (tree / "-f").touch()
    reason = run("rm -r --force -- -f", tree)
    assert reason is not None
    assert "-f is a file. Use unlink -f." in reason


def test_every_operand_gets_advice(tree: Path) -> None:
    reason = run("rm -rf file.txt empty", tree)
    assert reason is not None
    assert "Use unlink file.txt." in reason
    assert "Use rmdir empty." in reason
