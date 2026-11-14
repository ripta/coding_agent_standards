"""Tests for snips.py. Run: uv run --with pytest pytest claude/scripts"""

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import snips


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True).stdout.strip()


def _commit(repo: Path, path: str, text: str) -> str:
    (repo / path).write_text(text)
    _git(repo, "add", path)
    _git(repo, "commit", "-q", "-m", f"edit {path}")
    return _git(repo, "rev-parse", "HEAD")


def _snip(repo: Path, subject: str = snips.SUBJECT) -> str:
    _git(repo, "commit", "-q", "--allow-empty", "-m", subject, "-m", "End of work.")
    return _git(repo, "rev-parse", "HEAD")


def _subjects(repo: Path, base: str) -> list[str]:
    return _git(repo, "log", "--reverse", "--format=%s", f"{base}..HEAD").splitlines()


@pytest.fixture
def repo(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "t")
    _git(repo, "config", "commit.gpgsign", "false")
    monkeypatch.chdir(repo)
    return repo


def test_list_finds_only_empty_commits_with_the_snip_subject(repo):
    """Catches a snip test that trusts the subject alone, which would drop a commit carrying work."""
    base = _commit(repo, "a.txt", "a0\n")
    _commit(repo, "a.txt", "a1\n")
    real = _snip(repo)
    (repo / "b.txt").write_text("b\n")
    _git(repo, "add", "b.txt")
    _git(repo, "commit", "-q", "-m", snips.SUBJECT)
    impostor = _git(repo, "rev-parse", "HEAD")
    _git(repo, "commit", "-q", "--allow-empty", "-m", "an empty commit that is not a snip")

    result = snips.list_snips(base, "HEAD")
    assert result["snips"] == [real]
    assert result["not_empty"] == [impostor]


def test_redundant_is_a_snip_right_after_another_snip(repo):
    """Catches a rule that drops a lone snip, including one directly on the base, or one with work before it."""
    base = _commit(repo, "a.txt", "a0\n")
    lead = _snip(repo)
    _commit(repo, "a.txt", "a1\n")
    first = _snip(repo)
    second = _snip(repo)
    third = _snip(repo)
    _commit(repo, "a.txt", "a2\n")
    last = _snip(repo)

    result = snips.list_snips(base, "HEAD")
    assert result["snips"] == [lead, first, second, third, last]
    assert result["redundant"] == [second, third]


def test_drop_redundant_keeps_one_snip_per_run(repo):
    """Catches a drop that removes the wrong snip, leaves a run behind, or changes the tree."""
    base = _commit(repo, "a.txt", "a0\n")
    _commit(repo, "a.txt", "a1\n")
    kept = _snip(repo)
    dropped = _snip(repo)
    _commit(repo, "b.txt", "b\n")
    _snip(repo)
    tree = _git(repo, "rev-parse", "HEAD^{tree}")

    result = snips.drop(base, "redundant")
    assert result["dropped"] == [dropped]
    assert result["tree_matches"] is True
    assert _git(repo, "rev-parse", "HEAD~2") == kept
    assert _subjects(repo, base) == ["edit a.txt", snips.SUBJECT, "edit b.txt", snips.SUBJECT]
    assert _git(repo, "rev-parse", "HEAD^{tree}") == tree


def test_drop_all_leaves_no_snips_and_keeps_other_empty_commits(repo):
    """Catches a drop that also removes empty commits the user did not mark as snips."""
    base = _commit(repo, "a.txt", "a0\n")
    _snip(repo)
    _commit(repo, "a.txt", "a1\n")
    _git(repo, "commit", "-q", "--allow-empty", "-m", "keep me")
    _snip(repo)

    result = snips.drop(base, "all")
    assert len(result["dropped"]) == 2
    assert _subjects(repo, base) == ["edit a.txt", "keep me"]


def test_drop_ignores_autosquash_config(repo):
    """Catches a rebase that obeys rebase.autoSquash and reorders fixup commits while dropping snips."""
    base = _commit(repo, "a.txt", "a0\n")
    _commit(repo, "a.txt", "a1\n")
    _commit(repo, "b.txt", "b\n")
    (repo / "a.txt").write_text("a2\n")
    _git(repo, "commit", "-q", "-am", "fixup! edit a.txt")
    _snip(repo)
    _snip(repo)
    _git(repo, "config", "rebase.autoSquash", "true")

    snips.drop(base, "redundant")
    assert _subjects(repo, base) == ["edit a.txt", "edit b.txt", "fixup! edit a.txt", snips.SUBJECT]


def test_drop_with_nothing_to_drop_leaves_head_alone(repo):
    """Catches a drop that rewrites commits it did not need to touch."""
    base = _commit(repo, "a.txt", "a0\n")
    _snip(repo)
    head = _commit(repo, "a.txt", "a1\n")

    result = snips.drop(base, "redundant")
    assert result == {"dropped": [], "previous_head": head, "head": head, "tree_matches": True}
    assert _git(repo, "rev-parse", "HEAD") == head


def test_merge_in_range_is_rejected(repo):
    """Catches a drop that flattens a merge, which a linear rebase would do silently."""
    base = _commit(repo, "a.txt", "a0\n")
    _git(repo, "checkout", "-q", "-b", "side")
    _commit(repo, "b.txt", "b\n")
    _git(repo, "checkout", "-q", "main")
    _commit(repo, "a.txt", "a1\n")
    _git(repo, "merge", "-q", "--no-edit", "side")
    _snip(repo)
    _snip(repo)

    with pytest.raises(snips.SnipError, match="merge"):
        snips.drop(base, "redundant")


def test_cli_list_prints_json(repo, capsys):
    base = _commit(repo, "a.txt", "a0\n")
    snip = _snip(repo)
    assert snips.main(["snips.py", "list", "--base", base]) == 0
    assert f'"{snip}"' in capsys.readouterr().out
