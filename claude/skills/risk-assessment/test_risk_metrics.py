"""Tests for risk-metrics.sh. Run: uv run --with pytest pytest claude/skills/risk-assessment"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("risk-metrics.sh")

GIT_ENV = {
    "GIT_AUTHOR_NAME": "alice",
    "GIT_AUTHOR_EMAIL": "alice@example.com",
    "GIT_COMMITTER_NAME": "alice",
    "GIT_COMMITTER_EMAIL": "alice@example.com",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
}

DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _git(repo: Path, *args: str, author: str = "alice") -> str:
    env = {**os.environ, **GIT_ENV, "GIT_AUTHOR_EMAIL": f"{author}@example.com"}
    command = ["git", "-c", "protocol.file.allow=always", "-c", "commit.gpgsign=false", *args]
    return subprocess.run(command, cwd=repo, env=env, check=True, capture_output=True, text=True).stdout.strip()


def _init(path: Path) -> Path:
    path.mkdir(parents=True)
    _git(path, "init", "-q", "-b", "main")
    return path


def _commit(repo: Path, path: str, text: str, subject: str, author: str = "alice") -> None:
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a") as handle:
        handle.write(text)
    _git(repo, "add", path)
    _git(repo, "commit", "-q", "-m", subject, author=author)


def _metrics(repo: Path, *args: str, cwd: Path | None = None) -> dict[str, list[str]]:
    env = {**os.environ, **GIT_ENV}
    result = subprocess.run(
        ["bash", str(SCRIPT), *args], cwd=cwd or repo, env=env, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    return _sections(result.stdout)


def _sections(stdout: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current = None
    for line in stdout.splitlines():
        if line.startswith("## "):
            current = line[3:].split(" ", 1)[0]
            sections[current] = []
        elif line and current is not None:
            sections[current].append(line)
    return sections


@pytest.fixture
def mono(tmp_path) -> Path:
    """A monorepo whose web app has a bugfix commit by a second author."""
    repo = _init(tmp_path / "mono")
    _commit(repo, "apps/api/a.go", "a\n", "api: init")
    _commit(repo, "apps/web/w.txt", "web file, line 1\nweb file, line 2\nweb file, line 3\n", "web: init")
    _commit(repo, "apps/web/w.txt", "web file, line 4\n", "web: fix crash on load", author="bob")
    return repo


def test_untracked_files_outside_the_cwd_are_listed(mono):
    """Catches `git ls-files --others` dropping every untracked file outside the caller's directory."""
    (mono / "apps" / "web" / "x.txt").write_text("1\n2\n3\n")

    sections = _metrics(mono, cwd=mono / "apps" / "api")

    assert "3\t0\tapps/web/x.txt" in sections["files"]
    assert "never (new file)\t0\tapps/web/x.txt" in sections["ownership"]


def test_history_of_a_file_outside_the_cwd_is_found(mono):
    """Catches root-relative diff paths being read as cwd-relative by `git log`.

    That reported a file with two authors and a bugfix as `never (new file)` with no bugfixes.
    """
    (mono / "apps" / "web" / "w.txt").write_text("changed\n")

    sections = _metrics(mono, cwd=mono / "apps" / "api")

    assert "1\tapps/web/w.txt" in sections["hotspots"]
    (row,) = [r for r in sections["ownership"] if r.endswith("\tapps/web/w.txt")]
    last, authors, _ = row.split("\t")
    assert DATE.match(last), row
    assert authors == "2"


@pytest.mark.parametrize("args", [[], ["HEAD~1"], ["HEAD~1", "HEAD"]], ids=["worktree", "base", "range"])
def test_every_mode_reports_the_same_from_a_subdirectory(mono, args):
    """Catches any section depending on the directory the script is started in."""
    (mono / "apps" / "web" / "w.txt").write_text("changed\n")
    (mono / "apps" / "web" / "x.txt").write_text("1\n")

    from_root = _metrics(mono, *args)
    from_subdir = _metrics(mono, *args, cwd=mono / "apps" / "api")

    assert from_subdir == from_root
    assert any(row.endswith("\tapps/web/w.txt") for row in from_root["ownership"])


