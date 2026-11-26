"""Tests for block-rm-rf.sh. Run: uv run --with pytest pytest claude/hooks"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from hooktest import run_hook, run_tool_hook


CG_RUN, CG_RUN_MANY = "mcp__cg__cg_run", "mcp__cg__cg_run_many"


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


def test_the_plugin_wires_the_guard_to_every_tool_it_reads() -> None:
    """Catches the guard shipping unwired, or wired to Bash alone. The cg tools then skip it."""
    config = json.loads((Path(__file__).parent / "hooks.json").read_text())
    groups = [
        group["matcher"]
        for group in config["hooks"]["PreToolUse"]
        if any(h["command"].endswith("/hooks/block-rm-rf.sh") for h in group["hooks"])
    ]

    for tool in ("Bash", CG_RUN, CG_RUN_MANY):
        assert any(re.fullmatch(m, tool) for m in groups), f"{tool} is not matched by {groups}"


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


def cg_run(argv: list | None, tree: Path, cwd: str = "") -> str | None:
    return run_tool_hook("block-rm-rf.sh", CG_RUN, {"command": argv, "cwd": cwd}, cwd=tree, home=tree)


def cg_run_many(argvs: list, tree: Path, cwd: str = "") -> str | None:
    return run_tool_hook("block-rm-rf.sh", CG_RUN_MANY, {"commands": argvs, "cwd": cwd}, cwd=tree, home=tree)


@pytest.mark.parametrize(
    "argv",
    [
        ["rm", "-rf", "full"],
        ["rm", "-r", "-f", "full"],
        ["rm", "--recursive", "--force", "full"],
        ["/bin/rm", "-rf", "full"],
        ["sudo", "rm", "-rf", "full"],
        ["xargs", "rm", "-rf"],
        ["bash", "-c", "rm -rf full"],
        ["sh", "-c", "cd x && rm -rf full"],
        ["bash", "-lc", "echo hi; rm -rf full"],
        ["eval", "rm -rf full"],
    ],
)
def test_cg_run_denies_every_spelling_of_the_delete(argv: list, tree: Path) -> None:
    """Catches the guard reading only Bash. rules/shell-discipline.md sends agents through cg_run."""
    assert cg_run(argv, tree) is not None


@pytest.mark.parametrize(
    "argv",
    [
        ["rm", "-r", "full"],
        ["rm", "-f", "file.txt"],
        ["rm", "file.txt"],
        ["unlink", "file.txt"],
        ["grep", "-rn", "rm -rf", "."],
        ["bash", "-c", "echo hi"],
        ["bash", "-c", "grep 'rm -rf' ."],
        ["echo", "rm -rf full"],
        [],
        None,
    ],
)
def test_cg_run_allows_commands_without_both_flags_on_one_rm(argv: list | None, tree: Path) -> None:
    """Catches a false positive from reading a whole argv word as text to scan, or a crash on an empty argv."""
    assert cg_run(argv, tree) is None


def test_cg_run_many_checks_every_command(tree: Path) -> None:
    reason = cg_run_many([["ls", "-la"], ["rm", "-rf", "file.txt"]], tree)
    assert reason is not None
    assert "Use unlink file.txt." in reason


def test_cg_run_many_allows_a_pool_with_no_delete(tree: Path) -> None:
    assert cg_run_many([["ls", "-la"], ["rm", "-r", "full"], ["bash", "-c", "echo hi"]], tree) is None


def test_cg_run_advises_from_the_cg_cwd(tree: Path) -> None:
    """Catches advice read from the session directory when the call runs elsewhere."""
    reason = cg_run(["rm", "-rf", "a"], tree, cwd=str(tree / "full"))
    assert reason is not None
    assert "a is a file. Use unlink a." in reason


def test_cg_run_many_advises_from_the_shared_cwd(tree: Path) -> None:
    reason = cg_run_many([["rm", "-rf", "a"]], tree, cwd=str(tree / "full"))
    assert reason is not None
    assert "a is a file. Use unlink a." in reason


def test_cg_run_advises_on_an_operand_with_spaces_as_one_name(tree: Path) -> None:
    (tree / "two words.txt").touch()
    reason = cg_run(["rm", "-rf", "two words.txt"], tree)
    assert reason is not None
    assert "two words.txt is a file. Use unlink two words.txt." in reason


@pytest.mark.parametrize(
    "command",
    [
        "r''m -rf full",
        'r"m" -rf full',
        "r\\m -rf full",
        "bash -c \"r''m -rf full\"",
        "'r'm -rf full",
        "rm -r''f full",
        "rm -r\\f full",
    ],
)
def test_a_command_name_split_by_quotes_is_still_the_delete(command: str, tree: Path) -> None:
    """The wrapper once let only a payload that held the text `rm` through, and the scanner joins quoted
    pieces. The text `r''m` held no `rm`, so a delete spelled that way was never scanned."""
    assert run(command, tree) is not None


@pytest.mark.parametrize(
    "argv",
    [
        ["bash", "-c", "r''m -rf x"],
        ["bash", "-O", "extglob", "-c", "rm -rf x"],
        ["bash", "+O", "extglob", "-c", "rm -rf x"],
        ["bash", "-O", "extglob", "-O", "globstar", "-c", "rm -rf x"],
        ["bash", "-o", "pipefail", "-c", "rm -rf x"],
        ["bash", "+o", "pipefail", "-c", "rm -rf x"],
        ["bash", "-eo", "pipefail", "-c", "rm -rf x"],
        ["bash", "--norc", "-c", "rm -rf x"],
        ["bash", "--rcfile", "rc", "-c", "rm -rf x"],
        ["zsh", "-O", "extglob", "-c", "rm -rf x"],
    ],
)
def test_cg_run_reads_a_shell_script_past_the_shells_options(argv: list, tree: Path) -> None:
    """Catches an option that takes a value read as the end of the options, so the script after it is
    never scanned. `-O` and `+O` take a shell option name, `+o` takes a `set -o` name."""
    assert cg_run(argv, tree) is not None


@pytest.mark.parametrize(
    "command",
    [
        "bash -O extglob -c 'rm -rf full'",
        "bash +O extglob -c 'rm -rf full'",
        "bash --rcfile rc -c 'rm -rf full'",
        "bash >/dev/null -O extglob -c 'rm -rf full'",
        "sudo bash -O extglob -c 'rm -rf full'",
    ],
)
def test_bash_reads_a_shell_script_past_the_shells_options(command: str, tree: Path) -> None:
    assert run(command, tree) is not None


@pytest.mark.parametrize(
    "argv",
    [
        ["bash", "-O", "extglob", "-c", "echo hi"],
        ["bash", "-O", "extglob", "script.sh", "rm -rf x"],
        ["bash", "script.sh", "-c", "rm -rf x"],
        ["bash", "--rcfile", "rc", "script.sh", "rm -rf x"],
    ],
)
def test_a_shell_that_runs_a_file_is_not_given_the_scripts_after_it(argv: list, tree: Path) -> None:
    """Only `-c` makes the next word a script. The words after a script file are its arguments."""
    assert cg_run(argv, tree) is None


def test_a_cg_call_with_no_cwd_is_advised_from_both_directories(tree: Path, tmp_path_factory) -> None:
    """The payload's cwd follows the Bash tool's `cd`. The cg server runs where it started. The delete
    runs in the second, so the advice reads both."""
    server = tmp_path_factory.mktemp("server")
    (server / "full").touch()

    reason = run_tool_hook(
        "block-rm-rf.sh", CG_RUN, {"command": ["rm", "-rf", "full"], "cwd": ""}, cwd=tree, home=tree, project_dir=server
    )

    assert reason is not None
    assert f"From {tree}: full is a directory with 2 entries." in reason
    assert f"From {server}: full is a file. Use unlink full." in reason


def test_a_cg_call_with_the_same_directory_twice_is_advised_once(tree: Path) -> None:
    reason = run_tool_hook(
        "block-rm-rf.sh", CG_RUN, {"command": ["rm", "-rf", "file.txt"]}, cwd=tree, home=tree, project_dir=tree
    )

    assert reason is not None
    assert reason.count("Use unlink file.txt.") == 1
    assert "From " not in reason


def test_a_cg_call_with_an_absolute_cwd_ignores_the_project_directory(tree: Path, tmp_path_factory) -> None:
    server = tmp_path_factory.mktemp("server")
    (server / "file.txt").mkdir()

    reason = run_tool_hook(
        "block-rm-rf.sh",
        CG_RUN,
        {"command": ["rm", "-rf", "file.txt"], "cwd": str(tree)},
        cwd=server,
        home=tree,
        project_dir=server,
    )

    assert reason is not None
    assert "file.txt is a file. Use unlink file.txt." in reason
    assert "From " not in reason


@pytest.mark.parametrize(
    "tool_input",
    [
        {"command": ["rm", "-rf", "x"]},
        {"command": 5, "note": "rm"},
        "rm -rf x",
    ],
)
def test_a_payload_it_cannot_read_that_mentions_rm_is_denied(tool_input: object, tree: Path) -> None:
    """A TypeError from an unexpected shape exited 1, and an exit of 1 does not block the call."""
    reason = run_tool_hook("block-rm-rf.sh", "Bash", tool_input, cwd=tree, home=tree)  # type: ignore[arg-type]

    assert reason is not None
    assert "could not read" in reason


def test_a_payload_it_cannot_read_that_does_not_mention_rm_is_allowed() -> None:
    """No cwd is sent, since a test directory's name may spell `rm`."""
    assert run_tool_hook("block-rm-rf.sh", "Bash", {"command": ["ls"]}) is None
