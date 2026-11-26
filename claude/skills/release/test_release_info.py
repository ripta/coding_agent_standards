"""Tests for release-info.sh. Run: uv run --with pytest pytest claude/skills/release"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("release-info.sh")

# The script reads today's date from `date`. A stub on PATH fixes it, so month-scheme tags are stable.
DATE_STUB = """#!/bin/sh
case "$1" in
  +%Y-%m-%d) echo 2026-11-25 ;;
  +%Y) echo 2026 ;;
  +%m) echo 11 ;;
  *) exec /bin/date "$@" ;;
esac
"""

GIT_ENV = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.com",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.com",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
}


def _git(repo: Path, *args: str) -> str:
    env = {**os.environ, **GIT_ENV}
    return subprocess.run(["git", *args], cwd=repo, env=env, check=True, capture_output=True, text=True).stdout.strip()


def _commit(repo: Path, path: str, subject: str) -> None:
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a") as handle:
        handle.write(f"{subject}\n")
    _git(repo, "add", path)
    _git(repo, "commit", "-q", "-m", subject)


def _tag(repo: Path, name: str) -> None:
    _git(repo, "tag", "-a", name, "-m", f"release {name}")


def _run(repo: Path, tmp_path: Path, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    stub_dir = tmp_path / "stub-bin"
    stub_dir.mkdir(exist_ok=True)
    stub = stub_dir / "date"
    stub.write_text(DATE_STUB)
    stub.chmod(0o755)

    env = {**os.environ, **GIT_ENV, "PATH": f"{stub_dir}{os.pathsep}{os.environ['PATH']}"}
    return subprocess.run(
        ["bash", str(SCRIPT), *args], cwd=cwd or repo, env=env, capture_output=True, text=True
    )


def _sections(stdout: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current = None
    for line in stdout.splitlines():
        if line.startswith("@@"):
            current = line[2:]
            sections[current] = []
        elif current is not None:
            sections[current].append(line)
    return sections


@pytest.fixture
def repo(tmp_path) -> Path:
    path = tmp_path / "repo"
    path.mkdir()
    _git(path, "init", "-q", "-b", "main")
    _git(path, "config", "commit.gpgsign", "false")
    _git(path, "config", "tag.gpgsign", "false")
    return path


def _monorepo(repo: Path) -> None:
    """api is tagged first, then web, so web's tag is the nearest tag to HEAD."""
    _commit(repo, "apps/api/main.go", "api: init")
    _tag(repo, "apps/api/v1.2.0")
    _commit(repo, "apps/web/app.ts", "web: ui")
    _commit(repo, "apps/api/main.go", "api: add endpoint")
    _commit(repo, "apps/web/app.ts", "web: css")
    _tag(repo, "apps/web/v0.3.0")
    _commit(repo, "apps/api/main.go", "api: fix crash")


def test_untagged_run_ignores_tags_that_belong_to_components(repo, tmp_path):
    """Catches `git describe` taking a component's tag as the repo's latest tag, which crashed the semver parse."""
    _monorepo(repo)

    result = _run(repo, tmp_path)

    assert result.returncode == 0, result.stderr
    sections = _sections(result.stdout)
    assert sections["NO_TAGS"] == ["true"]
    assert sections["COMPONENTS"] == ["apps/api", "apps/web"]


def test_untagged_run_prefers_an_unprefixed_tag_over_a_nearer_component_tag(repo, tmp_path):
    """Catches the nearest tag winning, which would bump the repo's version from a component's number."""
    _commit(repo, "README.md", "root: init")
    _tag(repo, "v1.0.0")
    _monorepo(repo)
    _commit(repo, "3d/model.obj", "3d: init")
    _tag(repo, "3d/v1.4.0")

    result = _run(repo, tmp_path)

    assert result.returncode == 0, result.stderr
    sections = _sections(result.stdout)
    assert sections["LATEST_TAG"] == ["v1.0.0"]
    assert sections["NEXT_PATCH"] == ["v1.0.1"]
    assert sections["COMMIT_COUNT"] == ["6"]


def test_component_run_scopes_the_tag_the_count_and_the_log_to_its_path(repo, tmp_path):
    """Catches a component release that counts or drafts notes from commits of other components.

    It runs from another component's directory, so a cwd-relative path would also fail it.
    """
    _monorepo(repo)

    result = _run(repo, tmp_path, "--component", "apps/api", cwd=repo / "apps" / "web")

    assert result.returncode == 0, result.stderr
    sections = _sections(result.stdout)
    assert sections["COMPONENT"] == ["apps/api"]
    assert sections["SCHEME"] == ["semver"]
    assert sections["LATEST_TAG"] == ["apps/api/v1.2.0"]
    assert sections["NEXT_MAJOR"] == ["apps/api/v2.0.0"]
    assert sections["NEXT_MINOR"] == ["apps/api/v1.3.0"]
    assert sections["NEXT_PATCH"] == ["apps/api/v1.2.1"]
    assert sections["COMMIT_COUNT"] == ["2"]

    log = "\n".join(sections["GIT_LOG"])
    assert "api: add endpoint" in log
    assert "api: fix crash" in log
    assert "web:" not in log


