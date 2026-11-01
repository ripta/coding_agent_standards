"""Tests for standards_imports.py. Run: uv run --with pytest pytest claude/scripts"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
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


# -- hook paths -----------------------------------------------------------------------------

HOME = Path("/home/u")
LINK_HOOKS = "$HOME/.claude/coding-standards-current/hooks/a.sh"
HOOK_PATHS = [
    ("$HOME spelling", '"$HOME/projects/coding_agent_standards/claude/hooks/a.sh" --x', [LINK_HOOKS]),
    ("braced HOME", "${HOME}/projects/coding_agent_standards/claude/hooks/a.sh", [LINK_HOOKS]),
    ("tilde and symlink", "~/coding-standards/claude/hooks/a.sh", [LINK_HOOKS]),
    ("absolute home", "/home/u/projects/coding_agent_standards/claude/hooks/a.sh", [LINK_HOOKS]),
    ("mapped directory", "$HOME/coding-standards/practices/a.sh", ["$HOME/.claude/coding-standards-current/practices/a.sh"]),
    ("repo-only path", "$HOME/projects/coding_agent_standards/bin/a.sh", []),
    ("already on the link", LINK_HOOKS, []),
    ("another user's home", "/home/other/projects/coding_agent_standards/claude/hooks/a.sh", []),
]


@pytest.mark.parametrize(("name", "command", "expected"), HOOK_PATHS, ids=[c[0] for c in HOOK_PATHS])
def test_old_hook_paths_map_onto_the_link_only_for_plugin_files(name: str, command: str, expected: list) -> None:
    """A hook wired to the checkout leaks its working tree. Repo-only tools have no link path to suggest."""
    assert [new for _, new in si.old_hook_paths(command, HOME)] == expected


def test_a_hung_git_is_given_up_on(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A hung git must not burn the hook's whole 5 s budget and lose the warnings found so far."""
    fake = tmp_path / "bin"
    fake.mkdir()
    (fake / "git").write_text("#!/bin/sh\nsleep 3\n")
    (fake / "git").chmod(0o755)
    monkeypatch.setenv("PATH", f"{fake}:{os.environ['PATH']}")
    monkeypatch.setattr(si, "GIT_TIMEOUT", 0.2, raising=False)

    start = time.monotonic()
    checkout = si.locate(tmp_path)

    assert time.monotonic() - start < 1.5
    assert checkout.root == tmp_path.resolve()
    assert checkout.main_root is None


# -- check ----------------------------------------------------------------------------------

SNAP = {"profiles/p.md": "p\n", "rules/a.md": "a\n"}
GOOD = f"@{LINK}/profiles/p.md\n"
OLD = f"@{CHECKOUT}/claude/rules/a.md\n"

TAGS = [
    ("old-unresolved", "does not resolve in the plugin snapshot"),
    ("old", "imports the old standards path"),
    ("link-unresolved", "is not in the standards snapshot"),
    ("plain", "without a leading @"),
    ("no-import", "does not import the coding standards"),
    ("worktree", ".worktreeinclude"),
    ("approval", "has not approved external imports"),
    ("hook", "which is the checkout's working tree"),
    ("link", f"{LINK} "),
    ("notice-text", "This is a --plugin-dir session"),
]


def tag(level: str, text: str) -> str:
    """Name a result by its phrase, so a test states the exact set of warnings and an unknown text shows up whole."""
    for name, phrase in TAGS:
        if phrase in text and (name != "link" or text.startswith(LINK)):
            return f"{level}:{name}"
    return f"{level}:{text}"


