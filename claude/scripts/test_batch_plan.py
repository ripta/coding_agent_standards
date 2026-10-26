"""Tests for batch_plan.py. Run: uv run --with pytest pytest claude/scripts"""

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import batch_plan


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True).stdout.strip()


def _commit(repo: Path, path: str, text: str) -> str:
    (repo / path).write_text(text)
    _git(repo, "add", path)
    _git(repo, "commit", "-q", "-m", f"edit {path}")
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "t")
    _git(repo, "config", "commit.gpgsign", "false")
    base = _commit(repo, "a.txt", "a0\n")
    monkeypatch.chdir(repo)
    commits = {
        "docs": _commit(repo, "docs.md", "docs\n"),
        "a1": _commit(repo, "a.txt", "a1\n"),
        "b": _commit(repo, "b.txt", "b\n"),
        "a2": _commit(repo, "a.txt", "a2\n"),
    }
    return {"base": base, "tip": commits["a2"], **commits}


def test_independent_streams_rebuild_the_tip(repo):
    plan = {"base": repo["base"], "tip": repo["tip"], "batches": [
        {"name": "docs", "commits": [repo["docs"]]},
        {"name": "a", "commits": [repo["a1"], repo["a2"]]},
        {"name": "b", "commits": [repo["b"]]},
    ]}
    result = batch_plan.verify(plan)
    assert result["ok"], result
    assert all(b["applies"] for b in result["batches"])


def test_hidden_dependency_is_a_conflict(repo):
    plan = {"base": repo["base"], "tip": repo["tip"], "batches": [
        {"name": "first", "commits": [repo["docs"], repo["a1"], repo["b"]]},
        {"name": "second", "commits": [repo["a2"]]},
    ]}
    result = batch_plan.verify(plan)
    assert not result["ok"]
    assert result["batches"][1] == {"name": "second", "applies": False, "conflict": repo["a2"]}


def test_declared_dependency_resolves_the_conflict(repo):
    plan = {"base": repo["base"], "tip": repo["tip"], "batches": [
        {"name": "first", "commits": [repo["docs"], repo["a1"], repo["b"]]},
        {"name": "second", "commits": [repo["a2"]], "after": ["first"]},
    ]}
    assert batch_plan.verify(plan)["ok"]


def test_missing_commit_is_reported(repo):
    plan = {"base": repo["base"], "tip": repo["tip"], "batches": [
        {"name": "a", "commits": [repo["a1"], repo["a2"]]},
        {"name": "b", "commits": [repo["b"]]},
    ]}
    result = batch_plan.verify(plan)
    assert not result["ok"]
    assert result["missing"] == [repo["docs"]]
    assert result["tree_matches"] is False


def test_worktree_is_cleaned_up(repo):
    plan = {"base": repo["base"], "tip": repo["tip"], "batches": [
        {"name": "all", "commits": [repo["docs"], repo["a1"], repo["b"], repo["a2"]]},
    ]}
    batch_plan.verify(plan)
    assert len(_git(Path.cwd(), "worktree", "list").splitlines()) == 1


@pytest.mark.parametrize(("batches", "message"), [
    ([], "no batches"),
    ([{"name": "x", "commits": ["HEAD"]}, {"name": "x", "commits": ["HEAD~1"]}], "unique"),
    ([{"name": "x", "commits": ["HEAD"], "after": ["y"]}], "unknown batch"),
    ([{"name": "x", "commits": ["HEAD"]}, {"name": "y", "commits": ["HEAD"]}], "repeats commits"),
])
def test_malformed_plans_are_rejected(repo, batches, message):
    with pytest.raises(batch_plan.PlanError, match=message):
        batch_plan.verify({"base": repo["base"], "tip": repo["tip"], "batches": batches})


def test_after_cycle_is_rejected(repo):
    batches = [{"name": "x", "commits": [repo["a1"]], "after": ["y"]},
               {"name": "y", "commits": [repo["a2"]], "after": ["x"]}]
    with pytest.raises(batch_plan.PlanError, match="cycle"):
        batch_plan.verify({"base": repo["base"], "tip": repo["tip"], "batches": batches})