@pytest.mark.parametrize(
    ("destination", "committed"),
    [
        ("apps/web/z.txt", False),
        ("docs/w.txt", False),
        ("apps/web/z.txt", True),
        ("docs/w.txt", True),
    ],
    ids=["brace-worktree", "plain-worktree", "brace-committed", "plain-committed"],
)
def test_a_renamed_file_keeps_the_history_it_had_under_its_old_name(mono, destination, committed):
    """Catches a rename being read as a new file.

    Git writes the row as `apps/web/{w.txt => z.txt}` or `apps/web/w.txt => docs/w.txt`. Neither is a
    path, so the history lookups found nothing, and a file with two authors and a bugfix looked new.
    The committed case also holds that the rename commit itself is the change, not history: its
    subject says fix, and it must not count as a second bugfix.
    """
    (mono / destination).parent.mkdir(parents=True, exist_ok=True)
    _git(mono, "mv", "apps/web/w.txt", destination)
    with (mono / destination).open("a") as handle:
        handle.write("edited\n")
    if committed:
        _git(mono, "add", destination)
        _git(mono, "commit", "-q", "-m", "fix: move the web file")
    args = ["HEAD~1", "HEAD"] if committed else []

    sections = _metrics(mono, *args)

    # Counts stay as git reports them for a rename with an edit: one line added, none deleted.
    assert f"1\t0\t{destination}" in sections["files"]
    assert "files_changed\t1" in sections["summary"]
    assert f"1\t{destination}" in sections["hotspots"]
    (row,) = [r for r in sections["ownership"] if r.endswith(f"\t{destination}")]
    last, authors, _ = row.split("\t")
    assert DATE.match(last), row
    assert authors == "2"


@pytest.fixture
def branches(tmp_path) -> Path:
    """main has one bugfix by bob. feature adds a bugfix by carol on top. Checked out: stale, before both."""
    repo = _init(tmp_path / "branches")
    _commit(repo, "apps/api/a.go", "a1\n", "api: init")
    _git(repo, "branch", "stale")
    _commit(repo, "apps/api/a.go", "a2\n", "fix: crash", author="bob")
    _git(repo, "switch", "-q", "-c", "feature")
    _commit(repo, "apps/api/a.go", "a3\n", "fix: handle nil", author="carol")
    _git(repo, "switch", "-q", "stale")
    return repo


def test_a_range_reads_the_history_before_the_change_not_the_checked_out_branch(branches):
    """Catches `git log` reading whatever is checked out, so a PR assessed from another branch got its history.

    History is read from the merge-base. Reading the head instead would count the change's own bugfix
    and its author as history, and every touched file would show its last commit as the change.
    """
    sections = _metrics(branches, "main", "feature")

    assert "1\tapps/api/a.go" in sections["hotspots"]
    (row,) = [r for r in sections["ownership"] if r.endswith("\tapps/api/a.go")]
    assert row.split("\t")[1] == "2"


def test_a_base_reads_the_history_at_the_base_not_the_checked_out_branch(branches):
    """Catches `risk-metrics.sh main` counting the commits it is diffing against as history."""
    _git(branches, "switch", "-q", "feature")

    sections = _metrics(branches, "main")

    assert "1\tapps/api/a.go" in sections["hotspots"]
    (row,) = [r for r in sections["ownership"] if r.endswith("\tapps/api/a.go")]
    assert row.split("\t")[1] == "2"


@pytest.fixture
def super_repo(tmp_path):
    """A superproject with a submodule at libs/lib. Returns (superproject, upstream lib)."""
    lib = _init(tmp_path / "lib")
    _commit(lib, "src/a.go", "a1\na2\n", "init")
    _commit(lib, "src/a.go", "a2b\n", "fix: off by one", author="bob")

    repo = _init(tmp_path / "super")
    _commit(repo, "apps/api/main.go", "m\n", "api: init")
    _git(repo, "submodule", "add", "-q", str(lib), "libs/lib")
    _git(repo, "commit", "-q", "-m", "add the lib submodule")
    return repo, lib


def _move_submodule_forward(repo: Path) -> None:
    sub = repo / "libs" / "lib"
    _commit(sub, "src/a.go", "a3\na4\n", "fix: nil check", author="carol")
    _commit(sub, "src/b.go", "b1\n", "add b")


def test_a_changed_submodule_is_replaced_by_its_own_changed_files(super_repo):
    """Catches a submodule bump reporting as `1 1 libs/lib` with no per-file metrics.

    The uncommitted file in the submodule is part of the working tree, so it is listed as well.
    """
    repo, _ = super_repo
    _move_submodule_forward(repo)
    (repo / "libs" / "lib" / "docs").mkdir()
    (repo / "libs" / "lib" / "docs" / "n.txt").write_text("1\n2\n3\n")

    sections = _metrics(repo, cwd=repo / "apps" / "api")

    assert sorted(sections["files"]) == [
        "1\t0\tlibs/lib/src/b.go",
        "2\t0\tlibs/lib/src/a.go",
        "3\t0\tlibs/lib/docs/n.txt",
    ]
    assert "files_changed\t3" in sections["summary"]
    assert "insertions\t6" in sections["summary"]

    # The bugfix and the second author live in the submodule's history, not the superproject's. The
    # bump's own commits, a bugfix by a third author, are the change and do not count as history.
    assert "1\tlibs/lib/src/a.go" in sections["hotspots"]
    (row,) = [r for r in sections["ownership"] if r.endswith("\tlibs/lib/src/a.go")]
    last, authors, _ = row.split("\t")
    assert DATE.match(last), row
    assert authors == "2"
    assert "never (new file)\t0\tlibs/lib/src/b.go" in sections["ownership"]
    assert "never (new file)\t0\tlibs/lib/docs/n.txt" in sections["ownership"]

    (submodule,) = sections["submodules"]
    path, old, new, status = submodule.split("\t")
    assert (path, status) == ("libs/lib", "expanded")
    assert old != new


