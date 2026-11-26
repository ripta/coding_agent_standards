"""Tests for block-private-terms.sh and private-terms.py.

Run: uv run --with pytest pytest claude/hooks
"""

from __future__ import annotations

import json
import os
import re
import shutil
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

    # A session that runs the tests may set it, and the guard reads it for a cg call with no cwd.
    e.pop("CLAUDE_PROJECT_DIR", None)
    e.update(
        HOME=str(home),
        PATH=f"{bin_dir}:{e['PATH']}",
        GH_LOG=str(tmp_path / "gh.log"),
        GH_VISIBILITY="PUBLIC",
        GIT_CONFIG_GLOBAL=os.devnull,
        GIT_CONFIG_NOSYSTEM="1",
    )
    return e


def git(env: dict, repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), "-c", "protocol.file.allow=always", *args], check=True, env=env)


def make_repo(path: Path, env: dict) -> Path:
    """Create a repo with one commit. Its remote is public, by the fake host."""
    path.mkdir(parents=True)
    for args in (
        ["init", "-q", "-b", "main"],
        ["config", "user.email", "t@example.com"],
        ["config", "user.name", "t"],
        ["remote", "add", "origin", "git@github.com:someone/repo.git"],
    ):
        git(env, path, *args)
    (path / "README.md").write_text("hello\n")
    git(env, path, "add", "README.md")
    git(env, path, "commit", "-qm", "init")
    return path


@pytest.fixture
def repo(tmp_path: Path, env: dict) -> Path:
    return make_repo(tmp_path / "repo", env)


def stage(repo: Path, env: dict, name: str, text: str) -> None:
    (repo / name).write_text(text)
    subprocess.run(["git", "-C", str(repo), "add", name], check=True, env=env)


def pretooluse(repo: Path, env: dict, command: str, tool: str = "Bash") -> str | None:
    """Return the deny reason, or None when the hook allows the command."""
    return run_hook(env, {"tool_name": tool, "tool_input": {"command": command}, "cwd": str(repo)})


def run_hook(env: dict, payload: dict) -> str | None:
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


# -- which repo a commit goes to ---------------------------------------------------------------
# The guard must read the repo the command commits to, not the repo of the payload's cwd. Each test
# makes the cwd repo private, so a guard that reads it allows the commit and the test fails.


@pytest.fixture
def workspace(tmp_path: Path, env: dict) -> Path:
    """A private superproject `ws` holding the submodule `ws/sub`. The host calls the submodule public."""
    origin = make_repo(tmp_path / "sub-origin", env)
    ws = make_repo(tmp_path / "ws", env)
    git(env, ws, "submodule", "add", "-q", str(origin), "sub")
    git(env, ws, "commit", "-qm", "add sub")
    git(env, ws, "config", "codingstandards.visibility", "private")
    return ws


@pytest.mark.parametrize(
    "command",
    [
        "cd sub && git commit -m x",
        "cd sub; git commit -m x",
        "cd sub\ngit commit -m x",
        "cd ./sub && git commit -m x",
        "cd 'sub' && git commit -m x",
        "cd -- sub && git commit -m x",
        "cd sub/../sub && git commit -m x",
        "cd . && cd sub && git commit -m x",
        "cd sub && git -C . commit -m x",
        "cd sub||exit 1; git commit -m x",
        "(cd sub && git commit -m x)",
        "git commit -m a && cd sub && git commit -m b",
        "bash -c 'cd sub && git commit -m x'",
        "sh -c \"cd sub && git commit -m x\"",
        "cd sub 2>&1 && git commit -m x",
        "cd sub >/dev/null 2>&1 && git commit -m x",
        "cd sub && git commit -m 'fix; tidy && go'",
        'cd sub && git commit -m "$(cat <<\'EOF\'\nPort notes\n\nbody; with && stuff\nEOF\n)"',
        "FOO=1 cd sub && sudo git commit -m x",
    ],
)
def test_cd_before_a_commit_picks_the_repo(workspace: Path, env: dict, command: str) -> None:
    """Catches a guard that reads the cwd repo after `cd` moved into a submodule."""
    stage(workspace / "sub", env, "notes.md", "AcmeCorp\n")

    reason = pretooluse(workspace, env, command)

    assert reason is not None
    assert "AcmeCorp (notes.md:1)" in reason


def test_dash_c_is_relative_to_the_cd(workspace: Path, env: dict, tmp_path: Path) -> None:
    stage(workspace / "sub", env, "notes.md", "AcmeCorp\n")

    reason = pretooluse(tmp_path, env, "cd ws && git -C sub commit -m x")

    assert reason is not None
    assert "AcmeCorp (notes.md:1)" in reason


def test_cd_into_a_sibling_checkout(repo: Path, env: dict, tmp_path: Path) -> None:
    """A polyrepo workspace commits to the sibling checkout, which the cwd repo says nothing about."""
    git(env, repo, "config", "codingstandards.visibility", "private")
    sibling = make_repo(tmp_path / "sibling", env)
    stage(sibling, env, "notes.md", "AcmeCorp\n")

    reason = pretooluse(repo, env, "cd ../sibling && git commit -m x")

    assert reason is not None
    assert "AcmeCorp (notes.md:1)" in reason


def test_cd_to_a_home_relative_path(tmp_path: Path, env: dict) -> None:
    project = make_repo(Path(env["HOME"]) / "proj", env)
    stage(project, env, "notes.md", "AcmeCorp\n")

    reason = pretooluse(tmp_path, env, "cd ~/proj && git commit -m x")

    assert reason is not None
    assert "AcmeCorp (notes.md:1)" in reason


def test_a_cd_in_a_subshell_does_not_leak_out(workspace: Path, env: dict) -> None:
    """The commit runs in ws, which is private. The staged term in sub is not part of it."""
    stage(workspace / "sub", env, "notes.md", "AcmeCorp\n")

    assert pretooluse(workspace, env, "(cd sub && ls); git commit -m x") is None


def test_a_cd_to_a_missing_directory_in_a_private_repo_is_allowed(workspace: Path, env: dict) -> None:
    """The nearest existing directory is in the private workspace, so that is the repo checked."""
    stage(workspace / "sub", env, "notes.md", "AcmeCorp\n")

    assert pretooluse(workspace, env, "cd nowhere && git commit -m x") is None


@pytest.mark.parametrize(
    "command",
    [
        'cd "$SUB" && git commit -m x',
        "cd $(git rev-parse --show-toplevel)/sub && git commit -m x",
        "cd - && git commit -m x",
        "popd && git commit -m x",
        "cd sub* && git commit -m x",
        'git -C "$SUB" commit -m x',
        "cd nowhere || git commit -m x",
        "cd nowhere; git commit -m x",
        "cd nowhere\ngit commit -m x",
        "cd nowhere && ls; git commit -m x",
    ],
)
def test_a_target_it_cannot_follow_is_denied_with_how_to_rerun(workspace: Path, env: dict, command: str) -> None:
    """Catches a guard that falls back to the cwd repo. Here that repo is private and clean, so the
    old fallback allowed the commit. Nothing is staged anywhere, so only the target decides."""
    reason = pretooluse(workspace, env, command)

    assert reason is not None
    assert "cannot tell which repo" in reason
    assert "git -C <path> commit" in reason


@pytest.mark.parametrize(
    "command",
    [
        "G=git; $G commit -m x",
        "$(which git) commit -m x",
        "`which git` commit -m x",
        '"${GIT}" commit -m x',
        "sudo $GIT -C sub commit -m x",
        "FOO=1 $G commit -m x",
        "x=$(date) $G commit -m x",
    ],
)
def test_a_command_word_it_cannot_expand_is_denied(workspace: Path, env: dict, command: str) -> None:
    """The command word may expand to git, so the commit it makes cannot be placed."""
    reason = pretooluse(workspace, env, command)

    assert reason is not None
    assert "git -C <path> commit" in reason


@pytest.mark.parametrize(
    "command",
    [
        'cd "$SUB" && git status',
        'cd "$SUB"; ls',
        "G=git; $G status",
        "echo $(date) and `date`",
        "x=$(date) git status",
        'GIT_DIR="$D" git status',
    ],
)
def test_an_unplaceable_command_that_does_not_commit_is_allowed(workspace: Path, env: dict, command: str) -> None:
    assert pretooluse(workspace, env, command) is None


def test_a_clean_commit_after_a_cd_it_cannot_follow_is_still_denied(workspace: Path, env: dict) -> None:
    """The hook cannot see what the commit carries, so a clean tree does not make it safe."""
    stage(workspace, env, "notes.md", "nothing here\n")

    assert pretooluse(workspace, env, 'cd "$SUB" && git commit -m x') is not None


