"""Tests for block-private-terms.sh and private-terms.py. Run: uv run --with pytest pytest claude/hooks"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

HOOKS = Path(__file__).parent


@pytest.fixture
def env(tmp_path: Path) -> dict:
    home = tmp_path / "home"
    terms = home / ".config" / "coding_agent_standards" / "private-terms.txt"
    terms.parent.mkdir(parents=True)
    terms.write_text("# employer names\nAcmeCorp\n\nproject falcon\n")

    # A fake gh answers from GH_VISIBILITY and logs each call, so tests never reach the network.
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text('#!/bin/sh\necho call >> "$GH_LOG"\n[ -n "$GH_VISIBILITY" ] || exit 1\necho "$GH_VISIBILITY"\n')
    gh.chmod(0o755)

    e = dict(os.environ)
    e.update(
        HOME=str(home),
        PATH=f"{bin_dir}:{e['PATH']}",
        GH_LOG=str(tmp_path / "gh.log"),
        GH_VISIBILITY="PUBLIC",
        GIT_CONFIG_GLOBAL=os.devnull,
        GIT_CONFIG_NOSYSTEM="1",
    )
    return e


@pytest.fixture
def repo(tmp_path: Path, env: dict) -> Path:
    r = tmp_path / "repo"
    r.mkdir()
    for args in (
        ["init", "-q", "-b", "main"],
        ["config", "user.email", "t@example.com"],
        ["config", "user.name", "t"],
        ["remote", "add", "origin", "git@github.com:someone/repo.git"],
    ):
        subprocess.run(["git", "-C", str(r), *args], check=True, env=env)
    (r / "README.md").write_text("hello\n")
    subprocess.run(["git", "-C", str(r), "add", "README.md"], check=True, env=env)
    subprocess.run(["git", "-C", str(r), "commit", "-qm", "init"], check=True, env=env)
    return r


def stage(repo: Path, env: dict, name: str, text: str) -> None:
    (repo / name).write_text(text)
    subprocess.run(["git", "-C", str(repo), "add", name], check=True, env=env)


def pretooluse(repo: Path, env: dict, command: str, tool: str = "Bash") -> str | None:
    """Return the deny reason, or None when the hook allows the command."""
    payload = {"tool_name": tool, "tool_input": {"command": command}, "cwd": str(repo)}
    result = subprocess.run(
        [HOOKS / "block-private-terms.sh"], input=json.dumps(payload), capture_output=True, text=True, env=env
    )
    assert result.returncode == 0, result.stderr
    if not result.stdout.strip():
        return None
    out = json.loads(result.stdout)["hookSpecificOutput"]
    assert out["permissionDecision"] == "deny"
    return out["permissionDecisionReason"]


def gh_calls(env: dict) -> int:
    log = Path(env["GH_LOG"])
    return len(log.read_text().splitlines()) if log.exists() else 0


def test_a_staged_term_is_denied_in_a_public_repo(repo: Path, env: dict) -> None:
    stage(repo, env, "notes.md", "line one\nlearned at acmecorp\n")
    reason = pretooluse(repo, env, "git commit -m 'Add notes'")
    assert reason is not None
    assert "acmecorp (notes.md:2)" in reason
    assert "public repo" in reason


def test_a_term_in_the_message_is_denied(repo: Path, env: dict) -> None:
    stage(repo, env, "notes.md", "nothing here\n")
    reason = pretooluse(repo, env, 'git commit -m "Port the Project Falcon wiki"')
    assert reason is not None
    assert "Project Falcon (commit command)" in reason


def test_a_commit_by_path_checks_the_working_tree(repo: Path, env: dict) -> None:
    (repo / "README.md").write_text("hello\nAcmeCorp\n")
    reason = pretooluse(repo, env, "git commit -m 'Update' -- README.md")
    assert reason is not None
    assert "README.md:2" in reason


def test_git_dash_c_names_the_repo(repo: Path, env: dict, tmp_path: Path) -> None:
    stage(repo, env, "notes.md", "AcmeCorp\n")
    payload_cwd = tmp_path
    payload = {"tool_name": "Bash", "tool_input": {"command": f"git -C {repo} commit -m x"}, "cwd": str(payload_cwd)}
    result = subprocess.run(
        [HOOKS / "block-private-terms.sh"], input=json.dumps(payload), capture_output=True, text=True, env=env
    )
    assert "AcmeCorp (notes.md:1)" in result.stdout


@pytest.mark.parametrize("text", ["acmecorporation\n", "xAcmeCorp\n", "project falconry\n"])
def test_a_term_inside_a_longer_word_is_allowed(repo: Path, env: dict, text: str) -> None:
    stage(repo, env, "notes.md", text)
    assert pretooluse(repo, env, "git commit -m x") is None


def test_a_removed_line_is_allowed(repo: Path, env: dict) -> None:
    stage(repo, env, "notes.md", "AcmeCorp\n")
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "seed"], check=True, env=env)
    stage(repo, env, "notes.md", "a company\n")
    assert pretooluse(repo, env, "git commit -m x") is None


def test_a_private_repo_is_skipped(repo: Path, env: dict) -> None:
    env["GH_VISIBILITY"] = "PRIVATE"
    stage(repo, env, "notes.md", "AcmeCorp\n")
    assert pretooluse(repo, env, "git commit -m x") is None


def test_declared_visibility_wins_over_the_host(repo: Path, env: dict) -> None:
    subprocess.run(["git", "-C", str(repo), "config", "codingstandards.visibility", "private"], check=True, env=env)
    stage(repo, env, "notes.md", "AcmeCorp\n")
    assert pretooluse(repo, env, "git commit -m x") is None
    assert gh_calls(env) == 0


def test_an_unknown_repo_is_checked_and_names_the_override(repo: Path, env: dict) -> None:
    subprocess.run(["git", "-C", str(repo), "remote", "remove", "origin"], check=True, env=env)
    stage(repo, env, "notes.md", "AcmeCorp\n")
    reason = pretooluse(repo, env, "git commit -m x")
    assert reason is not None
    assert "visibility is unknown" in reason
    assert "config codingstandards.visibility private" in reason


def test_a_failed_lookup_is_unknown_and_not_cached(repo: Path, env: dict) -> None:
    env["GH_VISIBILITY"] = ""
    stage(repo, env, "notes.md", "AcmeCorp\n")
    assert "visibility is unknown" in pretooluse(repo, env, "git commit -m x")
    pretooluse(repo, env, "git commit -m x")
    assert gh_calls(env) == 2


def test_a_public_result_is_cached(repo: Path, env: dict) -> None:
    stage(repo, env, "notes.md", "AcmeCorp\n")
    pretooluse(repo, env, "git commit -m x")
    pretooluse(repo, env, "git commit -m x")
    assert gh_calls(env) == 1


def test_an_expired_private_result_is_looked_up_again(repo: Path, env: dict) -> None:
    cache = Path(env["HOME"]) / ".local" / "state" / "coding_agent_standards" / "term-guard" / "visibility.json"
    cache.parent.mkdir(parents=True)
    url = "git@github.com:someone/repo.git"
    cache.write_text(json.dumps({url: {"visibility": "private", "checked": 0}}))
    stage(repo, env, "notes.md", "AcmeCorp\n")
    assert pretooluse(repo, env, "git commit -m x") is not None
    assert gh_calls(env) == 1


def test_no_term_file_allows_everything(repo: Path, env: dict) -> None:
    (Path(env["HOME"]) / ".config" / "coding_agent_standards" / "private-terms.txt").unlink()
    stage(repo, env, "notes.md", "AcmeCorp\n")
    assert pretooluse(repo, env, "git commit -m x") is None


@pytest.mark.parametrize("command", ["git status", "grep AcmeCorp notes.md", "git log --oneline"])
def test_other_commands_are_ignored(repo: Path, env: dict, command: str) -> None:
    stage(repo, env, "notes.md", "AcmeCorp\n")
    assert pretooluse(repo, env, command) is None


def test_other_tools_are_ignored(repo: Path, env: dict) -> None:
    stage(repo, env, "notes.md", "AcmeCorp\n")
    assert pretooluse(repo, env, "git commit -m x", tool="Edit") is None


def test_git_pre_commit_blocks_a_staged_term(repo: Path, env: dict) -> None:
    stage(repo, env, "notes.md", "AcmeCorp\n")
    result = subprocess.run(
        [HOOKS / "private-terms.py", "pre-commit"], cwd=repo, capture_output=True, text=True, env=env
    )
    assert result.returncode == 1
    assert "AcmeCorp (notes.md:1)" in result.stderr
    assert "--no-verify" in result.stderr


def test_git_commit_msg_ignores_comment_lines(repo: Path, env: dict, tmp_path: Path) -> None:
    message = tmp_path / "MSG"
    message.write_text("Add notes\n# AcmeCorp in a comment\n")
    script = HOOKS / "private-terms.py"
    ok = subprocess.run([script, "commit-msg", message], cwd=repo, capture_output=True, text=True, env=env)
    assert ok.returncode == 0

    message.write_text("Add AcmeCorp notes\n")
    bad = subprocess.run([script, "commit-msg", message], cwd=repo, capture_output=True, text=True, env=env)
    assert bad.returncode == 1
    assert "AcmeCorp (commit message)" in bad.stderr
