"""Tests for toolcalls.py. Run: uv run --with pytest pytest claude/hooks"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from toolcalls import CG_RUN, CG_RUN_MANY, BadPayload, mentions, shell_script_index, tool_commands


@pytest.fixture(autouse=True)
def no_project_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    """A session that runs the tests may set CLAUDE_PROJECT_DIR, which `tool_commands` reads."""
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"tool_name": "Bash", "tool_input": {"command": "ls -la"}, "cwd": "/w"}, [("ls -la", "/w")]),
        ({"tool_name": "Bash", "tool_input": {}, "cwd": "/w"}, [("", "/w")]),
        ({"tool_name": CG_RUN, "tool_input": {"command": ["ls", "-la"], "cwd": ""}, "cwd": "/w"}, [("ls -la", "/w")]),
        ({"tool_name": CG_RUN, "tool_input": {"command": ["ls"], "cwd": "/other"}, "cwd": "/w"}, [("ls", "/other")]),
        ({"tool_name": CG_RUN, "tool_input": {"command": ["ls"], "cwd": "sub"}, "cwd": "/w"}, [("ls", "/w/sub")]),
        (
            {"tool_name": CG_RUN, "tool_input": {"command": ["bash", "-c", "a b; c"]}, "cwd": "/w"},
            [("bash -c 'a b; c'", "/w")],
        ),
        (
            {"tool_name": CG_RUN, "tool_input": {"command": ["rm", "two words"]}, "cwd": "/w"},
            [("rm 'two words'", "/w")],
        ),
        (
            {"tool_name": CG_RUN_MANY, "tool_input": {"commands": [["ls"], ["pwd"]], "cwd": "sub"}, "cwd": "/w"},
            [("ls", "/w/sub"), ("pwd", "/w/sub")],
        ),
        ({"tool_name": CG_RUN, "tool_input": {"command": None}, "cwd": "/w"}, []),
        ({"tool_name": CG_RUN_MANY, "tool_input": {"commands": [None, "ls", ["pwd"]]}, "cwd": "/w"}, [("pwd", "/w")]),
        ({"tool_name": "Edit", "tool_input": {"command": "ls"}, "cwd": "/w"}, []),
        ({"tool_name": CG_RUN, "cwd": "/w"}, []),
        (
            {"tool_name": CG_RUN, "tool_input": {"command": ["git", "commit"], "env": {"GIT_DIR": "/a b/.git"}}, "cwd": "/w"},
            [("GIT_DIR='/a b/.git' git commit", "/w")],
        ),
        (
            {"tool_name": CG_RUN, "tool_input": {"command": ["ls"], "env": {"PATH": "/x", "GIT_WORK_TREE": "t"}}, "cwd": "/w"},
            [("GIT_WORK_TREE=t ls", "/w")],
        ),
        (
            {"tool_name": CG_RUN_MANY, "tool_input": {"commands": [["a"], ["b"]], "env": {"GIT_DIR": "g"}}, "cwd": "/w"},
            [("GIT_DIR=g a", "/w"), ("GIT_DIR=g b", "/w")],
        ),
        ({"tool_name": CG_RUN, "tool_input": {"command": ["ls"], "env": {"A": "1"}}, "cwd": "/w"}, [("ls", "/w")]),
        ({"tool_name": CG_RUN, "tool_input": {"command": ["ls"], "env": ["GIT_DIR=x"]}, "cwd": "/w"}, [("ls", "/w")]),
        ({"tool_name": "Bash", "tool_input": {"command": "ls", "env": {"GIT_DIR": "x"}}, "cwd": "/w"}, [("ls", "/w")]),
    ],
)
def test_each_tool_gives_the_shell_text_and_directory_it_runs(payload: dict, expected: list) -> None:
    """Catches a cg argv read as one word, a cg cwd taken from the wrong base, or a `GIT_` variable in
    a cg call's `env` that never reaches the text. Every hook that scans command text reads this, so
    a miss here is a miss in each of them."""
    assert tool_commands(payload) == expected


def test_an_empty_cg_cwd_names_both_the_payload_directory_and_the_server_directory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The payload's cwd follows the Bash tool's persisted `cd`. The cg server runs in the directory
    it started in, which is the project directory. A call with no cwd runs in the second, so a guard
    that reads only the first checks the wrong repo."""
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", "/proj")

    payload = {"tool_name": CG_RUN, "tool_input": {"command": ["ls"], "cwd": ""}, "cwd": "/w"}

    assert tool_commands(payload) == [("ls", "/w"), ("ls", "/proj")]