def test_an_unplaceable_commit_is_allowed_without_a_term_file(workspace: Path, env: dict) -> None:
    (Path(env["HOME"]) / ".config" / "coding_agent_standards" / "private-terms.txt").unlink()

    assert pretooluse(workspace, env, 'cd "$SUB" && git commit -m x') is None


@pytest.mark.parametrize(
    "command",
    [
        "cd nowhere && git commit -m x",
        "mkdir x && cd x && git commit -m x",
        "cd a/b/c && git commit -m x",
        "cd nowhere && ls && git commit -m x",
        "cd nowhere && (git commit -m x)",
        "cd nowhere && { git commit -m x; }",
        "cd nowhere && git commit -m x || echo failed",
    ],
)
def test_a_cd_to_a_missing_directory_checks_the_repo_around_it(repo: Path, env: dict, command: str) -> None:
    """Catches a guard that lets the commit through unchecked. `mkdir x && cd x` makes the directory
    inside the public repo, so the commit lands there. The hook cannot know that, so it checks the
    repo of the nearest directory that exists."""
    stage(repo, env, "notes.md", "AcmeCorp\n")

    reason = pretooluse(repo, env, command)

    assert reason is not None
    assert "AcmeCorp (notes.md:1)" in reason


def test_a_missing_directory_outside_any_repo_is_allowed(repo: Path, env: dict, tmp_path: Path) -> None:
    """The nearest existing directory is in no repo, so there is nothing to check."""
    stage(repo, env, "notes.md", "AcmeCorp\n")

    assert pretooluse(repo, env, f"cd {tmp_path}/outside/nowhere && git commit -m x") is None


@pytest.mark.parametrize("command", ["cd sub/missing/deeper && git commit -m x", "cd sub/../sub/nope && git commit -m x"])
def test_a_missing_directory_below_a_submodule_checks_the_submodule(workspace: Path, env: dict, command: str) -> None:
    """The nearest existing directory is `sub`, whose repo is public, and not the private workspace."""
    stage(workspace / "sub", env, "notes.md", "AcmeCorp\n")

    reason = pretooluse(workspace, env, command)

    assert reason is not None
    assert "AcmeCorp (notes.md:1)" in reason


def test_a_failed_cd_ends_at_the_end_of_its_chain(repo: Path, env: dict) -> None:
    """After `;` the commit runs here or there, so the hook cannot place it and says how to rerun."""
    stage(repo, env, "notes.md", "AcmeCorp\n")

    reason = pretooluse(repo, env, "cd nowhere && ls; git commit -m x")

    assert reason is not None
    assert "git -C <path> commit" in reason


def test_a_subshell_does_not_carry_a_failed_cd_out(repo: Path, env: dict, tmp_path: Path) -> None:
    """The `cd` is in a subshell, so the commit after it runs in the cwd, which holds a public term."""
    stage(repo, env, "notes.md", "AcmeCorp\n")

    reason = pretooluse(repo, env, "(cd nowhere && ls); git commit -m x")

    assert reason is not None
    assert "AcmeCorp (notes.md:1)" in reason


# -- pathspecs read relative to the directory the command runs in --------------------------------


@pytest.fixture
def mono(tmp_path: Path, env: dict) -> Path:
    """A public repo holding the tracked file app1/f.txt, whose working copy carries a term."""
    r = make_repo(tmp_path / "mono", env)
    (r / "app1").mkdir()
    (r / "app1" / "f.txt").write_text("clean\n")
    (r / "app1" / "g.txt").write_text("clean\n")
    git(env, r, "add", "app1")
    git(env, r, "commit", "-qm", "add app1")
    (r / "app1" / "f.txt").write_text("clean\nAcmeCorp\n")
    return r


@pytest.mark.parametrize(
    "command",
    [
        "git commit -m x -- f.txt",
        "git commit -m x f.txt",
        "git commit f.txt -m x",
        "git commit -m x -- ./f.txt",
        "git commit -a -m x",
    ],
)
def test_a_pathspec_is_read_from_the_cwd_not_the_repo_top(mono: Path, env: dict, command: str) -> None:
    """Catches the diff reading `f.txt` at the repo top, where no such file exists."""
    reason = pretooluse(mono / "app1", env, command)

    assert reason is not None
    assert "AcmeCorp (app1/f.txt:2)" in reason


def test_punctuation_inside_the_message_does_not_end_the_command(mono: Path, env: dict) -> None:
    """A `;` in the quoted message once cut the command short, so the pathspec after it was lost."""
    reason = pretooluse(mono / "app1", env, "git commit -m 'fix; tidy' -- f.txt")

    assert reason is not None
    assert "AcmeCorp (app1/f.txt:2)" in reason


def test_a_pathspec_after_dash_c_is_read_from_that_directory(mono: Path, env: dict) -> None:
    reason = pretooluse(mono, env, "git -C app1 commit -m x -- f.txt")

    assert reason is not None
    assert "AcmeCorp (app1/f.txt:2)" in reason


def test_a_pathspec_after_cd_is_read_from_that_directory(mono: Path, env: dict) -> None:
    reason = pretooluse(mono, env, "cd app1 && git commit -m x -- f.txt")

    assert reason is not None
    assert "AcmeCorp (app1/f.txt:2)" in reason


def test_a_commit_by_path_ignores_the_other_working_tree_changes(mono: Path, env: dict) -> None:
    """Only g.txt is committed, so the term in f.txt stays out of this commit."""
    assert pretooluse(mono / "app1", env, "git commit -m x -- g.txt") is None


# -- the cg MCP tools --------------------------------------------------------------------------
# rules/shell-discipline.md sends agents through these tools, so a commit made that way skips a guard
# that reads only the Bash tool.


def cg_run(repo: Path, env: dict, argv: list, cwd: str = "") -> str | None:
    payload = {"tool_name": "mcp__cg__cg_run", "tool_input": {"command": argv, "cwd": cwd}, "cwd": str(repo)}
    return run_hook(env, payload)


def cg_run_many(repo: Path, env: dict, argvs: list, cwd: str = "") -> str | None:
    payload = {"tool_name": "mcp__cg__cg_run_many", "tool_input": {"commands": argvs, "cwd": cwd}, "cwd": str(repo)}
    return run_hook(env, payload)


def test_cg_run_denies_a_staged_term(repo: Path, env: dict) -> None:
    stage(repo, env, "notes.md", "AcmeCorp\n")

    reason = cg_run(repo, env, ["git", "commit", "-m", "Add notes"])

    assert reason is not None
    assert "AcmeCorp (notes.md:1)" in reason


def test_cg_run_denies_a_term_in_the_message(repo: Path, env: dict) -> None:
    stage(repo, env, "notes.md", "nothing here\n")

    reason = cg_run(repo, env, ["git", "commit", "-m", "Port the Project Falcon wiki"])

    assert reason is not None
    assert "Project Falcon (commit command)" in reason


def test_cg_run_with_a_cwd_commits_there(repo: Path, env: dict, tmp_path: Path) -> None:
    """The tool's own cwd names the repo. The payload's cwd is elsewhere."""
    stage(repo, env, "notes.md", "AcmeCorp\n")

    reason = cg_run(tmp_path, env, ["git", "commit", "-m", "x"], cwd=str(repo))

    assert reason is not None
    assert "AcmeCorp (notes.md:1)" in reason


def test_cg_run_with_an_empty_cwd_uses_the_payload_cwd(repo: Path, env: dict) -> None:
    stage(repo, env, "notes.md", "AcmeCorp\n")

    assert cg_run(repo, env, ["git", "commit", "-m", "x"], cwd="") is not None


def test_cg_run_dash_c_names_the_repo(repo: Path, env: dict, tmp_path: Path) -> None:
    stage(repo, env, "notes.md", "AcmeCorp\n")

    assert cg_run(tmp_path, env, ["git", "-C", str(repo), "commit", "-m", "x"]) is not None


@pytest.mark.parametrize("shell", ["bash", "sh", "zsh"])
def test_cg_run_sees_a_commit_inside_a_shell_wrapper(workspace: Path, env: dict, shell: str) -> None:
    stage(workspace / "sub", env, "notes.md", "AcmeCorp\n")

    reason = cg_run(workspace, env, [shell, "-c", "cd sub && git commit -m x"])

    assert reason is not None
    assert "AcmeCorp (notes.md:1)" in reason


def test_cg_run_cwd_is_where_a_wrapper_starts(workspace: Path, env: dict, tmp_path: Path) -> None:
    stage(workspace / "sub", env, "notes.md", "AcmeCorp\n")

    assert cg_run(tmp_path, env, ["bash", "-c", "cd sub && git commit -m x"], cwd=str(workspace)) is not None