def test_component_with_no_tags_counts_only_its_own_commits(repo, tmp_path):
    """Catches the first release of a component counting every commit in the repo."""
    _commit(repo, "apps/web/app.ts", "web: ui")
    _tag(repo, "apps/web/v0.3.0")
    _commit(repo, "apps/api/main.go", "api: init")
    _commit(repo, "apps/web/app.ts", "web: css")
    _commit(repo, "apps/api/main.go", "api: add endpoint")

    result = _run(repo, tmp_path, "--component", "apps/api")

    assert result.returncode == 0, result.stderr
    sections = _sections(result.stdout)
    assert sections["NO_TAGS"] == ["true"]
    assert sections["COMPONENT"] == ["apps/api"]
    assert sections["COMMIT_COUNT"] == ["2"]
    assert "web:" not in "\n".join(sections["GIT_LOG"])


def test_component_with_no_commits_since_its_tag_is_an_error_even_when_others_changed(repo, tmp_path):
    """Catches a component release being offered because some other component moved on."""
    _commit(repo, "apps/api/main.go", "api: init")
    _tag(repo, "apps/api/v1.2.0")
    _commit(repo, "apps/web/app.ts", "web: ui")

    result = _run(repo, tmp_path, "--component", "apps/api")

    assert result.returncode == 1
    assert "no commits" in result.stderr
    assert "apps/api" in result.stderr


@pytest.mark.parametrize(
    ("dirty_path", "args", "expected_exit"),
    [
        ("apps/web/app.ts", ["--component", "apps/api"], 0),
        ("apps/api/main.go", ["--component", "apps/api"], 1),
        ("apps/web/app.ts", [], 1),
    ],
    ids=["other-component-dirty", "own-component-dirty", "whole-repo-dirty"],
)
def test_the_dirty_check_covers_only_the_released_path(repo, tmp_path, dirty_path, args, expected_exit):
    """Catches a dirty file in one app blocking the release of another, or a whole-repo release ignoring it."""
    _commit(repo, "apps/api/main.go", "api: init")
    _commit(repo, "apps/web/app.ts", "web: ui")
    _tag(repo, "v1.0.0")
    _tag(repo, "apps/api/v1.2.0")
    _commit(repo, "apps/api/main.go", "api: add endpoint")
    (repo / dirty_path).write_text("uncommitted\n")

    result = _run(repo, tmp_path, *args)

    assert result.returncode == expected_exit, result.stderr
    if expected_exit:
        assert "dirty" in result.stderr


@pytest.mark.parametrize(
    ("args", "expected_next"),
    [
        (["--component", "apps/api"], "apps/api/v2026.11.3"),
        ([], "v2026.11.5"),
    ],
    ids=["component", "unprefixed"],
)
def test_month_serials_count_only_the_selected_prefix(repo, tmp_path, args, expected_next):
    """Catches another component's tags, or last month's, raising the serial of this release."""
    _commit(repo, "README.md", "root: init")
    _tag(repo, "v2026.11.4")
    _commit(repo, "apps/api/main.go", "api: init")
    _tag(repo, "apps/api/v2026.10.9")
    _tag(repo, "apps/api/v2026.11.1")
    _tag(repo, "apps/api/v2026.11.2")
    _commit(repo, "apps/web/app.ts", "web: ui")
    _tag(repo, "apps/web/v2026.11.7")
    _commit(repo, "apps/api/main.go", "api: add endpoint")
    _commit(repo, "README.md", "root: notes")

    result = _run(repo, tmp_path, *args)

    assert result.returncode == 0, result.stderr
    sections = _sections(result.stdout)
    assert sections["SCHEME"] == ["month"]
    assert sections["NEXT_TAG"] == [expected_next]


def test_a_component_does_not_inherit_tags_of_a_component_nested_under_it(repo, tmp_path):
    """Catches `apps/api` taking `apps/api/v2/v9.0.0` as its own latest tag.

    A nested directory named like a version is the one case where the tag glob alone cannot tell them apart.
    """
    _commit(repo, "apps/api/main.go", "api: init")
    _tag(repo, "apps/api/v1.0.0")
    _commit(repo, "apps/api/v2/lib.go", "v2: init")
    _tag(repo, "apps/api/v2/v9.0.0")
    _commit(repo, "apps/api/main.go", "api: add endpoint")

    result = _run(repo, tmp_path, "--component", "apps/api")

    assert result.returncode == 0, result.stderr
    sections = _sections(result.stdout)
    assert sections["LATEST_TAG"] == ["apps/api/v1.0.0"]
    assert sections["COMMIT_COUNT"] == ["2"]


