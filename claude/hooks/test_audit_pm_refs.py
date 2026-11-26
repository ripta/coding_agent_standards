"""Tests for audit-pm-refs.sh. Run: uv run --with pytest pytest claude/hooks"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

HOOK = Path(__file__).parent / "audit-pm-refs.sh"
REF = "// see MOSK-12\n"


def git(cwd: Path, *args: str) -> None:
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
    config = ["-c", "user.name=t", "-c", "user.email=t@example.com", "-c", "protocol.file.allow=always"]
    subprocess.run(["git", *config, *args], cwd=cwd, env=env, check=True, capture_output=True)


def make_repo(path: Path, files: dict) -> Path:
    path.mkdir(parents=True)
    git(path, "init", "-q", "-b", "main")
    for rel, text in files.items():
        (path / rel).parent.mkdir(parents=True, exist_ok=True)
        (path / rel).write_text(text)
    git(path, "add", ".")
    git(path, "commit", "-qm", "init")
    return path


def audit(project: Path, stop_hook_active: bool = False) -> tuple[int, str]:
    """Run the Stop hook. Return its exit code and what it told Claude."""
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(project)}
    stdin = json.dumps({"stop_hook_active": stop_hook_active})
    result = subprocess.run([HOOK, "MOSK"], input=stdin, env=env, capture_output=True, text=True)
    return result.returncode, result.stderr


def dirty(project: Path) -> None:
    """Change a tracked file, since the hook stands down when the tree matches HEAD."""
    (project / "README.md").write_text("changed\n")


@pytest.fixture
def project(tmp_path: Path) -> Path:
    return make_repo(
        tmp_path / "project",
        {
            "README.md": "hello\n",
            "app1/real.go": "package app1\n",
            "app1/spec/notes.go": REF,
            "app1/.claude/hook.go": REF,
            "spec/top.go": REF,
            ".claude/top.go": REF,
            "notes.md": "MOSK-12\n",
        },
    )


def test_a_clean_tree_is_skipped(project: Path) -> None:
    """A chat-only turn costs nothing, even when the tree already holds a reference."""
    (project / "app1" / "real.go").write_text(REF)
    git(project, "commit", "-qam", "ref")

    assert audit(project)[0] == 0


def test_a_reference_in_code_fails_the_stop(project: Path) -> None:
    (project / "app1" / "real.go").write_text(REF)

    code, err = audit(project)

    assert code == 2
    assert "app1/real.go:1:" in err
    assert "MOSK-12" in err


def test_a_retry_from_a_stop_hook_stands_down(project: Path) -> None:
    (project / "app1" / "real.go").write_text(REF)

    assert audit(project, stop_hook_active=True)[0] == 0


def test_exempt_paths_pass_at_any_depth(project: Path) -> None:
    """Markdown, spec/, and .claude/ are exempt, at the top and below it.

    block-pm-references.sh allows `*/spec/*` and `*/.claude/*`, so a monorepo app's own spec passes there.
    The audit once excluded only the top-level directories and flagged `app1/spec/notes.go`.
    """
    dirty(project)

    code, err = audit(project)

    assert code == 0, err


# -- submodules -------------------------------------------------------------------------------


@pytest.fixture
def with_submodule(tmp_path: Path, project: Path) -> Path:
    lib = make_repo(
        tmp_path / "lib",
        {"code.go": "package lib\n", "spec/x.go": REF, ".claude/y.go": REF, "n.md": "MOSK-9\n"},
    )
    git(project, "submodule", "add", "-q", str(lib), "vendor/lib")
    git(project, "commit", "-qm", "add lib")
    return project


def test_a_reference_inside_a_submodule_fails_the_stop(with_submodule: Path) -> None:
    """git grep does not enter a submodule by itself, so the audit passed a tree whose submodule held one."""
    sub = with_submodule / "vendor" / "lib"
    (sub / "code.go").write_text(REF)

    code, err = audit(with_submodule)

    assert code == 2, err
    assert "vendor/lib/code.go:1:" in err


def test_a_submodule_keeps_the_same_exemptions(with_submodule: Path) -> None:
    """Only code.go is flagged. The submodule's spec/, .claude/, and markdown follow the parent's rule."""
    sub = with_submodule / "vendor" / "lib"
    (sub / "code.go").write_text(REF)

    _, err = audit(with_submodule)

    assert "vendor/lib/code.go" in err
    assert "vendor/lib/spec" not in err
    assert "vendor/lib/.claude" not in err
    assert "n.md" not in err


def test_a_submodule_that_was_never_checked_out_is_skipped(tmp_path: Path, with_submodule: Path) -> None:
    clone = tmp_path / "clone"
    subprocess.run(["git", "clone", "-q", str(with_submodule), str(clone)], check=True, capture_output=True)
    (clone / "README.md").write_text("changed\n")

    code, err = audit(clone)

    assert code == 0, err