def test_cg_run_quotes_an_argument_with_spaces(tmp_path: Path, env: dict) -> None:
    """A directory with a space must reach git as one word."""
    spaced = make_repo(tmp_path / "my repo", env)
    stage(spaced, env, "notes.md", "AcmeCorp\n")

    assert cg_run(tmp_path, env, ["git", "-C", str(spaced), "commit", "-m", "x"]) is not None


def test_cg_run_many_checks_every_command(repo: Path, env: dict) -> None:
    stage(repo, env, "notes.md", "AcmeCorp\n")

    reason = cg_run_many(repo, env, [["git", "status"], ["git", "commit", "-m", "x"]])

    assert reason is not None
    assert "AcmeCorp (notes.md:1)" in reason


def test_cg_run_many_runs_commands_apart(workspace: Path, env: dict) -> None:
    """Each command starts at the shared cwd. A cd in one does not carry to the next."""
    stage(workspace / "sub", env, "notes.md", "AcmeCorp\n")

    assert cg_run_many(workspace, env, [["bash", "-c", "cd sub"], ["git", "commit", "-m", "x"]]) is None


@pytest.mark.parametrize("argv", [["git", "status"], ["git", "log", "--oneline"], ["grep", "AcmeCorp", "notes.md"], []])
def test_cg_run_ignores_other_commands(repo: Path, env: dict, argv: list) -> None:
    stage(repo, env, "notes.md", "AcmeCorp\n")

    assert cg_run(repo, env, argv) is None


def test_cg_run_with_no_command_is_ignored(repo: Path, env: dict) -> None:
    payload = {"tool_name": "mcp__cg__cg_run", "tool_input": {"command": None}, "cwd": str(repo)}

    assert run_hook(env, payload) is None


def test_hooks_json_wires_the_guard_to_every_tool_it_reads() -> None:
    """Catches a tool the hook reads but the plugin never sends it."""
    config = json.loads((HOOKS / "hooks.json").read_text())
    matchers = [
        group["matcher"]
        for group in config["hooks"]["PreToolUse"]
        if any(h["command"].endswith("/hooks/block-private-terms.sh") for h in group["hooks"])
    ]

    for tool in ("Bash", "mcp__cg__cg_run", "mcp__cg__cg_run_many"):
        assert any(re.fullmatch(m, tool) for m in matchers), f"{tool} is not matched by {matchers}"


# -- heredoc bodies and command substitutions ---------------------------------------------------
# A heredoc body is text for the command it feeds, not shell. The workspace is private and `sub` is
# public with a staged term. A commit that runs in the workspace is allowed. One that moves into
# `sub` is denied.


@pytest.mark.parametrize(
    ("opener", "indent"),
    [("<<EOF", ""), ("<<'EOF'", ""), ('<<"EOF"', ""), ("<<-EOF", "\t"), ("<<\\EOF", "")],
)
def test_a_cd_inside_a_heredoc_body_does_not_move_the_commit(
    workspace: Path, env: dict, opener: str, indent: str
) -> None:
    """Catches a tokenizer that reads the body as shell, so its `cd sub` moves the next commit."""
    stage(workspace / "sub", env, "notes.md", "AcmeCorp\n")

    command = f"cat > doc.md {opener}\n{indent}cd sub\n{indent}EOF\ngit commit -m x"

    assert pretooluse(workspace, env, command) is None


def test_each_of_two_heredocs_on_one_line_has_its_own_body(workspace: Path, env: dict) -> None:
    stage(workspace / "sub", env, "notes.md", "AcmeCorp\n")

    command = "cat <<A <<'B'\ncd sub\nA\ncd sub\nB\ngit commit -m x"

    assert pretooluse(workspace, env, command) is None


def test_an_apostrophe_in_a_heredoc_body_does_not_swallow_the_rest(workspace: Path, env: dict) -> None:
    """The quote once ran to the end, so the later commit was never placed in `sub`."""
    stage(workspace / "sub", env, "notes.md", "AcmeCorp\n")

    reason = pretooluse(workspace, env, "cd sub\ncat > doc.md <<EOF\nit's here\nEOF\ngit commit -m x")

    assert reason is not None
    assert "AcmeCorp (notes.md:1)" in reason


def test_a_heredoc_fed_to_a_shell_is_read_as_a_script(workspace: Path, env: dict) -> None:
    """Skipping every body would miss the commit in `bash <<EOF`, which does run."""
    stage(workspace / "sub", env, "notes.md", "AcmeCorp\n")

    reason = pretooluse(workspace, env, "bash <<'EOF'\ncd sub\ngit commit -m x\nEOF")

    assert reason is not None
    assert "AcmeCorp (notes.md:1)" in reason


@pytest.mark.parametrize(
    "command",
    [
        "echo $((1<<2))\ncd sub\ngit commit -m x",
        "echo $(( 1 << 2 ))\ncd sub\ngit commit -m x",
        "cat <<EOF\ncd sub\ngit commit -m x",
        "cat <<EOF\ncd sub\nEOF2\ngit commit -m x",
        "cat <<<EOF\ncd sub\ngit commit -m x\nEOF",
        "cat <<< 'a b'\ncd sub\ngit commit -m x",
    ],
)
def test_a_shift_or_an_unterminated_heredoc_does_not_hide_the_commands_after_it(
    workspace: Path, env: dict, command: str
) -> None:
    """A `<<` with no terminator line is not a heredoc to skip. Hiding the rest would fail open."""
    stage(workspace / "sub", env, "notes.md", "AcmeCorp\n")

    reason = pretooluse(workspace, env, command)

    assert reason is not None
    assert "AcmeCorp (notes.md:1)" in reason


@pytest.mark.parametrize(
    "command",
    [
        "echo `cd sub`; git commit -m x",
        "echo $(cd sub); git commit -m x",
        "x=`cd sub && pwd`; git commit -m x",
        "echo \"`cd sub`\" `cd sub`\ngit commit -m x",
    ],
)
def test_a_cd_inside_a_command_substitution_does_not_leak(workspace: Path, env: dict, command: str) -> None:
    """The substitution runs in a subshell, like `( ... )`. The commit stays in the workspace."""
    stage(workspace / "sub", env, "notes.md", "AcmeCorp\n")

    assert pretooluse(workspace, env, command) is None


def test_a_commit_inside_a_backtick_substitution_is_placed_there(workspace: Path, env: dict) -> None:
    stage(workspace / "sub", env, "notes.md", "AcmeCorp\n")

    reason = pretooluse(workspace, env, "echo `cd sub && git commit -m x`")

    assert reason is not None
    assert "AcmeCorp (notes.md:1)" in reason


# -- GIT_DIR, GIT_WORK_TREE, and the flags that set them ---------------------------------------


@pytest.mark.parametrize(
    "command",
    [
        "GIT_DIR={repo}/.git GIT_WORK_TREE={repo} git commit -m x",
        "GIT_DIR=repo/.git GIT_WORK_TREE=repo git commit -m x",
        "env GIT_DIR={repo}/.git GIT_WORK_TREE={repo} git commit -m x",
        "git --git-dir={repo}/.git --work-tree={repo} commit -m x",
        "git --git-dir {repo}/.git --work-tree {repo} commit -m x",
        "export GIT_DIR={repo}/.git GIT_WORK_TREE={repo}; git commit -m x",
        "GIT_DIR={repo}/.git; GIT_WORK_TREE={repo}; git commit -m x",
        "cd repo && GIT_DIR=.git git commit -m x",
        "cd repo && git --git-dir=.git commit -m x",
        "(export GIT_DIR={repo}/.git GIT_WORK_TREE={repo}; git commit -m x)",
    ],
)
def test_a_literal_git_dir_names_the_repo(repo: Path, env: dict, tmp_path: Path, command: str) -> None:
    """Catches a guard that checks the cwd, which holds no repo, when GIT_DIR points elsewhere."""
    stage(repo, env, "notes.md", "AcmeCorp\n")

    reason = pretooluse(tmp_path, env, command.format(repo=repo))

    assert reason is not None
    assert "AcmeCorp (notes.md:1)" in reason


def test_a_git_dir_to_a_private_repo_is_allowed(repo: Path, env: dict, tmp_path: Path) -> None:
    """The cwd repo is public and holds the term. GIT_DIR sends the commit to a private one."""
    stage(repo, env, "notes.md", "AcmeCorp\n")
    other = make_repo(tmp_path / "other", env)
    git(env, other, "config", "codingstandards.visibility", "private")

    command = f"GIT_DIR={other}/.git GIT_WORK_TREE={other} git commit -m x"

    assert pretooluse(repo, env, command) is None