def test_components_come_from_reachable_version_tags_only(repo, tmp_path):
    """Catches a component list padded with non-version tags or tags the release cannot see."""
    _commit(repo, "apps/api/main.go", "api: init")
    _tag(repo, "v1.0.0")
    _tag(repo, "apps/api/v1.0.0")
    _tag(repo, "apps/api/v1.1.0")
    _tag(repo, "tools/cli/v0.1.0")
    _tag(repo, "docs/notes")
    _tag(repo, "docs/v1/notes")
    _git(repo, "switch", "-q", "-c", "side")
    _commit(repo, "side/x.go", "side: init")
    _tag(repo, "side/v1.0.0")
    _git(repo, "switch", "-q", "main")
    _commit(repo, "apps/api/main.go", "api: add endpoint")

    result = _run(repo, tmp_path)

    assert result.returncode == 0, result.stderr
    assert _sections(result.stdout)["COMPONENTS"] == ["apps/api", "tools/cli"]


def test_listing_components_works_in_a_dirty_tree(repo, tmp_path):
    """Catches discovery failing on an unrelated dirty file, before the user can pick a clean component."""
    _monorepo(repo)
    (repo / "apps" / "web" / "app.ts").write_text("uncommitted\n")

    result = _run(repo, tmp_path, "--list-components", cwd=repo / "apps" / "api")

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["@@COMPONENTS", "apps/api", "apps/web", "@@END"]


def test_listing_components_in_a_plain_repo_is_an_empty_section(repo, tmp_path):
    """Catches a plain repo being reported as a monorepo."""
    _commit(repo, "README.md", "root: init")
    _tag(repo, "v1.0.0")

    result = _run(repo, tmp_path, "--list-components")

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["@@COMPONENTS", "@@END"]


@pytest.mark.parametrize(
    "component",
    ["apps/nope", "../elsewhere", "/etc", ".", "", "apps/a b"],
    ids=["missing", "parent", "absolute", "dot", "empty", "space"],
)
def test_a_component_must_be_a_tag_safe_path_in_the_repo(repo, tmp_path, component):
    """Catches a typo or a path outside the repo silently producing an unscoped release."""
    _commit(repo, "apps/api/main.go", "api: init")
    (repo / "apps" / "a b").mkdir()
    (repo / "apps" / "a b" / "x").write_text("x\n")
    _git(repo, "add", "apps")
    _git(repo, "commit", "-q", "-m", "space")

    result = _run(repo, tmp_path, "--component", component)

    assert result.returncode == 1
    assert "component" in result.stderr


def test_a_trailing_slash_names_the_same_component(repo, tmp_path):
    """Catches tab completion's `apps/api/` producing the tag `apps/api//v...`."""
    _monorepo(repo)

    result = _run(repo, tmp_path, "--component", "apps/api/")

    assert result.returncode == 0, result.stderr
    assert _sections(result.stdout)["NEXT_PATCH"] == ["apps/api/v1.2.1"]


def test_a_latest_tag_that_is_not_a_version_is_an_error_not_a_crash(repo, tmp_path):
    """Catches `value too great for base` leaking out of the semver arithmetic."""
    _commit(repo, "README.md", "root: init")
    _tag(repo, "v1beta")
    _commit(repo, "README.md", "root: more")

    result = _run(repo, tmp_path)

    assert result.returncode == 1
    assert "too great" not in result.stderr
    assert "v1beta" in result.stderr


def test_a_plain_semver_repo_keeps_its_sections(repo, tmp_path):
    """Pins the contract older callers parse. It passes before and after component support."""
    _commit(repo, "README.md", "root: init")
    _tag(repo, "v1.2.3")
    _commit(repo, "README.md", "root: more")

    result = _run(repo, tmp_path)

    assert result.returncode == 0, result.stderr
    sections = _sections(result.stdout)
    assert sections["SCHEME"] == ["semver"]
    assert sections["LATEST_TAG"] == ["v1.2.3"]
    assert sections["NEXT_MAJOR"] == ["v2.0.0"]
    assert sections["NEXT_MINOR"] == ["v1.3.0"]
    assert sections["NEXT_PATCH"] == ["v1.2.4"]
    assert sections["TODAY"] == ["2026-11-25"]
    assert sections["COMMIT_COUNT"] == ["1"]
    assert "root: more" in sections["GIT_LOG"]
    assert result.stdout.rstrip().endswith("@@END")


def test_a_repo_with_no_tags_keeps_its_sections(repo, tmp_path):
    """Pins the no-tags contract. It passes before and after component support."""
    _commit(repo, "README.md", "root: init")

    result = _run(repo, tmp_path)

    assert result.returncode == 0, result.stderr
    sections = _sections(result.stdout)
    assert sections["NO_TAGS"] == ["true"]
    assert sections["YEAR"] == ["2026"]
    assert sections["MONTH"] == ["11"]
    assert sections["COMMIT_COUNT"] == ["1"]