class World:
    """A fake HOME, an installed snapshot, a --plugin-dir tree, a link, and a git project."""

    def __init__(self, tmp: Path) -> None:
        self.tmp = tmp.resolve()
        self.home = self.tmp / "home"
        self.installed = self.snap(self.home / "installed")
        self.dev = self.snap(self.tmp / "dev")
        self.link = self.home / ".claude" / "coding-standards-current"
        self.link.parent.mkdir(parents=True)
        self.project = repo(self.tmp)
        self.approve(True)

    def snap(self, path: Path) -> Path:
        for rel, text in SNAP.items():
            (path / rel).parent.mkdir(parents=True, exist_ok=True)
            (path / rel).write_text(text)
        return path

    def write(self, files: dict) -> None:
        for rel, text in files.items():
            path = self.project / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)

    def approve(self, value: object) -> None:
        config = self.home / ".claude.json"
        if value is None:
            config.unlink(missing_ok=True)
        elif value == "other-project":
            config.write_text(json.dumps({"projects": {str(self.tmp / "else"): {"hasClaudeMdExternalIncludesApproved": True}}}))
        else:
            config.write_text(json.dumps({"projects": {str(self.project): {"hasClaudeMdExternalIncludesApproved": value}}}))

    def check(self, session: str = "installed", cwd: Path | None = None) -> list:
        root = self.installed if session == "installed" else self.dev
        results = si.check(cwd or self.project, root, session, self.link, self.home, self.home / ".claude.json")
        return [tag(level, text) for level, text in results]


@pytest.fixture
def world(tmp_path: Path) -> World:
    return World(tmp_path)


PROJECT_CASES = [
    ("clean", {"CLAUDE.md": GOOD}, []),
    ("see line", {"CLAUDE.md": f"See @{LINK}/profiles/p.md\n"}, []),
    ("local file counts", {"CLAUDE.local.md": GOOD}, []),
    ("old path", {"CLAUDE.md": OLD}, ["warning:old"]),
    ("old path resolves only through the symlinks", {"CLAUDE.md": f"@{CHECKOUT}/languages/go.md\n"}, ["warning:old-unresolved"]),
    ("old path with no mapping", {"CLAUDE.md": f"@{CHECKOUT}/bugs/x.md\n"}, ["warning:old-unresolved"]),
    ("unresolved link path", {"CLAUDE.md": f"@{LINK}/rules/gone.md\n"}, ["warning:link-unresolved"]),
    ("plain text", {"CLAUDE.md": f"- {LINK}/profiles/p.md\n"}, ["warning:plain"]),
    ("plain text is not also no-import", {"CLAUDE.md": f"{CHECKOUT}/profiles/p.md\n"}, ["warning:plain"]),
    ("no import", {"CLAUDE.md": "Nothing here.\n"}, ["warning:no-import"]),
    ("no file", {}, ["warning:no-import"]),
    ("code span", {"CLAUDE.md": f"Write `{OLD.strip()}` to import.\n{GOOD}"}, []),
    ("fence", {"CLAUDE.md": f"```\n{OLD}```\n{GOOD}"}, []),
    ("prose naming the checkout", {"CLAUDE.md": f"Clone it to {CHECKOUT} first.\n{GOOD}"}, []),
    ("link target", {"CLAUDE.md": f"[docs]({CHECKOUT}/claude/rules/a.md)\n{GOOD}"}, []),
    ("link target alone is no import", {"CLAUDE.md": f"[docs]({LINK}/rules/a.md)\n"}, ["warning:no-import"]),
    ("hook path in prose", {"CLAUDE.md": f"Wire {CHECKOUT}/claude/hooks/block-zig-cache.sh by hand.\n{GOOD}"}, []),
    ("old and link problems both", {"CLAUDE.md": OLD + f"@{LINK}/rules/gone.md\n"}, ["warning:old", "warning:link-unresolved"]),
]


@pytest.mark.parametrize(("name", "files", "expected"), PROJECT_CASES, ids=[c[0] for c in PROJECT_CASES])
def test_project_imports(world: World, name: str, files: dict, expected: list) -> None:
    """Each import that loads nothing earns exactly its own warning, and code, prose and link targets earn none.

    An old path that resolves must not also be called unresolved, and one that does not must not
    be told it loads nothing today. It cannot prove the wording, which the full-text test does.
    """
    world.write(files)

    assert world.check() == expected


def test_a_parent_directorys_file_is_checked_from_a_subdirectory(world: World) -> None:
    """Claude Code loads every file up to the git root, so a stale import above the cwd still counts."""
    world.write({"CLAUDE.md": GOOD, "pkg/CLAUDE.md": OLD})

    assert world.check(cwd=world.project / "pkg") == ["warning:old"]