@pytest.mark.parametrize(
    "command",
    [
        'GIT_DIR="$D" git commit -m x',
        "GIT_WORK_TREE=$(pwd)/x git commit -m x",
        "git --git-dir=$D commit -m x",
        'git --work-tree "$W" commit -m x',
        "export GIT_DIR=$D; git commit -m x",
        "cd repo && GIT_DIR=../$D git commit -m x",
        "GIT_DIR=sub*/.git git commit -m x",
    ],
)
def test_a_git_dir_it_cannot_resolve_is_denied(repo: Path, env: dict, tmp_path: Path, command: str) -> None:
    reason = pretooluse(tmp_path, env, command)

    assert reason is not None
    assert "git -C <path> commit" in reason


def test_a_git_dir_assignment_ends_with_its_subshell(repo: Path, env: dict, tmp_path: Path) -> None:
    """The export is inside `( )`. The commit after it runs in the cwd, which is no repo."""
    stage(repo, env, "notes.md", "AcmeCorp\n")

    command = f"(export GIT_DIR={repo}/.git GIT_WORK_TREE={repo}); git commit -m x"

    assert pretooluse(tmp_path, env, command) is None


def test_unset_ends_a_git_dir_assignment(repo: Path, env: dict, tmp_path: Path) -> None:
    command = f"export GIT_DIR=$D; unset GIT_DIR; git status; git -C {repo} commit -m x"

    assert pretooluse(tmp_path, env, command) is None


def test_cg_run_env_can_set_git_dir(repo: Path, env: dict, tmp_path: Path) -> None:
    """The cg tools take an `env` mapping, so GIT_DIR can arrive there and not in the argv."""
    stage(repo, env, "notes.md", "AcmeCorp\n")
    payload = {
        "tool_name": "mcp__cg__cg_run",
        "tool_input": {
            "command": ["git", "commit", "-m", "x"],
            "env": {"GIT_DIR": f"{repo}/.git", "GIT_WORK_TREE": str(repo)},
        },
        "cwd": str(tmp_path),
    }

    reason = run_hook(env, payload)

    assert reason is not None
    assert "AcmeCorp (notes.md:1)" in reason


# -- --pathspec-from-file ----------------------------------------------------------------------


@pytest.fixture
def listed(mono: Path) -> Path:
    """Mono's app1, with a list that names only f.txt. Its working copy has a term."""
    (mono / "app1" / "list.txt").write_text("f.txt\n")
    return mono / "app1"


@pytest.mark.parametrize(
    "option",
    ["--pathspec-from-file=list.txt", "--pathspec-from-file list.txt", "--pathspec-from-file=./list.txt"],
)
def test_a_pathspec_file_names_what_the_commit_takes(listed: Path, env: dict, option: str) -> None:
    """Catches a guard that ignores the list, so no path is read from the working tree."""
    reason = pretooluse(listed, env, f"git commit -m x {option}")

    assert reason is not None
    assert "AcmeCorp (app1/f.txt:2)" in reason


def test_a_pathspec_file_that_names_a_clean_path_is_allowed(listed: Path, env: dict) -> None:
    (listed / "list.txt").write_text("g.txt\n")

    assert pretooluse(listed, env, "git commit -m x --pathspec-from-file=list.txt") is None


def test_a_nul_separated_pathspec_file_is_read(listed: Path, env: dict) -> None:
    (listed / "list.txt").write_bytes(b"g.txt\0f.txt\0")

    reason = pretooluse(listed, env, "git commit -m x --pathspec-from-file=list.txt --pathspec-file-nul")

    assert reason is not None
    assert "AcmeCorp (app1/f.txt:2)" in reason


def test_a_pathspec_file_after_dash_c_is_read_from_that_directory(mono: Path, listed: Path, env: dict) -> None:
    reason = pretooluse(mono, env, "git -C app1 commit -m x --pathspec-from-file=list.txt")

    assert reason is not None
    assert "AcmeCorp (app1/f.txt:2)" in reason


@pytest.mark.parametrize(
    "option",
    [
        "--pathspec-from-file=-",
        '--pathspec-from-file="$LIST"',
        "--pathspec-from-file=$(mktemp)",
        "--pathspec-from-file=missing.txt",
        "--pathspec-from-file=../../outside.txt",
        "--pathspec-from-file=/etc/hosts",
        "--pathspec-from-file=quoted.txt",
        "--pathspec-from-file=/etc/*",
    ],
)
def test_a_pathspec_file_it_cannot_read_is_denied(listed: Path, env: dict, tmp_path: Path, option: str) -> None:
    """A file outside the repo, a missing one, stdin, and a quoted entry are not plain paths."""
    (tmp_path / "outside.txt").write_text("f.txt\n")
    (listed / "quoted.txt").write_text('"f.txt"\n')

    reason = pretooluse(listed, env, f"git commit -m x {option}")

    assert reason is not None
    assert "--pathspec-from-file" in reason
    assert "path" in reason


def test_a_pathspec_file_it_cannot_read_is_allowed_in_a_private_repo(listed: Path, env: dict) -> None:
    git(env, listed, "config", "codingstandards.visibility", "private")

    assert pretooluse(listed, env, "git commit -m x --pathspec-from-file=missing.txt") is None


# -- repo programs must not run -----------------------------------------------------------------
# Hooks run outside the sandbox, in a directory the command names. A repo can configure programs
# that git runs while it reads a diff. The hook must read the diff without running any of them.

PLANTS = {
    "textconv": ('cat "$1"', {"diff.x.textconv": "{script}"}, "* diff=x"),
    "external diff": ("exit 0", {"diff.external": "{script}"}, None),
    "fsmonitor": ("exit 1", {"core.fsmonitor": "{script}"}, None),
    "clean filter": ("cat", {"filter.x.clean": "{script}"}, "* filter=x"),
    "required clean filter": (
        "cat",
        {"filter.x.clean": "{script}", "filter.x.required": "true"},
        "* filter=x",
    ),
    "process filter": ("exit 1", {"filter.x.process": "{script}"}, "* filter=x"),
    "filter named with a dot": ("cat", {"filter.a.b.clean": "{script}"}, "* filter=a.b"),
}


def plant(repo: Path, env: dict, tmp_path: Path, kind: str) -> Path:
    """Make git run a script when it uses `kind`. Return the file the script writes."""
    body, settings, attributes = PLANTS[kind]
    marker = tmp_path / "ran.marker"
    script = tmp_path / "planted.sh"
    script.write_text(f'#!/bin/sh\necho ran >> "{marker}"\n{body}\n')
    script.chmod(0o755)
    for key, value in settings.items():
        git(env, repo, "config", key, value.format(script=script))
    if attributes:
        (repo / ".gitattributes").write_text(attributes + "\n")
    marker.unlink(missing_ok=True)
    return marker


@pytest.mark.parametrize("kind", list(PLANTS))
def test_a_programs_the_repo_configures_never_runs(repo: Path, env: dict, tmp_path: Path, kind: str) -> None:
    """Catches a diff that runs a textconv, external diff, fsmonitor, or filter the repo names.

    The commit takes the index and the working tree, so both diffs run. A term in each proves the
    hook read each diff, and that a program it turned off did not make git fail. The marker proves
    it did not run the program.
    """
    stage(repo, env, "notes.md", "AcmeCorp\n")
    (repo / "README.md").write_text("hello\nAcmeCorp in the working tree\n")
    marker = plant(repo, env, tmp_path, kind)

    reason = pretooluse(repo, env, "git commit -a -m x")

    assert reason is not None
    assert "AcmeCorp (notes.md:1)" in reason
    assert "AcmeCorp (README.md:2)" in reason
    assert not marker.exists(), "the repo's program ran"


@pytest.fixture
def old_git(tmp_path: Path, env: dict) -> dict:
    """An env whose `git` ignores GIT_CONFIG_COUNT, as a git older than 2.31 does."""
    real = shutil.which("git", path=env["PATH"])
    bin_dir = tmp_path / "oldgit"
    bin_dir.mkdir()
    wrapper = bin_dir / "git"
    wrapper.write_text(f'#!/bin/sh\nunset GIT_CONFIG_COUNT\nexec "{real}" "$@"\n')
    wrapper.chmod(0o755)
    return {**env, "PATH": f"{bin_dir}:{env['PATH']}"}