def test_a_committed_submodule_bump_is_expanded_between_its_two_commits(super_repo):
    """Catches the range mode reading the submodule's working tree instead of the two recorded commits."""
    repo, _ = super_repo
    _move_submodule_forward(repo)
    _git(repo, "add", "libs/lib")
    _git(repo, "commit", "-q", "-m", "bump the lib")
    (repo / "libs" / "lib" / "extra.txt").write_text("not part of the range\n")

    sections = _metrics(repo, "HEAD~1", "HEAD")

    assert sorted(sections["files"]) == ["1\t0\tlibs/lib/src/b.go", "2\t0\tlibs/lib/src/a.go"]
    assert "1\tlibs/lib/src/a.go" in sections["hotspots"]


def test_a_new_submodule_lists_all_of_its_files_as_added(tmp_path, super_repo):
    """Catches an added submodule being diffed against a commit it never had."""
    repo, _ = super_repo
    other = _init(tmp_path / "other")
    _commit(other, "o.txt", "o1\no2\n", "init")
    _git(repo, "submodule", "add", "-q", str(other), "libs/other")

    sections = _metrics(repo)

    assert "2\t0\tlibs/other/o.txt" in sections["files"]
    assert not [row for row in sections["files"] if row.endswith("\tlibs/other")]
    assert "never (new file)\t0\tlibs/other/o.txt" in sections["ownership"]
    (submodule,) = sections["submodules"]
    assert submodule.split("\t")[::3] == ["libs/other", "expanded"]


def test_a_submodule_that_is_not_checked_out_keeps_its_gitlink_row_and_says_why(tmp_path, super_repo):
    """Catches the metrics silently covering less than the change, with no word that a submodule was skipped."""
    repo, _ = super_repo
    _move_submodule_forward(repo)
    new = _git(repo / "libs" / "lib", "rev-parse", "HEAD")

    clone = tmp_path / "clone"
    _git(tmp_path, "clone", "-q", str(repo), str(clone))
    _git(clone, "update-index", "--cacheinfo", f"160000,{new},libs/lib")
    _git(clone, "commit", "-q", "-m", "bump the lib")

    sections = _metrics(clone, "HEAD~1", "HEAD")

    assert sections["files"] == ["1\t1\tlibs/lib"]
    (submodule,) = sections["submodules"]
    assert submodule.split("\t")[::3] == ["libs/lib", "not-initialized"]


def test_a_submodule_without_the_new_commit_keeps_its_gitlink_row_and_says_why(tmp_path, super_repo):
    """Catches a range diff run in a submodule that never fetched the commit, which would fail the whole script."""
    repo, _ = super_repo
    _move_submodule_forward(repo)
    new = _git(repo / "libs" / "lib", "rev-parse", "HEAD")

    clone = tmp_path / "clone"
    _git(tmp_path, "clone", "-q", "--recurse-submodules", str(repo), str(clone))
    _git(clone, "update-index", "--cacheinfo", f"160000,{new},libs/lib")
    _git(clone, "commit", "-q", "-m", "bump the lib")

    sections = _metrics(clone, "HEAD~1", "HEAD")

    assert sections["files"] == ["1\t1\tlibs/lib"]
    (submodule,) = sections["submodules"]
    assert submodule.split("\t")[::3] == ["libs/lib", "missing-objects"]


def test_a_submodule_without_the_old_commit_keeps_its_gitlink_row_and_says_why(tmp_path, super_repo):
    """Catches a range diff run from a commit the submodule does not have, which would fail the whole script."""
    repo, _ = super_repo

    clone = tmp_path / "clone"
    _git(tmp_path, "clone", "-q", "--recurse-submodules", str(repo), str(clone))
    present = _git(clone / "libs" / "lib", "rev-parse", "HEAD")
    _git(clone, "update-index", "--cacheinfo", f"160000,{'ab' * 20},libs/lib")
    _git(clone, "commit", "-q", "-m", "point at a commit nobody has")
    _git(clone, "update-index", "--cacheinfo", f"160000,{present},libs/lib")
    _git(clone, "commit", "-q", "-m", "point back")

    sections = _metrics(clone, "HEAD~1", "HEAD")

    assert sections["files"] == ["1\t1\tlibs/lib"]
    (submodule,) = sections["submodules"]
    assert submodule.split("\t")[::3] == ["libs/lib", "missing-objects"]


def test_a_repo_without_submodules_prints_no_submodules_section(mono):
    """Pins the output of a plain repo. It passes before and after submodule support."""
    (mono / "apps" / "web" / "w.txt").write_text("changed\n")

    sections = _metrics(mono)

    assert "submodules" not in sections
    assert list(sections) == ["target", "files", "summary", "hotspots", "ownership", "risk_markers"]