def test_warning_texts_name_the_file_the_lines_and_the_fix(world: World) -> None:
    """Catches a warning that does not say which file and lines to fix, or does not name /update-profile."""
    world.write({"CLAUDE.md": "intro\n" + OLD})
    (old,) = si.check(world.project, world.installed, "installed", world.link, world.home, world.home / ".claude.json")

    assert old == (
        "warning",
        f"{world.project}/CLAUDE.md imports the old standards path {CHECKOUT}/claude/rules/a.md (line 2). "
        "The path loads only while the checkout keeps its transition symlinks. Run /update-profile to point it at the plugin link.",
    )

    world.write({"CLAUDE.md": f"@{CHECKOUT}/languages/go.md\n"})
    (unresolved,) = si.check(world.project, world.installed, "installed", world.link, world.home, world.home / ".claude.json")

    assert unresolved == (
        "warning",
        f"{world.project}/CLAUDE.md imports the old standards path {CHECKOUT}/languages/go.md (line 1), which does not "
        "resolve in the plugin snapshot. It loads today only through the checkout's transition symlinks, and will load "
        "nothing once they go. Run /update-profile to rewrite what it can and report the rest.",
    )


def test_a_warning_lists_at_most_three_paths_and_lines(world: World) -> None:
    """Eleven stale imports must not print eleven paths into context at every session start."""
    lines = "".join(f"- @{CHECKOUT}/claude/rules/a{n}.md\n" for n in range(1, 6))
    world.write({"CLAUDE.md": lines})
    for n in range(1, 6):
        (world.installed / "rules" / f"a{n}.md").write_text("x\n")

    ((_, text),) = si.check(world.project, world.installed, "installed", world.link, world.home, world.home / ".claude.json")

    assert text.count("rules/a") == 3
    assert "and 2 more" in text
    assert "lines 1, 2, 3, and 2 more" in text


APPROVAL_CASES = [
    ("not approved", False, ["warning:approval"]),
    ("approved", True, []),
    ("project missing", "other-project", ["warning:approval"]),
    ("config missing", None, []),
]


@pytest.mark.parametrize(("name", "state", "expected"), APPROVAL_CASES, ids=[c[0] for c in APPROVAL_CASES])
def test_approval_covers_every_line_with_an_import(world: World, name: str, state: object, expected: list) -> None:
    """Most projects write `See @...`. The old check read only lines that began with @ and missed them."""
    world.write({"CLAUDE.md": f"See @{LINK}/profiles/p.md for the rules.\n"})
    world.approve(state)

    assert world.check() == expected


def test_a_config_that_is_not_json_is_not_an_answer(world: World) -> None:
    """A half-written ~/.claude.json must not make every project warn."""
    world.write({"CLAUDE.md": GOOD})
    (world.home / ".claude.json").write_text("{nope")

    assert world.check() == []


def test_no_approval_warning_without_an_import(world: World) -> None:
    """Plain text and link targets are not external imports, so approval is not what is wrong."""
    world.write({"CLAUDE.md": f"[a]({LINK}/profiles/p.md) and {LINK}/rules/a.md\n"})
    world.approve(False)

    assert world.check() == ["warning:plain"]


def settings(command: str) -> str:
    return json.dumps({"hooks": {"PreToolUse": [{"hooks": [{"type": "command", "command": command}]}]}})


@pytest.mark.parametrize("name", ["settings.json", "settings.local.json"])
def test_old_hook_paths_name_the_link_path(world: World, name: str) -> None:
    """A hook wired to the checkout runs unreleased code, and the warning must give the exact fix."""
    world.write({"CLAUDE.md": GOOD, f".claude/{name}": settings('"$HOME/projects/coding_agent_standards/claude/hooks/a.sh"')})

    ((level, text),) = si.check(world.project, world.installed, "installed", world.link, world.home, world.home / ".claude.json")

    assert level == "warning"
    assert text == (
        f"{world.project}/.claude/{name} runs $HOME/projects/coding_agent_standards/claude/hooks/a.sh, which is the "
        "checkout's working tree. Use $HOME/.claude/coding-standards-current/hooks/a.sh instead, so the command runs "
        "the installed plugin."
    )


def test_link_hook_paths_and_broken_settings_are_quiet(world: World) -> None:
    """A hook already on the link is right. A settings file that is not JSON is not this check's business."""
    world.write({"CLAUDE.md": GOOD, ".claude/settings.json": settings(LINK_HOOKS), ".claude/settings.local.json": "{nope"})

    assert world.check() == []


# -- sessions -------------------------------------------------------------------------------