@pytest.mark.parametrize("kind", ["clean filter", "required clean filter", "process filter"])
def test_filters_are_turned_off_whatever_the_git_version(repo: Path, env: dict, old_git: dict, tmp_path: Path, kind: str) -> None:
    """Catches protection that rests on an environment variable an older git ignores."""
    stage(repo, env, "notes.md", "AcmeCorp\n")
    (repo / "README.md").write_text("hello\nAcmeCorp in the working tree\n")
    marker = plant(repo, env, tmp_path, kind)

    reason = pretooluse(repo, old_git, "git commit -a -m x")

    assert reason is not None
    assert "AcmeCorp (README.md:2)" in reason
    assert not marker.exists(), "the repo's program ran"


def test_a_filter_it_cannot_turn_off_denies_the_commit(repo: Path, env: dict, tmp_path: Path) -> None:
    """A driver named `a=b` cannot be spelled in `git -c`, so the hook cannot silence it. It must
    refuse to read the diff, and say why, and not read it with the driver on."""
    stage(repo, env, "notes.md", "AcmeCorp\n")
    (repo / "README.md").write_text("hello\nAcmeCorp in the working tree\n")
    marker = tmp_path / "ran.marker"
    script = tmp_path / "planted.sh"
    script.write_text(f'#!/bin/sh\necho ran >> "{marker}"\ncat\n')
    script.chmod(0o755)
    with open(repo / ".git" / "config", "a") as config:
        config.write(f'[filter "a=b"]\n\tclean = {script}\n')
    (repo / ".gitattributes").write_text("* filter=a=b\n")

    reason = pretooluse(repo, env, "git commit -a -m x")

    assert reason is not None
    assert "filter driver" in reason
    assert "a=b" in reason
    assert not marker.exists()


def test_a_diff_that_is_not_utf8_is_still_read(repo: Path, env: dict) -> None:
    """A strict decode of git's output raised, so the hook exited non-zero and let the commit by."""
    (repo / "notes.md").write_bytes(b"caf\xe9\nAcmeCorp\n")
    subprocess.run(["git", "-C", str(repo), "add", "notes.md"], check=True, env=env)

    reason = pretooluse(repo, env, "git commit -m x")

    assert reason is not None
    assert "AcmeCorp (notes.md:2)" in reason


def test_a_planted_program_does_not_run_for_a_pre_commit_check(repo: Path, env: dict, tmp_path: Path) -> None:
    """The git pre-commit hook reads the same diff, so it gets the same protection."""
    stage(repo, env, "notes.md", "AcmeCorp\n")
    marker = tmp_path / "ran.marker"
    script = tmp_path / "planted.sh"
    script.write_text(f'#!/bin/sh\necho ran >> "{marker}"\ncat "$1"\n')
    script.chmod(0o755)
    git(env, repo, "config", "diff.x.textconv", str(script))
    (repo / ".gitattributes").write_text("* diff=x\n")

    result = subprocess.run([HOOKS / "private-terms.py", "pre-commit"], cwd=repo, capture_output=True, text=True, env=env)

    assert result.returncode == 1
    assert "AcmeCorp (notes.md:1)" in result.stderr
    assert not marker.exists()


# -- the shell wrapper's prefilter --------------------------------------------------------------


@pytest.mark.parametrize(
    "command",
    [
        "g''it commit -m x",
        "git com''mit -m x",
        'g"i"t c"omm"it -m x',
        "g\\it commit -m x",
        "git comm\\it -m x",
        "\"git\" \"commit\" -m x",
        "git \\\ncommit -m x",
        "g\\\nit commit -m x",
    ],
)
def test_a_commit_spelled_with_quotes_reaches_the_tokenizer(repo: Path, env: dict, command: str) -> None:
    """The wrapper once let only the literal text `git` then `commit` through. The tokenizer joins
    quoted pieces, so a split spelling slipped past it."""
    stage(repo, env, "notes.md", "AcmeCorp\n")

    reason = pretooluse(repo, env, command)

    assert reason is not None
    assert "AcmeCorp (notes.md:1)" in reason


# -- what a commit takes, by the options it is given ---------------------------------------------
# `-p`, `--patch`, and `--interactive` commit working-tree hunks that nothing has staged. An option the
# hook cannot place may carry anything. Both read the working tree, which is the superset.


@pytest.fixture
def dirty(repo: Path, env: dict) -> Path:
    """A public repo with a term in a tracked file's working copy and in an untracked file. Nothing is staged."""
    (repo / "README.md").write_text("hello\nAcmeCorp in the working tree\n")
    (repo / "fresh.md").write_text("AcmeCorp in a new file\n")
    return repo


@pytest.mark.parametrize(
    "command",
    [
        "git commit -p",
        "git commit --patch -m x",
        "git commit --pat -m x",
        "git commit --p",
        "git commit -vp -m x",
        "git commit -pm x",
        "git commit -p -- README.md",
        "git commit -m x --patch",
    ],
)
def test_a_commit_that_picks_hunks_reads_the_working_tree(dirty: Path, env: dict, command: str) -> None:
    """Catches a guard that diffs only the index, so `-p` commits a hunk it never read."""
    reason = pretooluse(dirty, env, command)

    assert reason is not None
    assert "AcmeCorp (README.md:2)" in reason


@pytest.mark.parametrize(
    "command", ["git commit --interactive", "git commit --inter -m x", "git commit -m x --interactive"]
)
def test_a_commit_that_adds_files_reads_the_untracked_files_too(dirty: Path, env: dict, command: str) -> None:
    """`git add -i` can add an untracked file, so `--interactive` may commit one."""
    reason = pretooluse(dirty, env, command)

    assert reason is not None
    assert "AcmeCorp (README.md:2)" in reason
    assert "AcmeCorp (fresh.md:1)" in reason


def test_picking_hunks_does_not_add_an_untracked_file(repo: Path, env: dict) -> None:
    """`git add -p` reads tracked files, so an untracked term is not part of the commit."""
    (repo / "fresh.md").write_text("AcmeCorp in a new file\n")

    assert pretooluse(repo, env, "git commit -p -m x") is None


@pytest.mark.parametrize(
    "command",
    [
        "git commit --made-up-option -m x",
        "git commit --no-such=1 -m x",
        "git commit -W -m x",
        "git commit --a -m x",
        "git commit --f -m x",
        "git commit --ver -m x",
    ],
)
def test_an_option_it_does_not_know_reads_everything(dirty: Path, env: dict, command: str) -> None:
    """An option the hook cannot place may add any file. A prefix that fits two options is no option
    at all, and git refuses it. Reading everything is safe for both."""
    reason = pretooluse(dirty, env, command)

    assert reason is not None
    assert "AcmeCorp (README.md:2)" in reason
    assert "AcmeCorp (fresh.md:1)" in reason


@pytest.mark.parametrize(
    "command",
    [
        "git commit -n -s -q -v -e --no-edit --no-verify --allow-empty --amend -m x",
        "git commit -S -m x",
        "git commit -SKEYID -m x",
        "git commit --gpg-sign=KEY -u -m x",
        "git commit --untracked-files=no -m x",
        "git commit --author='A <a@x.y>' --date=now --cleanup=strip --trailer 'a: b' -m x",
        "git commit --signoff --reset-author --status --no-status --no-post-rewrite -m x",
        "git commit --dry-run --short --branch --porcelain -z -m x",
        "git commit -C HEAD -n",
        "git commit -c HEAD --reset-author",
        "git commit --fixup HEAD",
        "git commit --squash=HEAD",
        "git commit --reuse-message HEAD",
        "git commit --verb --no-verb -m x",
        "git commit --verif -m x",
        "git commit -mabc",
        "git commit -ma",
        "git commit -m a -m b",
        "git commit --mess=abc",
    ],
)
def test_the_options_it_knows_do_not_widen_the_read(dirty: Path, env: dict, command: str) -> None:
    """Nothing here takes more than the index. A guard that widens on every option cries wolf, and
    `-ma` is the message `a`, not `-m` and `-a`."""
    assert pretooluse(dirty, env, command) is None


@pytest.mark.parametrize("command", ["git commit -am x", "git commit -qam x", "git commit -a", "git commit --all -m x"])
def test_all_is_found_in_a_cluster_of_short_options(dirty: Path, env: dict, command: str) -> None:
    reason = pretooluse(dirty, env, command)

    assert reason is not None
    assert "AcmeCorp (README.md:2)" in reason


@pytest.fixture
def listed_app(mono: Path) -> Path:
    (mono / "app1" / "list.txt").write_text("f.txt\n")
    (mono / "app1" / "nul.txt").write_bytes(b"g.txt\0f.txt\0")
    return mono / "app1"


