"""Tests for standards_imports.py. Run: uv run --with pytest pytest claude/scripts"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import standards_imports as si

CLAUDE = Path(__file__).resolve().parents[1]
LINK = "~/.claude/coding-standards-current"
CHECKOUT = "~/projects/coding_agent_standards"


def kinds(text: str) -> list:
    return [(r.kind, r.rel) for r in si.parse_text(text)]


# -- parsing --------------------------------------------------------------------------------

OLD_FORMS = [
    (f"{CHECKOUT}/claude/rules/commit-style.md", "rules/commit-style.md"),
    ("~/coding-standards/claude/rules/commit-style.md", "rules/commit-style.md"),
    (f"{CHECKOUT}/practices/testing.md", "practices/testing.md"),
    (f"{CHECKOUT}/languages/go.md", "languages/go.md"),
    (f"{CHECKOUT}/profiles/go-service.md", "profiles/go-service.md"),
    (f"{CHECKOUT}/project-management/glossary.md", "project-management/glossary.md"),
    (f"{CHECKOUT}/knowledge/wiki.md", "knowledge/wiki.md"),
    ("~/coding-standards/practices/testing.md", "practices/testing.md"),
    ("~/coding-standards/languages/go.md", "languages/go.md"),
    ("~/coding-standards/profiles/go-service.md", "profiles/go-service.md"),
    ("~/coding-standards/project-management/glossary.md", "project-management/glossary.md"),
    ("~/coding-standards/knowledge/wiki.md", "knowledge/wiki.md"),
]


@pytest.mark.parametrize(("path", "rel"), OLD_FORMS)
def test_every_old_prefix_maps_onto_the_link(path: str, rel: str) -> None:
    """A form the mapping misses would leave a project importing a path that loads nothing."""
    assert kinds(f"@{path}\n") == [("old", rel)]


PARSE_CASES = [
    ("link form", f"@{LINK}/profiles/go-service.md\n", [("link", "profiles/go-service.md")]),
    ("list marker and lead", f"- See @{LINK}/rules/a.md\n", [("link", "rules/a.md")]),
    ("inside prose", f"Follow the standards in @{CHECKOUT}/claude/rules/a.md today\n", [("old", "rules/a.md")]),
    ("plain text", f"- {CHECKOUT}/profiles/python-project.md\n", [("plain", "profiles/python-project.md")]),
    ("plain text on the link", f"Read {LINK}/rules/a.md first\n", [("plain", "rules/a.md")]),
    ("unmapped old path", f"@{CHECKOUT}/bugs/a.md\n", [("old", None)]),
    ("two on a line", f"@{LINK}/rules/a.md @{LINK}/rules/b.md\n", [("link", "rules/a.md"), ("link", "rules/b.md")]),
    ("prose naming the checkout", f"The checkout at {CHECKOUT} holds them\n", []),
    ("directory with no file", f"See {CHECKOUT}/profiles/ for the list\n", []),
    ("not markdown", f"@{CHECKOUT}/claude/hooks/check-setup.sh\n", []),
    ("code span", f"Write `@{LINK}/rules/a.md` to import it\n", []),
    ("double-backtick span", f"Write ``@{LINK}/rules/a.md`` to import it\n", []),
    ("backtick fence", f"```\n@{LINK}/rules/a.md\n```\n", []),
    ("tilde fence", f"~~~md\n@{LINK}/rules/a.md\n~~~\n", []),
    ("after a fence", f"```\nx\n```\n@{LINK}/rules/a.md\n", [("link", "rules/a.md")]),
    ("markdown link target", f"[a]({LINK}/rules/a.md)\n", [("linktarget", "rules/a.md")]),
    ("old markdown link target", f"[a]({CHECKOUT}/claude/rules/a.md)\n", [("linktarget", "rules/a.md")]),
    ("reference definition", f"[a]: {CHECKOUT}/claude/rules/a.md\n", [("linktarget", "rules/a.md")]),
    ("after a span", f"Use `x` then @{LINK}/rules/a.md\n", [("link", "rules/a.md")]),
]


@pytest.mark.parametrize(("name", "text", "expected"), PARSE_CASES, ids=[c[0] for c in PARSE_CASES])
def test_parse_finds_only_what_claude_code_would_load_or_miss(name: str, text: str, expected: list) -> None:
    """Code spans and fences hold no imports, and prose naming the checkout is not a standards path."""
    assert kinds(text) == expected


def test_ref_offsets_index_the_original_line() -> None:
    """Edits splice by offset, so a code span before the import must not shift them."""
    line = f"`code` See @{LINK}/rules/a.md."
    (ref,) = si.parse_text(line)
    assert line[ref.start : ref.end] == f"@{LINK}/rules/a.md"


IMPORT_ONLY = [
    (f"@{LINK}/rules/a.md", True),
    (f"- @{LINK}/rules/a.md", True),
    (f"* See @{LINK}/rules/a.md", True),
    (f"1. @{LINK}/rules/a.md", True),
    (f"Standards: @{LINK}/rules/a.md", True),
    (f"@{LINK}/rules/a.md @{LINK}/rules/b.md", True),
    (f"This project follows the standards defined in @{LINK}/rules/a.md", False),
    (f"@{LINK}/rules/a.md has the rules", False),
    (f"## @{LINK}/rules/a.md", False),
]


@pytest.mark.parametrize(("line", "expected"), IMPORT_ONLY)
def test_import_only_lines_are_the_only_ones_safe_to_delete(line: str, expected: bool) -> None:
    """Deleting a prose line would delete the user's words."""
    assert si.is_import_only(line, si.parse_text(line)) is expected