def test_an_installed_session_resolves_against_the_plugin_root_not_the_link(world: World) -> None:
    """The link may still point at the old snapshot while link-current.sh repoints it in the same SessionStart."""
    old = world.tmp / "old"
    old.mkdir()
    world.link.symlink_to(old)
    world.write({"CLAUDE.md": GOOD})

    assert world.check() == []


def test_an_installed_session_never_checks_the_link(world: World) -> None:
    """link-current.sh runs beside the hook, so on a first session the link is legitimately absent."""
    world.write({"CLAUDE.md": GOOD})

    assert not world.link.exists() and not world.link.is_symlink()
    assert world.check() == []


@pytest.mark.parametrize("breaker", ["missing", "dangling", "file"])
def test_plugin_dir_reports_a_broken_link_first_and_resolves_nothing(world: World, breaker: str) -> None:
    """The user must not be sent to /update-profile for a link problem, and imports cannot be resolved without it."""
    if breaker == "dangling":
        world.link.symlink_to(world.tmp / "gone")
    elif breaker == "file":
        world.link.write_text("x")
    world.write({"CLAUDE.md": OLD + f"@{LINK}/rules/gone.md\n"})

    assert world.check("plugin-dir") == ["warning:link", "warning:old"]


def test_plugin_dir_resolves_against_the_links_target(world: World) -> None:
    """Under --plugin-dir the session's imports read the link, whatever the working tree holds."""
    linked = world.snap(world.tmp / "linked")
    world.link.symlink_to(linked)
    (world.dev / "rules" / "only-dev.md").write_text("x\n")
    (linked / "rules" / "only-link.md").write_text("x\n")
    world.write({"CLAUDE.md": f"@{LINK}/rules/only-dev.md\n@{LINK}/rules/only-link.md\n"})

    results = si.check(world.project, world.dev, "plugin-dir", world.link, world.home, world.home / ".claude.json")

    (text,) = [t for level, t in results if level == "warning"]
    assert "only-dev.md" in text and "only-link.md" not in text


NOTICE_CASES = [
    ("link differs, link import", "other", GOOD, ["notice:notice-text"]),
    ("link equals the working tree", "dev", GOOD, []),
    ("link differs, only an old import", "other", OLD, ["warning:old"]),
    ("link differs, no import", "other", "Nothing.\n", ["warning:no-import"]),
]


@pytest.mark.parametrize(("name", "target", "text", "expected"), NOTICE_CASES, ids=[c[0] for c in NOTICE_CASES])
def test_plugin_dir_notice_only_when_it_is_true(world: World, name: str, target: str, text: str, expected: list) -> None:
    """The notice says instructions come from the installed snapshot. Printing it when they do not misleads."""
    world.link.symlink_to(world.dev if target == "dev" else world.snap(world.tmp / "other"))
    world.write({"CLAUDE.md": text})

    assert world.check("plugin-dir") == expected


def test_the_notice_names_both_snapshots(world: World) -> None:
    """The reader must learn which tree the instructions come from and which the tools come from."""
    other = world.snap(world.tmp / "other")
    world.link.symlink_to(other)
    world.write({"CLAUDE.md": GOOD})

    ((level, text),) = si.check(world.project, world.dev, "plugin-dir", world.link, world.home, world.home / ".claude.json")

    assert level == "notice"
    assert str(other) in text and str(world.dev) in text


def test_an_installed_session_never_gets_the_notice(world: World) -> None:
    """Only a --plugin-dir session can disagree with its own link."""
    world.link.symlink_to(world.snap(world.tmp / "other"))
    world.write({"CLAUDE.md": GOOD})

    assert world.check() == []


def test_check_command_prints_prefixed_lines_and_nothing_when_clean(world: World, capsys: pytest.CaptureFixture) -> None:
    """check-setup.sh splits these lines by prefix, so the prefixes and one line per result are a contract."""
    args = ["check", "--cwd", str(world.project), "--plugin-root", str(world.installed), "--session", "installed", "--home", str(world.home)]

    world.write({"CLAUDE.md": GOOD})
    assert si.main(args) == 0
    assert capsys.readouterr().out == ""

    world.write({"CLAUDE.md": "none\n"})
    assert si.main(args) == 0
    out = capsys.readouterr().out
    assert out.startswith("warning: This project does not import") and out.count("\n") == 1