@pytest.mark.parametrize(
    "option",
    [
        "--pathspec-from=list.txt",
        "--pathspec-from list.txt",
        "--pathspec-from-f=list.txt",
        "--pathspec-from-file list.txt",
        "--pathspec-from-file=nul.txt --pathspec-file-n",
        "--pathspec-from=nul.txt --pathspec-file-nul",
    ],
)
def test_an_abbreviated_option_is_read_as_git_reads_it(listed_app: Path, env: dict, option: str) -> None:
    """Git takes any prefix of a long option that fits one. Catches an exact-name parse that reads
    `--pathspec-from=list.txt` as an unknown flag, so the list is never read."""
    reason = pretooluse(listed_app, env, f"git commit -m x {option}")

    assert reason is not None
    assert "AcmeCorp (app1/f.txt:2)" in reason


@pytest.mark.parametrize("option", ["--pathspec-from=-", "--pathspec-from=missing.txt", '--pathspec-from="$L"'])
def test_an_abbreviated_pathspec_file_it_cannot_read_is_denied(listed_app: Path, env: dict, option: str) -> None:
    reason = pretooluse(listed_app, env, f"git commit -m x {option}")

    assert reason is not None
    assert "--pathspec-from-file" in reason


@pytest.mark.parametrize(
    "command",
    [
        "git --namespace ns commit -m x",
        "git --config-env core.x=VAR commit -m x",
        "git --attr-source HEAD commit -m x",
        "git --no-pager -P --literal-pathspecs commit -m x",
        "git -c core.x=1 --exec-path=/x commit -m x",
        "git --git-dir=.git --namespace=ns commit -m x",
    ],
)
def test_a_global_option_that_takes_a_value_does_not_hide_the_subcommand(repo: Path, env: dict, command: str) -> None:
    """Catches a skip of one word per option, which reads the value after `--namespace` as the
    subcommand and never sees the commit."""
    stage(repo, env, "notes.md", "AcmeCorp\n")

    reason = pretooluse(repo, env, command)

    assert reason is not None
    assert "AcmeCorp (notes.md:1)" in reason


def test_a_commit_with_all_in_a_new_repo_reads_the_working_tree(tmp_path: Path, env: dict) -> None:
    """With no commit yet, `git diff HEAD` fails. The hook then read nothing, and `-a` took the
    working tree of every file the index knows."""
    fresh = tmp_path / "fresh"
    fresh.mkdir()
    git(env, fresh, "init", "-q", "-b", "main")
    git(env, fresh, "remote", "add", "origin", "git@github.com:someone/fresh.git")
    (fresh / "f.txt").write_text("clean\n")
    git(env, fresh, "add", "f.txt")
    (fresh / "f.txt").write_text("clean\nAcmeCorp\n")

    reason = pretooluse(fresh, env, "git commit -a -m x")

    assert reason is not None
    assert "AcmeCorp (f.txt:2)" in reason


# -- an index other than the default -------------------------------------------------------------


def alt_index(repo: Path, env: dict, where: Path, files: dict) -> Path:
    """Make an index at `where` that holds `files` on top of HEAD. The default index stays clean."""
    alt_env = {**env, "GIT_INDEX_FILE": str(where)}
    subprocess.run(["git", "-C", str(repo), "read-tree", "HEAD"], check=True, env=alt_env)
    for name, text in files.items():
        (repo / name).write_text(text)
        subprocess.run(["git", "-C", str(repo), "add", name], check=True, env=alt_env)
    return where


@pytest.mark.parametrize(
    "command",
    [
        "GIT_INDEX_FILE={idx} git commit -m x",
        "export GIT_INDEX_FILE={idx}; git commit -m x",
        "GIT_INDEX_FILE={idx}; git commit -m x",
        "env GIT_INDEX_FILE={idx} git commit -m x",
        "(export GIT_INDEX_FILE={idx}; git commit -m x)",
        "bash -c 'GIT_INDEX_FILE={idx} git commit -m x'",
        "GIT_INDEX_FILE={idx} sudo git commit -m x",
    ],
)
def test_a_commit_from_another_index_is_read_from_that_index(
    repo: Path, env: dict, tmp_path: Path, command: str
) -> None:
    """Catches a guard that diffs the default index. It holds nothing, and the commit carries the other."""
    idx = alt_index(repo, env, tmp_path / "alt.idx", {"notes.md": "AcmeCorp\n"})

    reason = pretooluse(repo, env, command.format(idx=idx))

    assert reason is not None
    assert "AcmeCorp (notes.md:1)" in reason


def test_cg_env_can_name_another_index(repo: Path, env: dict, tmp_path: Path) -> None:
    idx = alt_index(repo, env, tmp_path / "alt.idx", {"notes.md": "AcmeCorp\n"})
    payload = {
        "tool_name": "mcp__cg__cg_run",
        "tool_input": {"command": ["git", "commit", "-m", "x"], "env": {"GIT_INDEX_FILE": str(idx)}},
        "cwd": str(repo),
    }

    reason = run_hook(env, payload)

    assert reason is not None
    assert "AcmeCorp (notes.md:1)" in reason


def test_a_relative_index_path_is_read_from_the_repo_top(repo: Path, env: dict) -> None:
    """Git moves to the top of the work tree before it opens the index. The command runs in `sub`."""
    (repo / "sub").mkdir()
    alt_index(repo, env, repo / "alt.idx", {"notes.md": "AcmeCorp\n"})

    reason = pretooluse(repo / "sub", env, "GIT_INDEX_FILE=alt.idx git commit -m x")

    assert reason is not None
    assert "AcmeCorp (notes.md:1)" in reason


@pytest.mark.parametrize(
    "command",
    [
        'GIT_INDEX_FILE="$IDX" git commit -m x',
        "GIT_INDEX_FILE=$(mktemp) git commit -m x",
        "GIT_INDEX_FILE=`mktemp` git commit -m x",
        "export GIT_INDEX_FILE=$IDX; git commit -m x",
        "GIT_INDEX_FILE={tmp}/idx-* git commit -m x",
        "GIT_INDEX_FILE={tmp}/missing.idx git commit -m x",
        "GIT_INDEX_FILE={tmp} git commit -m x",
    ],
)
def test_an_index_it_cannot_read_is_denied(repo: Path, env: dict, tmp_path: Path, command: str) -> None:
    """The hook cannot tell what the commit carries, so it denies the commit."""
    reason = pretooluse(repo, env, command.format(tmp=tmp_path))

    assert reason is not None
    assert "GIT_INDEX_FILE" in reason


def test_an_index_it_cannot_read_is_allowed_in_a_private_repo(repo: Path, env: dict) -> None:
    git(env, repo, "config", "codingstandards.visibility", "private")

    assert pretooluse(repo, env, 'GIT_INDEX_FILE="$IDX" git commit -m x') is None


@pytest.mark.parametrize(
    "command",
    [
        'GIT_INDEX_FILE="$IDX" git status',
        'export GIT_INDEX_FILE="$IDX"; unset GIT_INDEX_FILE; git commit -m x',
        '(export GIT_INDEX_FILE="$IDX"); git commit -m x',
    ],
)
def test_an_index_that_does_not_reach_the_commit_is_allowed(repo: Path, env: dict, command: str) -> None:
    assert pretooluse(repo, env, command) is None


# -- the message in a file ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "option",
    [
        "-F msg.txt",
        "-Fmsg.txt",
        "-sF msg.txt",
        "--file msg.txt",
        "--file=msg.txt",
        "--fil=msg.txt",
        "-t msg.txt",
        "--template=msg.txt",
        "--templ msg.txt",
    ],
)
def test_a_term_in_a_message_file_is_denied(repo: Path, env: dict, option: str) -> None:
    """Catches a guard that scans only the command's text, which holds the file's name and not its text."""
    stage(repo, env, "notes.md", "nothing here\n")
    (repo / "msg.txt").write_text("Port the Project Falcon wiki\n")

    reason = pretooluse(repo, env, f"git commit {option}")

    assert reason is not None
    assert "Project Falcon (message file msg.txt)" in reason


def test_a_message_file_is_read_from_the_directory_the_commit_runs_in(workspace: Path, env: dict) -> None:
    (workspace / "sub" / "msg.txt").write_text("Port the Project Falcon wiki\n")

    for command in ("cd sub && git commit -F msg.txt", "git -C sub commit -F msg.txt"):
        reason = pretooluse(workspace, env, command)

        assert reason is not None, command
        assert "Project Falcon (message file msg.txt)" in reason


def test_a_message_file_outside_the_repo_is_read(repo: Path, env: dict, tmp_path: Path) -> None:
    message = tmp_path / "msg.txt"
    message.write_text("Port the Project Falcon wiki\n")

    reason = pretooluse(repo, env, f"git commit -F {message}")

    assert reason is not None
    assert f"Project Falcon (message file {message})" in reason