# -- snapshots ------------------------------------------------------------------------------


def snapshot(tmp_path: Path, files: dict) -> Path:
    root = tmp_path / "snap"
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return root


@pytest.mark.parametrize("rel", [None, "", "../x.md", "rules/../../x.md", "/etc/hosts", "rules/missing.md", "rules"])
def test_in_snapshot_rejects_what_is_not_a_snapshot_file(tmp_path: Path, rel: object) -> None:
    """A path that escapes the snapshot or names no file must not count as resolving."""
    snap = snapshot(tmp_path, {"rules/a.md": "a\n"})
    (tmp_path / "x.md").write_text("outside\n")
    assert si.in_snapshot(snap, rel) is False  # type: ignore[arg-type]
    assert si.in_snapshot(snap, "rules/a.md") is True


def test_included_files_follow_link_and_relative_imports(tmp_path: Path) -> None:
    """A profile includes its relative imports, which resolve against its own directory, and its link imports."""
    snap = snapshot(
        tmp_path,
        {
            "profiles/p.md": f"@../profiles/base.md\n@../languages/go.md\n@{LINK}/practices/t.md\n",
            "profiles/base.md": f"@{LINK}/rules/a.md\n",
            "languages/go.md": "go\n",
            "practices/t.md": "t\n",
            "rules/a.md": "a\n",
            "rules/unrelated.md": "u\n",
        },
    )
    assert si.profile_files(snap, ["p"]) == {
        "profiles/p.md", "profiles/base.md", "languages/go.md", "practices/t.md", "rules/a.md",
    }


def test_included_files_skip_code_cycles_and_missing_files(tmp_path: Path) -> None:
    """An import in a code span is text. A cycle must end. A missing import adds nothing."""
    snap = snapshot(
        tmp_path,
        {
            "profiles/p.md": f"@../profiles/q.md\n`@{LINK}/rules/a.md`\n```\n@{LINK}/rules/b.md\n```\n@../gone.md\n",
            "profiles/q.md": "@../profiles/p.md\n@../../outside.md\n",
            "rules/a.md": "a\n",
            "rules/b.md": "b\n",
        },
    )
    assert si.profile_files(snap, ["p"]) == {"profiles/p.md", "profiles/q.md"}


def test_real_profiles_resolve_in_the_real_plugin() -> None:
    """A profile that imports a file the plugin lacks would load nothing for every project that uses it."""
    profiles = sorted((CLAUDE / "profiles").glob("*.md"))
    assert profiles
    for profile in profiles:
        rel = f"profiles/{profile.name}"
        included = si.included_files(CLAUDE, rel)
        assert rel in included
        for current in included:
            for ref in si.parse_file(CLAUDE / current):
                if ref.at:
                    assert si.in_snapshot(CLAUDE, ref.rel), f"{current} imports {ref.path}, which is not in claude/"
    assert "rules/commit-style.md" in si.profile_files(CLAUDE, ["baseline"])