def test_a_relative_cg_cwd_is_read_from_both_bases(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", "/proj")

    payload = {"tool_name": CG_RUN_MANY, "tool_input": {"commands": [["ls"]], "cwd": "sub"}, "cwd": "/w"}

    assert tool_commands(payload) == [("ls", "/w/sub"), ("ls", "/proj/sub")]


@pytest.mark.parametrize(
    ("given_cwd", "project"),
    [("", "/w"), ("/abs", "/proj"), ("/abs", "/w"), ("", None), ("", "")],
)
def test_one_directory_is_listed_once(monkeypatch: pytest.MonkeyPatch, given_cwd: str, project: str | None) -> None:
    """An absolute cwd, or a project directory equal to the payload's, leaves nothing to check twice."""
    if project is not None:
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", project)

    payload = {"tool_name": CG_RUN, "tool_input": {"command": ["ls"], "cwd": given_cwd}, "cwd": "/w"}

    assert len(tool_commands(payload)) == 1


def test_bash_runs_only_in_the_payload_directory(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", "/proj")

    payload = {"tool_name": "Bash", "tool_input": {"command": "ls"}, "cwd": "/w"}

    assert tool_commands(payload) == [("ls", "/w")]


def test_nul_bytes_are_dropped_as_bash_drops_them() -> None:
    """A NUL in a word crashed the guards, and an exit of 1 lets the call run."""
    bash = {"tool_name": "Bash", "tool_input": {"command": "git -C '/x\0' commit"}, "cwd": "/w\0"}
    cg = {"tool_name": CG_RUN, "tool_input": {"command": ["git", "-C", "/x\0", "commit"], "cwd": "s\0ub"}, "cwd": "/w"}

    assert tool_commands(bash) == [("git -C '/x' commit", "/w")]
    assert tool_commands(cg) == [("git -C /x commit", "/w/sub")]


@pytest.mark.parametrize(
    "payload",
    [
        {"tool_name": "Bash", "tool_input": {"command": ["git", "commit"]}},
        {"tool_name": "Bash", "tool_input": {"command": 5}},
        {"tool_name": "Bash", "tool_input": "git commit"},
        {"tool_name": CG_RUN, "tool_input": {"command": "git commit"}},
        {"tool_name": CG_RUN_MANY, "tool_input": {"commands": "git commit"}},
        {"tool_name": CG_RUN, "tool_input": ["git", "commit"]},
        ["Bash", "git commit"],
    ],
)
def test_a_payload_in_the_wrong_shape_is_reported_and_not_guessed_at(payload: object) -> None:
    """A TypeError from a non-string command exited 1, which does not block. The guards turn this
    error into a denial when the call mentions their command."""
    with pytest.raises(BadPayload):
        tool_commands(payload)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("text", "word", "expected"),
    [
        ("git commit -m x", "commit", True),
        ("git com''mit -m x", "commit", True),
        ("git com\\mit", "commit", True),
        ('{"command": "git \\"c\\"ommit"}', "commit", True),
        ("git COMMIT", "commit", True),
        ("git status", "commit", False),
        ("ls", "rm", False),
        ("r''m -rf x", "rm", True),
        ("rm -rf x", "rm", True),
    ],
)
def test_mentions_reads_a_word_through_quoting(text: str, word: str, expected: bool) -> None:
    assert mentions(text, word) is expected


@pytest.mark.parametrize(
    ("words", "expected"),
    [
        (["-c", "rm x"], 1),
        (["-lc", "rm x"], 1),
        (["-xc", "rm x"], 1),
        (["-O", "extglob", "-c", "rm x"], 3),
        (["+O", "extglob", "-c", "rm x"], 3),
        (["-o", "pipefail", "-c", "rm x"], 3),
        (["+o", "pipefail", "-c", "rm x"], 3),
        (["-eo", "pipefail", "-c", "rm x"], 3),
        (["-euo", "pipefail", "-c", "rm x"], 3),
        (["-co", "pipefail", "rm x"], 2),
        (["-O", "extglob", "-O", "globstar", "-c", "rm x"], 5),
        (["--norc", "-c", "rm x"], 2),
        (["--rcfile", "f", "-c", "rm x"], 3),
        (["--init-file", "f", "-c", "rm x"], 3),
        (["--", "-c", "rm x"], None),
        (["-c", "--", "rm x"], 2),
        (["script.sh", "-c"], None),
        (["-O", "extglob", "script.sh"], None),
        (["-x"], None),
        (["-c"], None),
        ([], None),
    ],
)
def test_the_script_a_shell_runs_is_found_past_its_options(words: list, expected: int | None) -> None:
    """Catches an option that takes a value, such as `-O extglob`, read as the script or as the end of
    the options. The guards that scan a shell's script share this."""
    assert shell_script_index(words) == expected