def test_a_clean_message_file_is_allowed(repo: Path, env: dict) -> None:
    (repo / "msg.txt").write_text("Port the notes\n")

    assert pretooluse(repo, env, "git commit -F msg.txt --allow-empty") is None


@pytest.mark.parametrize(
    "command",
    [
        "git commit -F - <<'EOF'\nPort the notes\nEOF",
        "echo 'Port the notes' | git commit -F -",
        "git commit -F /dev/stdin <<< 'Port the notes'",
        "git commit --file=- <<< 'Port the notes'",
    ],
)
def test_a_message_from_stdin_reads_no_file(repo: Path, env: dict, command: str) -> None:
    """The message is in the command's text, which is scanned, or in a pipe the hook cannot see."""
    assert pretooluse(repo, env, command) is None


def test_a_term_in_a_stdin_message_is_denied_as_command_text(repo: Path, env: dict) -> None:
    reason = pretooluse(repo, env, "git commit -F - <<'EOF'\nPort the Project Falcon wiki\nEOF")

    assert reason is not None
    assert "Project Falcon (commit command)" in reason


@pytest.mark.parametrize(
    "option",
    [
        "-F missing.txt",
        '-F "$MSG"',
        "-F $(mktemp)",
        "-F ~nosuchuser/msg",
        "-F .",
        "-F msg-*.txt",
        "--template=missing.txt",
        "-t .",
    ],
)
def test_a_message_file_it_cannot_read_is_denied(repo: Path, env: dict, option: str) -> None:
    reason = pretooluse(repo, env, f"git commit {option}")

    assert reason is not None
    assert "message file" in reason
    assert "rules/disclosure.md" in reason


def test_a_message_file_it_cannot_read_is_allowed_in_a_private_repo(repo: Path, env: dict) -> None:
    git(env, repo, "config", "codingstandards.visibility", "private")

    assert pretooluse(repo, env, "git commit -F missing.txt") is None


# -- file names ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    ["acmecorp-notes.md", "docs/AcmeCorp/notes.md", "notes-for-acmecorp", "acmecorp_notes.md", "AcmeCorp.md"],
)
def test_a_new_file_whose_name_holds_a_term_is_denied(repo: Path, env: dict, name: str) -> None:
    """Catches a guard that reads only added lines. A path is never an added line."""
    (repo / name).parent.mkdir(parents=True, exist_ok=True)
    stage(repo, env, name, "nothing here\n")

    reason = pretooluse(repo, env, "git commit -m x")

    assert reason is not None
    assert f"(file name {name})" in reason
    assert "public repo" in reason


@pytest.mark.parametrize("content", [b"", b"\x00\x01\x02binary"])
def test_an_empty_or_binary_file_is_still_named(repo: Path, env: dict, content: bytes) -> None:
    """These have no added line at all, so only the name can carry a term."""
    (repo / "acmecorp.bin").write_bytes(content)
    subprocess.run(["git", "-C", str(repo), "add", "acmecorp.bin"], check=True, env=env)

    reason = pretooluse(repo, env, "git commit -m x")

    assert reason is not None
    assert "(file name acmecorp.bin)" in reason


def test_a_rename_is_read_on_both_sides(repo: Path, env: dict) -> None:
    (repo / "acmecorp-old.md").write_text("some notes that are long enough to match as a rename\n" * 5)
    git(env, repo, "add", "acmecorp-old.md")
    git(env, repo, "commit", "-qm", "seed")

    git(env, repo, "mv", "acmecorp-old.md", "notes.md")
    reason = pretooluse(repo, env, "git commit -m x")

    assert reason is not None
    assert "(file name acmecorp-old.md)" in reason

    git(env, repo, "reset", "-q", "--hard")
    git(env, repo, "mv", "acmecorp-old.md", "acmecorp-new.md")
    reason = pretooluse(repo, env, "git commit -m x")

    assert reason is not None
    assert "(file name acmecorp-new.md)" in reason
    assert "(file name acmecorp-old.md)" in reason


def test_a_deleted_file_is_read_by_name(repo: Path, env: dict) -> None:
    (repo / "acmecorp-old.md").write_text("notes\n")
    git(env, repo, "add", "acmecorp-old.md")
    git(env, repo, "commit", "-qm", "seed")
    git(env, repo, "rm", "-q", "acmecorp-old.md")

    reason = pretooluse(repo, env, "git commit -m x")

    assert reason is not None
    assert "(file name acmecorp-old.md)" in reason


def test_a_term_inside_a_longer_word_in_a_name_is_allowed(repo: Path, env: dict) -> None:
    stage(repo, env, "acmecorporation.md", "notes\n")

    assert pretooluse(repo, env, "git commit -m x") is None


def test_the_name_of_an_untracked_file_is_read_when_the_commit_may_add_it(repo: Path, env: dict) -> None:
    (repo / "acmecorp-notes.md").write_text("nothing\n")

    reason = pretooluse(repo, env, "git commit --interactive")

    assert reason is not None
    assert "(file name acmecorp-notes.md)" in reason


def test_an_untracked_file_that_is_too_large_to_read_is_denied(repo: Path, env: dict) -> None:
    with open(repo / "big.bin", "wb") as big:
        big.truncate(40 << 20)

    reason = pretooluse(repo, env, "git commit --interactive")

    assert reason is not None
    assert "big.bin" in reason


# -- a directory a wrapper changes --------------------------------------------------------------


@pytest.mark.parametrize(
    "command",
    [
        "env -C sub git commit -m x",
        "env -Csub git commit -m x",
        "env --chdir=sub git commit -m x",
        "env --chdir sub git commit -m x",
        "env --chd sub git commit -m x",
        "env -i -C sub git commit -m x",
        "env -C ./sub git -C . commit -m x",
        "env -C sub bash -c 'git commit -m x'",
        "env -C sub FOO=1 git commit -m x",
        "sudo -D sub git commit -m x",
        "sudo -Dsub git commit -m x",
        "sudo -nD sub git commit -m x",
        "sudo --chdir=sub git commit -m x",
        "sudo --chdir sub git commit -m x",
        "sudo -u root -D sub git commit -m x",
        "sudo env -C sub git commit -m x",
        "sudo -D sub env -C . git commit -m x",
        "cd sub && env -C . git commit -m x",
    ],
)
def test_a_wrapper_that_changes_the_directory_moves_the_commit(workspace: Path, env: dict, command: str) -> None:
    """The workspace is private and `sub` is public. Catches a guard that checks the directory the
    wrapper started in, when `env -C` and `sudo -D` run the commit in `sub`."""
    stage(workspace / "sub", env, "notes.md", "AcmeCorp\n")

    reason = pretooluse(workspace, env, command)

    assert reason is not None
    assert "AcmeCorp (notes.md:1)" in reason


@pytest.mark.parametrize(
    "command",
    [
        'env -C "$D" git commit -m x',
        'env --chdir="$D" git commit -m x',
        "env --chdir=$(pwd)/sub git commit -m x",
        'sudo -D "$D" git commit -m x',
        "sudo --chdir=sub* git commit -m x",
    ],
)
def test_a_wrapper_directory_it_cannot_follow_is_denied_with_how_to_rerun(
    workspace: Path, env: dict, command: str
) -> None:
    reason = pretooluse(workspace, env, command)

    assert reason is not None
    assert "git -C <path> commit" in reason


@pytest.mark.parametrize(
    "command",
    [
        "env FOO=1 git commit -m x",
        "sudo -u root git commit -m x",
        "env -u FOO git commit -m x",
        "sudo -n git commit -m x",
        "env -C sub ls && git commit -m x",
    ],
)
def test_a_wrapper_that_does_not_change_the_directory_leaves_the_commit_where_it_is(
    workspace: Path, env: dict, command: str
) -> None:
    """The commit runs in the private workspace, so the term in `sub` is not part of it. The last
    command's `env -C` belongs to `ls`."""
    stage(workspace / "sub", env, "notes.md", "AcmeCorp\n")

    assert pretooluse(workspace, env, command) is None