# -- discovery ------------------------------------------------------------------------------


def git(cwd: Path, *args: str) -> None:
    env = {**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null"}
    config = ["-c", "user.name=t", "-c", "user.email=t@example.com", "-c", "commit.gpgsign=false"]
    subprocess.run(["git", *config, *args], cwd=cwd, env=env, check=True, capture_output=True)


def repo(tmp_path: Path) -> Path:
    root = (tmp_path / "project").resolve()
    (root / "pkg" / "deep").mkdir(parents=True)
    git(root, "init", "-q")
    git(root, "commit", "-q", "--allow-empty", "-m", "init")
    return root


def test_discovery_reads_each_directory_up_to_the_git_root(tmp_path: Path) -> None:
    """Claude Code loads files from every parent up to the git root, and a file above it is not loaded."""
    root = repo(tmp_path)
    (root.parent / "CLAUDE.md").write_text("above the repo\n")
    (root / "CLAUDE.md").write_text("root\n")
    (root / ".claude").mkdir()
    (root / ".claude" / "CLAUDE.md").write_text("dot\n")
    (root / "pkg" / "CLAUDE.local.md").write_text("pkg\n")
    found = si.find_instruction_files(si.locate(root / "pkg" / "deep"))
    assert found == [root / "pkg" / "CLAUDE.local.md", root / "CLAUDE.md", root / ".claude" / "CLAUDE.md"]


def test_discovery_outside_git_reads_only_the_current_directory(tmp_path: Path) -> None:
    """With no git root to stop at, a parent's file must not be claimed."""
    plain = tmp_path / "plain" / "sub"
    plain.mkdir(parents=True)
    (plain.parent / "CLAUDE.md").write_text("parent\n")
    (plain / "CLAUDE.md").write_text("here\n")
    assert si.find_instruction_files(si.locate(plain)) == [plain.resolve() / "CLAUDE.md"]


def test_linked_worktree_finds_the_main_checkouts_local_file(tmp_path: Path) -> None:
    """Only a worktree's own CLAUDE.local.md loads, so the main checkout's copy has to be found separately."""
    root = repo(tmp_path)
    (root / "CLAUDE.local.md").write_text("main\n")
    tree = (tmp_path / "tree").resolve()
    git(root, "worktree", "add", "-q", str(tree), "-b", "tree")

    checkout = si.locate(tree)
    assert checkout.root == tree
    assert checkout.main_root == root
    assert si.find_instruction_files(checkout) == []
    assert si.main_copies(checkout) == [(tree / "CLAUDE.local.md", root / "CLAUDE.local.md")]
    assert si.locate(root).main_root is None


def test_refs_command_prints_files_and_resolution(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    """The refs command is the surface check-setup.sh reads, so its JSON shape is a contract."""
    root = repo(tmp_path)
    (root / "CLAUDE.md").write_text(f"@{LINK}/rules/a.md\n@{LINK}/rules/gone.md\n")
    snap = snapshot(tmp_path, {"rules/a.md": "a\n"})
    assert si.main(["refs", "--cwd", str(root), "--snapshot", str(snap), "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    (file,) = data["files"]
    assert [(r["rel"], r["resolves"]) for r in file["refs"]] == [("rules/a.md", True), ("rules/gone.md", False)]


def test_aliases_of_one_instruction_file_are_found_once(tmp_path: Path) -> None:
    """A .claude/CLAUDE.md symlinked to ../CLAUDE.md is one file. Listing it twice makes callers edit it twice."""
    root = repo(tmp_path)
    (root / "CLAUDE.md").write_text("root\n")
    (root / ".claude").mkdir()
    (root / ".claude" / "CLAUDE.md").symlink_to("../CLAUDE.md")
    checkout = si.locate(root)
    assert si.find_instruction_files(checkout) == [root / "CLAUDE.md"]
    assert si.instruction_groups(checkout) == [[root / "CLAUDE.md", root / ".claude" / "CLAUDE.md"]]


def test_git_paths_are_absolute_without_path_format(tmp_path: Path) -> None:
    """--path-format needs git 2.31. Older git must still locate the main checkout, so relative output is resolved."""
    root = repo(tmp_path)
    assert si.git_path(root, "--git-dir") == root / ".git"
    assert si.git_path(root / "pkg", "--git-common-dir") == root / ".git"
