"""Tests for block-rm-rf.sh. Run: uv run --with pytest pytest claude/hooks"""

from __future__ import annotations

import json
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


@pytest.mark.parametrize(
    "command",
    [
        "bash -c 'rm -rf full'",
        'bash -c "rm -rf full"',
        "sh -c 'rm -rf full'",
        "zsh -c 'rm -rf full'",
        "bash -lc 'rm -rf full'",
        "bash -euo pipefail -c 'rm -rf full'",
        "/bin/bash -c 'cd x && rm -rf full'",
        "sudo bash -c 'rm -rf full'",
        "bash -c \"bash -c 'rm -rf full'\"",
        "eval 'rm -rf full'",
        "eval rm -rf full",
        "(rm -rf full)",
        "(cd x; rm -rf full)",
        "echo $(rm -rf full)",
        'echo "$(rm -rf full)"',
        "echo `rm -rf full`",
        'echo "`rm -rf full`"',
        "cat <(rm -rf full)",
        "\\rm -rf full",
        "sudo \\rm -rf full",
        "'rm' -rf full",
        '"rm" -rf full',
        "bash <<EOF\nrm -rf full\nEOF",
        "bash <<< 'rm -rf full'",
    ],
)
def test_wrapped_and_quoted_spellings_are_denied(command: str, tree: Path) -> None:
    """Catches a wrapper the word splitter used to read as a quoted string."""
    assert run(command, tree) is not None


@pytest.mark.parametrize(
    "command",
    [
        "echo it's fine\nrm -rf full",
        "# it's a comment\nrm -rf full",
        "cat <<'EOF'\nit's text\nEOF\nrm -rf full",
        "cat <<-EOF\n\tit's text\n\tEOF\nrm -rf full",
        "git commit -m \"$(cat <<'EOF'\nit's text\nEOF\n)\" && rm -rf full",
        'echo "it\'s" && rm -rf full',
    ],
)
def test_an_apostrophe_in_text_does_not_hide_a_later_delete(command: str, tree: Path) -> None:
    """Catches a quote-aware scanner that reads prose as the start of a quoted string."""
    assert run(command, tree) is not None


@pytest.mark.parametrize(
    "command",
    [
        "grep 'rm -rf' file.txt",
        'grep "rm -rf" file.txt',
        "grep 'rm' -rf src",
        "echo 'rm -rf is dangerous'",
        'echo "rm -rf is dangerous"',
        "echo '$(rm -rf full)'",
        "echo '`rm -rf full`'",
        "echo 'bash -c \"rm -rf full\"'",
        "# rm -rf full",
        "cat <<EOF\nrm -rf full\nEOF",
        "git commit -m \"$(cat <<'EOF'\nStop using rm -rf full here\nEOF\n)\"",
        "git commit -m 'rm -rf is gone'",
        "bash -c 'echo hi'",
        "bash -c \"grep 'rm -rf' .\"",
        "rm a-br/b-dotfiles.json",
        "git log --format='%s' -- format.rmf",
    ],
)
def test_text_that_only_mentions_the_delete_is_allowed(command: str, tree: Path) -> None:
    """Catches a false positive. The plugin wires this hook for everyone, so these would recur."""
    assert run(command, tree) is None


def test_the_plugin_wires_the_guard_on_bash() -> None:
    """Catches the guard shipping unwired, which leaves a machine with no guard and no warning."""
    config = json.loads((Path(__file__).parent / "hooks.json").read_text())
    commands = [
        hook["command"]
        for group in config["hooks"]["PreToolUse"]
        if group.get("matcher") == "Bash"
        for hook in group["hooks"]
    ]
    assert '"${CLAUDE_PLUGIN_ROOT}"/hooks/block-rm-rf.sh' in commands


def test_a_quoted_operand_is_advised_on_as_one_name(tree: Path) -> None:
    (tree / "two words.txt").touch()
    reason = run("rm -rf 'two words.txt'", tree)
    assert reason is not None
    assert "two words.txt is a file. Use unlink two words.txt." in reason


def test_advice_reaches_inside_a_wrapper(tree: Path) -> None:
    reason = run("bash -c 'rm -rf file.txt'", tree)
    assert reason is not None
    assert "Use unlink file.txt." in reason


def test_redirect_targets_are_not_operands(tree: Path) -> None:
    reason = run("rm -rf empty >out.log 2>err.log", tree)
    assert reason is not None
    assert "Use rmdir empty." in reason
    assert "out.log" not in reason
    assert "err.log" not in reason
    assert " 2 " not in reason


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