@pytest.mark.parametrize(
    "command",
    [
        "export GIT_DIR={priv}/.git GIT_WORK_TREE={priv}; env -u GIT_DIR -u GIT_WORK_TREE git commit -m x",
        "export GIT_DIR={priv}/.git GIT_WORK_TREE={priv}; env -i git commit -m x",
        "export GIT_DIR={priv}/.git GIT_WORK_TREE={priv}; env --unset=GIT_DIR --unset=GIT_WORK_TREE git commit -m x",
        "export GIT_DIR={priv}/.git GIT_WORK_TREE={priv}; env - git commit -m x",
    ],
)
def test_env_can_clear_the_variables_that_moved_a_commit(repo: Path, env: dict, tmp_path: Path, command: str) -> None:
    """The variables point at a private repo, and `env` clears them. The commit lands in the cwd repo."""
    private = make_repo(tmp_path / "priv", env)
    git(env, private, "config", "codingstandards.visibility", "private")
    stage(repo, env, "notes.md", "AcmeCorp\n")

    reason = pretooluse(repo, env, command.format(priv=private))

    assert reason is not None
    assert "AcmeCorp (notes.md:1)" in reason


@pytest.mark.parametrize(
    "command",
    [
        "git -C {tmp} --git-dir={repo}/.git --work-tree={repo} commit -m x",
        "git --git-dir={repo}/.git --work-tree={repo} -C {tmp} commit -m x",
        "cd {repo} && git --git-dir=.git -C . commit -m x",
        "git -C {repo} --git-dir=.git commit -m x",
        "git --git-dir=.git -C {repo} commit -m x",
        "git -C {repo}/.. -C {name} commit -m x",
        "git -C {tmp} -C {repo} --git-dir=.git commit -m x",
    ],
)
def test_git_dir_and_dash_c_together_name_the_repo(repo: Path, env: dict, tmp_path: Path, command: str) -> None:
    """A relative `--git-dir` is read from the directory `-C` leaves git in, however the two are ordered."""
    stage(repo, env, "notes.md", "AcmeCorp\n")

    reason = pretooluse(tmp_path, env, command.format(repo=repo, tmp=tmp_path, name=repo.name))

    assert reason is not None
    assert "AcmeCorp (notes.md:1)" in reason


# -- the directory a cg call runs in ------------------------------------------------------------


def cg_payload(payload_cwd: Path, given_cwd: str | None) -> dict:
    """A cg_run of `git commit`, sent from `payload_cwd`. `given_cwd` None leaves the field out."""
    tool_input: dict = {"command": ["git", "commit", "-m", "x"]}
    if given_cwd is not None:
        tool_input["cwd"] = given_cwd
    return {"tool_name": "mcp__cg__cg_run", "tool_input": tool_input, "cwd": str(payload_cwd)}


def test_a_cg_call_with_no_cwd_is_checked_in_the_server_directory(repo: Path, env: dict, tmp_path: Path) -> None:
    """The payload's cwd follows the Bash tool's `cd`. The cg server runs where it started. A call with
    no cwd runs in the second, so a guard that reads only the first checks the wrong repo."""
    elsewhere = make_repo(tmp_path / "elsewhere", env)
    git(env, elsewhere, "config", "codingstandards.visibility", "private")
    stage(repo, env, "notes.md", "AcmeCorp\n")
    payload = cg_payload(elsewhere, "")

    reason = run_hook({**env, "CLAUDE_PROJECT_DIR": str(repo)}, payload)

    assert reason is not None
    assert "AcmeCorp (notes.md:1)" in reason


def test_a_cg_call_with_no_cwd_is_still_checked_in_the_payload_directory(repo: Path, env: dict, tmp_path: Path) -> None:
    elsewhere = make_repo(tmp_path / "elsewhere", env)
    git(env, elsewhere, "config", "codingstandards.visibility", "private")
    stage(repo, env, "notes.md", "AcmeCorp\n")
    payload = cg_payload(repo, None)

    reason = run_hook({**env, "CLAUDE_PROJECT_DIR": str(elsewhere)}, payload)

    assert reason is not None
    assert "AcmeCorp (notes.md:1)" in reason


def test_a_relative_cg_cwd_is_checked_from_the_server_directory(workspace: Path, env: dict, tmp_path: Path) -> None:
    stage(workspace / "sub", env, "notes.md", "AcmeCorp\n")
    payload = cg_payload(tmp_path, "sub")

    reason = run_hook({**env, "CLAUDE_PROJECT_DIR": str(workspace)}, payload)

    assert reason is not None
    assert "AcmeCorp (notes.md:1)" in reason


def test_a_cg_call_with_an_absolute_cwd_is_checked_only_there(repo: Path, env: dict, tmp_path: Path) -> None:
    private = make_repo(tmp_path / "priv", env)
    git(env, private, "config", "codingstandards.visibility", "private")
    stage(repo, env, "notes.md", "AcmeCorp\n")
    payload = cg_payload(repo, str(private))

    assert run_hook({**env, "CLAUDE_PROJECT_DIR": str(repo)}, payload) is None


# -- NUL bytes and payloads it cannot read ------------------------------------------------------


@pytest.mark.parametrize(
    "command",
    [
        "git -C '{repo}\0' commit -m x",
        "GIT_DIR='{repo}/.git\0' GIT_WORK_TREE={repo} git commit -m x",
        "cd '{repo}\0' && git commit -m x",
        "GIT_DIR={repo}/.git GIT_WORK_TREE='{repo}\0' git commit -m x",
        "git -C {repo} commit -F '{repo}/msg\0.txt'",
        "git -C {repo} commit -m x --pathspec-from-file='{repo}/l\0ist.txt'",
    ],
)
def test_a_nul_byte_in_the_command_is_dropped_as_bash_drops_it(
    repo: Path, env: dict, tmp_path: Path, command: str
) -> None:
    """A NUL in a path made `subprocess` and `os.path` raise, and the hook exited 1. That does not block."""
    stage(repo, env, "notes.md", "AcmeCorp\n")
    (repo / "msg.txt").write_text("hello\n")
    (repo / "list.txt").write_text("notes.md\n")

    reason = pretooluse(tmp_path, env, command.format(repo=repo))

    assert reason is not None
    assert "AcmeCorp (notes.md:1)" in reason


def test_a_nul_byte_in_a_cg_argv_is_dropped(repo: Path, env: dict, tmp_path: Path) -> None:
    stage(repo, env, "notes.md", "AcmeCorp\n")

    assert cg_run(tmp_path, env, ["git", "-C", f"{repo}\0", "commit", "-m", "x"]) is not None


def run_raw(env: dict, text: str) -> subprocess.CompletedProcess:
    return subprocess.run([HOOKS / "block-private-terms.sh"], input=text, capture_output=True, text=True, env=env)


@pytest.mark.parametrize(
    "tool_input",
    [
        {"command": ["git", "commit", "-m", "x"]},
        {"command": 5, "description": "git commit"},
        "git commit -m x",
    ],
)
def test_a_payload_it_cannot_read_that_mentions_a_commit_is_denied(repo: Path, env: dict, tool_input: object) -> None:
    """A TypeError from a non-string command exited 1, and an exit of 1 does not block the call."""
    reason = run_hook(env, {"tool_name": "Bash", "tool_input": tool_input, "cwd": str(repo)})

    assert reason is not None
    assert "could not read" in reason
    assert "commit" in reason


@pytest.mark.parametrize(
    "raw",
    ['["git commit -m x"]', "git commit -m x", '{"tool_name": "Bash", "tool_input": {"command": "git com\\mit'],
)
def test_a_payload_that_is_not_an_object_is_denied_when_it_mentions_a_commit(env: dict, raw: str) -> None:
    result = run_raw(env, raw)

    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)["hookSpecificOutput"]
    assert out["permissionDecision"] == "deny"
    assert "could not read" in out["permissionDecisionReason"]


@pytest.mark.parametrize(
    "raw", ["not json at all", "null", "[]", "{}", '{"tool_name": "Bash", "tool_input": {"command": 5}}']
)
def test_a_payload_it_cannot_read_that_mentions_no_commit_is_allowed(env: dict, raw: str) -> None:
    result = run_raw(env, raw)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == ""


def test_a_payload_it_cannot_read_is_allowed_without_terms(repo: Path, env: dict) -> None:
    (Path(env["HOME"]) / ".config" / "coding_agent_standards" / "private-terms.txt").unlink()

    assert run_hook(env, {"tool_name": "Bash", "tool_input": {"command": ["git", "commit"]}, "cwd": str(repo)}) is None


def test_a_term_file_that_is_not_text_does_not_crash_the_hook(repo: Path, env: dict) -> None:
    """A strict decode of the list raised, and the exit of 1 let every commit through."""
    stage(repo, env, "notes.md", "AcmeCorp\n")
    terms = Path(env["HOME"]) / ".config" / "coding_agent_standards" / "private-terms.txt"
    terms.write_bytes(b"AcmeCorp\n\xff\xfe\n")

    reason = pretooluse(repo, env, "git commit -m x")

    assert reason is not None
    assert "AcmeCorp (notes.md:1)" in reason
