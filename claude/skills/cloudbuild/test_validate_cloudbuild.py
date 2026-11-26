"""Tests for validate-cloudbuild.py. Run: uv run --with pytest --with pyyaml pytest claude/skills/cloudbuild"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

# The script name has a hyphen, so it loads by path. It registers itself first because
# dataclasses resolves string annotations through sys.modules.
_spec = importlib.util.spec_from_file_location(
    "validate_cloudbuild", Path(__file__).parent / "validate-cloudbuild.py"
)
validate = importlib.util.module_from_spec(_spec)
sys.modules["validate_cloudbuild"] = validate
_spec.loader.exec_module(validate)

CLEAN = """\
# GCB CI for mono. Triggers mono-pr, mono-main and mono-tag, us-central1.

steps:
  - id: CI
    name: 'golang:1.26-trixie'
    entrypoint: 'bash'
    args:
      - '-c'
      - |
        set -e
        make ci

timeout: 600s
"""

# No steps, which CB004 reports as an error.
BROKEN = "# GCB CI for mono. Triggers mono-pr, mono-main and mono-tag, us-central1.\n\ntimeout: 600s\n"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True)


def _write(repo: Path, path: str, text: str = CLEAN) -> None:
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A monorepo with a root config and one per-app config, all committed, with cwd at its root."""
    root = tmp_path / "mono"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "T")
    _git(root, "config", "commit.gpgsign", "false")
    _write(root, "cloudbuild.yaml")
    _write(root, "api/cloudbuild.yaml")
    _write(root, "web/cloudbuild.bench.yml")
    _git(root, "add", ".")
    _git(root, "commit", "-q", "-m", "init")
    monkeypatch.chdir(root)
    return root


def _found(repo: Path) -> set[str]:
    """The default paths, as they sit under the repo root. A returned path is relative to the cwd."""
    return {str(p.resolve().relative_to(repo.resolve())) for p in validate.default_paths()}


@pytest.mark.parametrize("cwd", ["", "api", "web"])
def test_default_paths_reach_every_config_in_the_repo_from_any_directory(
    repo: Path, monkeypatch: pytest.MonkeyPatch, cwd: str
) -> None:
    """A per-app config is not skipped when the run starts at the root or inside an app.

    The old default globbed only the working directory, so a run at the root never saw an app's
    config. This cannot show how a submodule behaves. A submodule is its own repo, and git does
    not list into it from the parent.
    """
    monkeypatch.chdir(repo / cwd)

    assert _found(repo) == {"cloudbuild.yaml", "api/cloudbuild.yaml", "web/cloudbuild.bench.yml"}


def test_default_paths_include_an_untracked_config_and_skip_an_ignored_one(repo: Path) -> None:
    """A config the skill just wrote is found before it is committed. A gitignored one is not."""
    _write(repo, "worker/cloudbuild.yaml")
    _write(repo, "scratch/cloudbuild.yaml")
    (repo / ".gitignore").write_text("scratch/\n", encoding="utf-8")

    found = _found(repo)

    assert "worker/cloudbuild.yaml" in found
    assert "scratch/cloudbuild.yaml" not in found


def test_default_paths_skip_a_tracked_config_deleted_from_the_working_tree(repo: Path) -> None:
    """git ls-files still lists a deleted file. Reading it would fail the whole run with a usage error."""
    (repo / "api" / "cloudbuild.yaml").unlink()

    assert "api/cloudbuild.yaml" not in _found(repo)


def test_a_broken_per_app_config_fails_a_run_with_no_paths(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The contract a caller sees: no arguments checks every app's config, and the failure names its file."""
    _write(repo, "api/cloudbuild.yaml", BROKEN)

    status = validate.main([])

    assert status == 1
    assert "api/cloudbuild.yaml:" in capsys.readouterr().out


def test_explicit_paths_are_validated_alone(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Paths on the command line still win. A broken config elsewhere in the repo does not leak in."""
    _write(repo, "api/cloudbuild.yaml", BROKEN)

    status = validate.main(["cloudbuild.yaml"])

    assert status == 0
    assert "api/cloudbuild.yaml" not in capsys.readouterr().out


def test_outside_a_git_repo_the_default_is_the_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without git the old behavior holds. It cannot show what a checkout outside git should look for."""
    plain = tmp_path / "plain"
    _write(plain, "cloudbuild.yaml")
    _write(plain, "api/cloudbuild.yaml")
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    monkeypatch.chdir(plain)

    assert [str(p) for p in validate.default_paths()] == ["cloudbuild.yaml"]


def test_a_repo_with_no_config_is_a_usage_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An empty result still exits 2 with a message, not 0 with nothing checked."""
    empty = tmp_path / "empty"
    empty.mkdir()
    _git(empty, "init", "-q", "-b", "main")
    monkeypatch.chdir(empty)

    assert validate.main([]) == 2
    assert "no cloudbuild" in capsys.readouterr().err
