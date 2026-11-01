"""Tests for update_profile.py. Run: uv run --with pytest pytest claude/scripts"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import update_profile

CLAUDE = Path(__file__).resolve().parents[1]
LINK = "~/.claude/coding-standards-current"
CHECKOUT = "~/projects/coding_agent_standards"

SNAPSHOT = {
    "profiles/baseline.md": f"# Baseline\n\n@{LINK}/rules/commit-style.md\n@{LINK}/practices/testing.md\n",
    "profiles/go-service.md": f"@../profiles/baseline.md\n@../languages/go.md\n@{LINK}/practices/security.md\n",
    "profiles/python-project.md": "@../profiles/baseline.md\n@../languages/python.md\n",
    "profiles/oss-contrib.md": f"@{LINK}/rules/pr-style.md\n",
    "rules/commit-style.md": "commit\n",
    "rules/pr-style.md": "pr\n",
    "practices/testing.md": "testing\n",
    "practices/security.md": "security\n",
    "languages/go.md": "go\n",
    "languages/python.md": "python\n",
    "project-management/glossary.md": "glossary\n",
    "knowledge/wiki.md": "wiki\n",
}


def git(cwd: Path, *args: str) -> None:
    env = {**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null"}
    config = ["-c", "user.name=t", "-c", "user.email=t@example.com", "-c", "commit.gpgsign=false"]
    subprocess.run(["git", *config, *args], cwd=cwd, env=env, check=True, capture_output=True)


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture) -> SimpleNamespace:
    """A fake HOME whose link points at a synthetic snapshot, and a git project."""
    tmp = tmp_path.resolve()
    home = tmp / "home"
    snap = tmp / "snapshot"
    for rel, text in SNAPSHOT.items():
        (snap / rel).parent.mkdir(parents=True, exist_ok=True)
        (snap / rel).write_text(text)
    (home / ".claude").mkdir(parents=True)
    (home / ".claude" / "coding-standards-current").symlink_to(snap)
    monkeypatch.setenv("HOME", str(home))

    project = tmp / "project"
    (project / "sub").mkdir(parents=True)
    git(project, "init", "-q")
    git(project, "commit", "-q", "--allow-empty", "-m", "init")

    def run(*argv: str, cwd: Path = project) -> tuple:
        status = update_profile.main([argv[0], *argv[1:], "--cwd", str(cwd)])
        out = capsys.readouterr()
        return status, (json.loads(out.out) if out.out.strip() else None), out.err

    return SimpleNamespace(tmp=tmp, home=home, snapshot=snap, project=project, run=run, link=home / ".claude" / "coding-standards-current")


def imp(rel: str) -> str:
    return f"@{LINK}/{rel}"


def edits(result: dict) -> list:
    return [(e["action"], e["before"], e["after"]) for e in result["edits"]]


# -- the profile import ---------------------------------------------------------------------


def test_fresh_project_gets_a_new_claude_md(env: SimpleNamespace) -> None:
    """A project with no instruction file must get one, and the plan must say the target is a default."""
    status, plan, _ = env.run("plan", "go-service")
    assert status == 0
    assert plan["target"] is None
    assert plan["default_target"] == str(env.project / "CLAUDE.md")
    assert plan["questions"] == {"target": True, "mode": False, "per_file": False}

    status, result, _ = env.run("apply", "go-service")
    assert status == 0
    assert (env.project / "CLAUDE.md").read_text() == imp("profiles/go-service.md") + "\n"
    assert result["written"] == [str(env.project / "CLAUDE.md")]


def test_oss_contrib_defaults_to_the_local_file(env: SimpleNamespace) -> None:
    """oss-contrib is meant to stay out of the upstream repo, so its default target is CLAUDE.local.md."""
    env.run("apply", "oss-contrib")
    assert (env.project / "CLAUDE.local.md").exists()
    assert not (env.project / "CLAUDE.md").exists()


def test_the_file_that_already_imports_the_standards_is_the_target(env: SimpleNamespace) -> None:
    """Adding the import to an unrelated instruction file would leave two files importing standards."""
    (env.project / "CLAUDE.md").write_text("# Project\n\nNotes.\n")
    (env.project / "CLAUDE.local.md").write_text(imp("rules/pr-style.md") + "\n")
    _, plan, _ = env.run("plan", "oss-contrib")
    assert plan["target"] == str(env.project / "CLAUDE.local.md")
    assert plan["questions"]["target"] is False


def test_apply_appends_after_the_last_import_and_is_idempotent(env: SimpleNamespace) -> None:
    """A second run must change nothing, or every run would stack another import."""
    (env.project / "CLAUDE.md").write_text(f"# Project\n\n{imp('rules/pr-style.md')}\n\nTail.\n")
    env.run("apply", "go-service", "--per-file", "keep")
    text = (env.project / "CLAUDE.md").read_text()
    assert text == f"# Project\n\n{imp('rules/pr-style.md')}\n{imp('profiles/go-service.md')}\n\nTail.\n"

    status, result, _ = env.run("apply", "go-service", "--per-file", "keep")
    assert result["written"] == []
    assert (env.project / "CLAUDE.md").read_text() == text


def test_appending_to_a_file_with_no_imports_keeps_a_blank_line(env: SimpleNamespace) -> None:
    """The import must not butt against the last paragraph, and a missing final newline must not glue lines."""
    (env.project / "CLAUDE.md").write_text("# Project\n\nNotes.")
    env.run("apply", "go-service")
    assert (env.project / "CLAUDE.md").read_text() == f"# Project\n\nNotes.\n\n{imp('profiles/go-service.md')}\n"


def test_crlf_line_endings_survive(env: SimpleNamespace) -> None:
    """Rewriting a CRLF file with LF endings would show up as a whole-file diff."""
    (env.project / "CLAUDE.md").write_bytes(f"# P\r\n\r\n@{CHECKOUT}/claude/rules/pr-style.md\r\n".encode())
    env.run("apply", "go-service", "--per-file", "keep")
    assert (env.project / "CLAUDE.md").read_bytes() == (
        f"# P\r\n\r\n{imp('rules/pr-style.md')}\r\n{imp('profiles/go-service.md')}\r\n".encode()
    )


MODES = [
    ("replace", f"# P\n\n{imp('profiles/python-project.md')}\n", f"# P\n\n{imp('profiles/go-service.md')}\n"),
    (
        "keep",
        f"# P\n\n{imp('profiles/python-project.md')}\n",
        f"# P\n\n{imp('profiles/python-project.md')}\n{imp('profiles/go-service.md')}\n",
    ),
]


@pytest.mark.parametrize(("mode", "before", "after"), MODES)
def test_a_different_profile_is_replaced_or_kept_beside_the_new_one(
    env: SimpleNamespace, mode: str, before: str, after: str
) -> None:
    """Switching profiles and stacking them are different intents, and the user chooses between them."""
    (env.project / "CLAUDE.md").write_text(before)
    _, plan, _ = env.run("plan", "go-service")
    assert plan["questions"]["mode"] is True
    assert [i["profile"] for i in plan["different_profile_imports"]] == ["python-project"]
    assert {v["mode"] for v in plan["variants"]} == {"keep", "replace"}

    env.run("apply", "go-service", "--mode", mode)
    assert (env.project / "CLAUDE.md").read_text() == after


def test_replace_drops_extra_profiles_and_swaps_inside_prose(env: SimpleNamespace) -> None:
    """Replace must never delete prose. A different profile inside a prose line is swapped in place and flagged."""
    (env.project / "CLAUDE.md").write_text(
        f"Uses @{CHECKOUT}/profiles/python-project.md for style.\n{imp('profiles/oss-contrib.md')}\n"
    )
    _, result, _ = env.run("apply", "go-service", "--mode", "replace")
    assert (env.project / "CLAUDE.md").read_text() == f"Uses {imp('profiles/go-service.md')} for style.\n"
    assert [f["line"] for f in result["flagged_prose"]] == [1]


def test_stacking_profiles_adds_each(env: SimpleNamespace) -> None:
    """Several profiles on the command line are all added, as elastane needs two."""
    env.run("apply", "go-service", "python-project")
    assert (env.project / "CLAUDE.md").read_text() == (
        f"{imp('profiles/go-service.md')}\n{imp('profiles/python-project.md')}\n"
    )


# -- old paths ------------------------------------------------------------------------------

OLD_PATHS = [
    (f"{CHECKOUT}/claude/rules/pr-style.md", "rules/pr-style.md"),
    ("~/coding-standards/claude/rules/pr-style.md", "rules/pr-style.md"),
    (f"{CHECKOUT}/practices/security.md", "practices/security.md"),
    (f"{CHECKOUT}/languages/go.md", "languages/go.md"),
    (f"{CHECKOUT}/profiles/oss-contrib.md", "profiles/oss-contrib.md"),
    (f"{CHECKOUT}/project-management/glossary.md", "project-management/glossary.md"),
    (f"{CHECKOUT}/knowledge/wiki.md", "knowledge/wiki.md"),
    ("~/coding-standards/practices/security.md", "practices/security.md"),
    ("~/coding-standards/languages/go.md", "languages/go.md"),
    ("~/coding-standards/profiles/oss-contrib.md", "profiles/oss-contrib.md"),
    ("~/coding-standards/project-management/glossary.md", "project-management/glossary.md"),
    ("~/coding-standards/knowledge/wiki.md", "knowledge/wiki.md"),
]


@pytest.mark.parametrize(("old", "rel"), OLD_PATHS)
def test_each_old_path_form_is_rewritten_onto_the_link(env: SimpleNamespace, old: str, rel: str) -> None:
    """A form the mapping misses keeps loading nothing after the checkout stops being a source."""
    (env.project / "CLAUDE.md").write_text(f"@{old}\n")
    _, plan, _ = env.run("plan", "python-project")
    assert [o["rel"] for o in plan["old_paths"]] == [rel]

    env.run("apply", "python-project", "--per-file", "keep")
    assert (env.project / "CLAUDE.md").read_text() == f"{imp(rel)}\n{imp('profiles/python-project.md')}\n"


def test_a_plain_text_path_becomes_an_import(env: SimpleNamespace) -> None:
    """A path with no @ loads nothing. The plan lists it, and the import it becomes counts as the profile."""
    (env.project / "CLAUDE.md").write_text(f"- {CHECKOUT}/profiles/python-project.md\n")
    _, plan, _ = env.run("plan", "python-project")
    assert [p["rel"] for p in plan["plain_text_paths"]] == ["profiles/python-project.md"]

    env.run("apply", "python-project")
    assert (env.project / "CLAUDE.md").read_text() == f"- {imp('profiles/python-project.md')}\n"


def test_code_spans_and_fences_are_left_alone(env: SimpleNamespace) -> None:
    """Claude Code expands no import there, so rewriting one would change documentation."""
    text = f"Use `@{CHECKOUT}/claude/rules/pr-style.md` like this:\n\n```\n@{CHECKOUT}/claude/rules/pr-style.md\n```\n"
    (env.project / "CLAUDE.md").write_text(text)
    env.run("apply", "python-project")
    assert (env.project / "CLAUDE.md").read_text() == text + f"\n{imp('profiles/python-project.md')}\n"


def test_a_parent_directorys_file_is_rewritten_too(env: SimpleNamespace) -> None:
    """Claude Code loads parents up to the git root, so an old import there is part of the project's state."""
    (env.project / "CLAUDE.md").write_text(f"@{CHECKOUT}/claude/rules/pr-style.md\n")
    (env.project / "sub" / "CLAUDE.md").write_text("# Sub\n")
    (env.tmp / "CLAUDE.md").write_text(f"@{CHECKOUT}/claude/rules/pr-style.md\n")

    _, plan, _ = env.run("plan", "oss-contrib", cwd=env.project / "sub")
    assert plan["target"] == str(env.project / "CLAUDE.md")

    env.run("apply", "oss-contrib", cwd=env.project / "sub")
    assert (env.project / "CLAUDE.md").read_text() == f"{imp('profiles/oss-contrib.md')}\n"
    assert (env.tmp / "CLAUDE.md").read_text() == f"@{CHECKOUT}/claude/rules/pr-style.md\n"


# -- skipped imports ------------------------------------------------------------------------

SKIPS = [
    ("old path mapped to a file the snapshot lacks", f"@{CHECKOUT}/claude/rules/nope.md", "nope.md is not in the snapshot"),
    ("link path the snapshot lacks", imp("rules/nope.md"), "nope.md is not in the snapshot"),
    ("old path with no mapping", f"@{CHECKOUT}/bugs/a.md", "no mapping"),
]


@pytest.mark.parametrize(("name", "line", "reason"), SKIPS, ids=[s[0] for s in SKIPS])
def test_an_import_that_does_not_resolve_is_skipped_and_the_rest_applies(
    env: SimpleNamespace, name: str, line: str, reason: str
) -> None:
    """Writing an import that loads nothing hides the failure. The line stays, and the other edits still land."""
    other = f"@{CHECKOUT}/claude/rules/pr-style.md"
    (env.project / "CLAUDE.md").write_text(f"{line}\n{other}\n")
    _, result, _ = env.run("apply", "python-project", "--per-file", "keep")
    assert (env.project / "CLAUDE.md").read_text() == (
        f"{line}\n{imp('rules/pr-style.md')}\n{imp('profiles/python-project.md')}\n"
    )
    assert [reason in s["reason"] for s in result["skipped"]] == [True]
    assert result["skipped"][0]["line"] == 1


# -- per-file lists -------------------------------------------------------------------------


def test_a_per_file_list_collapses_only_what_the_profile_includes(env: SimpleNamespace) -> None:
    """Dropping a file the profile lacks would stop it loading. It is rewritten as its own import instead."""
    (env.project / "CLAUDE.md").write_text(
        "# Standards\n\n"
        f"- @{CHECKOUT}/claude/rules/commit-style.md\n"
        f"- See @{CHECKOUT}/practices/testing.md\n"
        f"- @{CHECKOUT}/claude/rules/pr-style.md\n"
        f"- @{CHECKOUT}/claude/rules/nope.md\n"
    )
    _, plan, _ = env.run("plan", "python-project")
    assert plan["questions"]["per_file"] is True
    assert {v["per_file"] for v in plan["variants"]} == {"collapse", "keep"}

    _, result, _ = env.run("apply", "python-project")
    assert (env.project / "CLAUDE.md").read_text() == (
        "# Standards\n\n"
        f"- {imp('rules/pr-style.md')}\n"
        f"- @{CHECKOUT}/claude/rules/nope.md\n"
        f"{imp('profiles/python-project.md')}\n"
    )
    removed = [e["before"] for e in result["edits"] if e["action"] == "remove"]
    assert removed == [f"- @{CHECKOUT}/claude/rules/commit-style.md", f"- See @{CHECKOUT}/practices/testing.md"]
    assert [s["line"] for s in result["skipped"]] == [6]


def test_keeping_the_per_file_list_only_rewrites_it(env: SimpleNamespace) -> None:
    """The user may want the list as it is. Keep must rewrite the paths and remove nothing."""
    (env.project / "CLAUDE.md").write_text(f"- @{CHECKOUT}/claude/rules/commit-style.md\n")
    env.run("apply", "python-project", "--per-file", "keep")
    assert (env.project / "CLAUDE.md").read_text() == (
        f"- {imp('rules/commit-style.md')}\n{imp('profiles/python-project.md')}\n"
    )


def test_imports_inside_prose_are_rewritten_in_place_and_flagged(env: SimpleNamespace) -> None:
    """A prose line is the user's words, so it is kept even when its import is redundant, and flagged for hand trimming."""
    prose = f"This project follows the standards defined in @{CHECKOUT}/claude/rules/commit-style.md and more."
    (env.project / "CLAUDE.md").write_text(prose + "\n")
    _, result, _ = env.run("apply", "python-project")
    assert (env.project / "CLAUDE.md").read_text() == (
        f"This project follows the standards defined in {imp('rules/commit-style.md')} and more.\n"
        f"{imp('profiles/python-project.md')}\n"
    )
    assert [f["line"] for f in result["flagged_prose"]] == [1]
    assert [e["action"] for e in result["edits"]] == ["replace", "insert"]


def test_a_list_made_only_of_prose_lines_loses_nothing(env: SimpleNamespace) -> None:
    """A list where every import sits in prose has nothing safe to remove."""
    lines = [
        f"Follow @{CHECKOUT}/claude/rules/commit-style.md closely.",
        f"Also read @{CHECKOUT}/practices/testing.md before tests.",
    ]
    (env.project / "CLAUDE.md").write_text("\n".join(lines) + "\n")
    _, result, _ = env.run("apply", "python-project")
    assert [e["action"] for e in result["edits"]] == ["replace", "replace", "insert"]
    assert len(result["flagged_prose"]) == 2


# -- whole-run failures ---------------------------------------------------------------------


def test_an_unknown_profile_stops_the_run_and_lists_the_profiles(env: SimpleNamespace) -> None:
    """A typo must not create a dead import. The error lists what exists."""
    status, result, err = env.run("apply", "go-servce")
    assert (status, result) == (1, None)
    assert "unknown profile 'go-servce'" in err
    assert "go-service, oss-contrib, python-project" in err
    assert not (env.project / "CLAUDE.md").exists()


def break_missing(env: SimpleNamespace) -> None:
    env.link.unlink()


def break_dangling(env: SimpleNamespace) -> None:
    env.link.unlink()
    env.link.symlink_to(env.tmp / "gone")


def break_no_profiles(env: SimpleNamespace) -> None:
    for path in sorted((env.snapshot / "profiles").iterdir()):
        path.unlink()
    (env.snapshot / "profiles").rmdir()


LINK_FAILURES = [
    (break_missing, "does not exist"),
    (break_dangling, "no longer exists"),
    (break_no_profiles, "has no profiles/"),
]


@pytest.mark.parametrize(("breaker", "message"), LINK_FAILURES, ids=lambda v: getattr(v, "__name__", str(v)[:12]))
@pytest.mark.parametrize("command", ["plan", "apply"])
def test_a_missing_or_unusable_link_stops_the_run(env: SimpleNamespace, breaker, message: str, command: str) -> None:
    """A migrated project must never be written when the link loads nothing."""
    (env.project / "CLAUDE.md").write_text(f"@{CHECKOUT}/claude/rules/pr-style.md\n")
    breaker(env)
    status, result, err = env.run(command, "go-service")
    assert (status, result) == (1, None)
    assert message in err
    assert (env.project / "CLAUDE.md").read_text() == f"@{CHECKOUT}/claude/rules/pr-style.md\n"


def test_json_flag_is_accepted(env: SimpleNamespace) -> None:
    """Callers pass --json by habit, as they do to proposals.py."""
    status, plan, _ = env.run("plan", "go-service", "--json")
    assert status == 0 and plan["profiles"] == ["go-service"]


# -- linked worktrees -----------------------------------------------------------------------


@pytest.fixture
def tree(env: SimpleNamespace) -> Path:
    path = env.tmp / "tree"
    git(env.project, "worktree", "add", "-q", str(path), "-b", "tree")
    return path


OLD = f"@{CHECKOUT}/claude/rules/pr-style.md\n"


def test_a_worktree_with_its_own_local_file_edits_it_and_the_main_copy(env: SimpleNamespace, tree: Path) -> None:
    """Later worktrees copy the main checkout's file, so it has to get the change too."""
    (env.project / "CLAUDE.local.md").write_text(OLD)
    (tree / "CLAUDE.local.md").write_text(OLD)
    _, plan, _ = env.run("plan", "oss-contrib", cwd=tree)
    assert plan["target"] == str(tree / "CLAUDE.local.md")
    assert plan["main_checkout"] == str(env.project)

    _, result, _ = env.run("apply", "oss-contrib", cwd=tree)
    expected = f"{imp('profiles/oss-contrib.md')}\n"
    assert (tree / "CLAUDE.local.md").read_text() == expected
    assert (env.project / "CLAUDE.local.md").read_text() == expected
    assert sorted(result["written"]) == sorted([str(tree / "CLAUDE.local.md"), str(env.project / "CLAUDE.local.md")])
    assert result["notes"] == []


def test_a_worktree_without_a_local_file_edits_the_main_copy_and_says_to_copy_it(
    env: SimpleNamespace, tree: Path
) -> None:
    """The worktree loads no CLAUDE.local.md of the main checkout, so the user must be told to copy it in."""
    (env.project / "CLAUDE.local.md").write_text(OLD)
    _, result, _ = env.run("apply", "go-service", cwd=tree)
    assert (env.project / "CLAUDE.local.md").read_text() == (
        f"{imp('rules/pr-style.md')}\n{imp('profiles/go-service.md')}\n"
    )
    assert not (tree / "CLAUDE.local.md").exists()
    assert len(result["notes"]) == 1
    assert ".worktreeinclude" in result["notes"][0]


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores file modes")
def test_an_unwritable_main_copy_stops_the_whole_apply(env: SimpleNamespace, tree: Path) -> None:
    """A half-applied change would leave the worktree and the main checkout disagreeing."""
    (env.project / "CLAUDE.local.md").write_text(OLD)
    (tree / "CLAUDE.local.md").write_text(OLD)
    (env.project / "CLAUDE.local.md").chmod(0o444)

    status, result, _ = env.run("apply", "oss-contrib", cwd=tree)
    assert status == update_profile.EXIT_UNWRITABLE
    assert result["applied"] is False
    assert [u["path"] for u in result["unwritable"]] == [str(env.project / "CLAUDE.local.md")]
    assert (tree / "CLAUDE.local.md").read_text() == OLD
    assert (env.project / "CLAUDE.local.md").read_text() == OLD


# -- external imports -----------------------------------------------------------------------

APPROVALS = [
    (None, None),
    ({}, False),
    ({"hasClaudeMdExternalIncludesApproved": False}, False),
    ({"hasClaudeMdExternalIncludesApproved": True}, True),
]


@pytest.mark.parametrize(("entry", "approved"), APPROVALS)
def test_apply_reports_approval_and_never_grants_it(env: SimpleNamespace, entry: object, approved: object) -> None:
    """Only the user can approve external imports. The script reads the state and leaves the file alone."""
    config = env.home / ".claude.json"
    if entry is not None:
        config.write_text(json.dumps({"projects": {str(env.project): entry}}))
    before = config.read_text() if config.exists() else None

    _, result, _ = env.run("apply", "go-service")
    assert result["external_imports"]["approved"] is approved
    assert (config.read_text() if config.exists() else None) == before


# -- the real profiles ----------------------------------------------------------------------


def test_every_real_profile_can_be_added(env: SimpleNamespace) -> None:
    """The link must resolve every profile the repo ships, or /update-profile would refuse a real one."""
    env.link.unlink()
    env.link.symlink_to(CLAUDE)
    names = sorted(p.stem for p in (CLAUDE / "profiles").glob("*.md"))
    status, plan, _ = env.run("plan", *names)
    assert status == 0
    assert plan["variants"][0]["skipped"] == []


# -- review fixes ---------------------------------------------------------------------------


def test_two_names_for_one_file_are_edited_once(env: SimpleNamespace) -> None:
    """Both aliases were processed from the same text and the later write erased the profile import."""
    (env.project / "CLAUDE.md").write_text(f"@{CHECKOUT}/claude/rules/pr-style.md\n")
    (env.project / ".claude").mkdir()
    (env.project / ".claude" / "CLAUDE.md").symlink_to("../CLAUDE.md")

    _, plan, _ = env.run("plan", "oss-contrib")
    assert len(plan["instruction_files"]) == 1
    assert plan["instruction_files"][0]["aliases"] == [str(env.project / ".claude" / "CLAUDE.md")]

    _, result, _ = env.run("apply", "oss-contrib", "--per-file", "keep")
    assert result["written"] == [str(env.project / "CLAUDE.md")]
    assert (env.project / "CLAUDE.md").read_text() == f"{imp('rules/pr-style.md')}\n{imp('profiles/oss-contrib.md')}\n"
    assert (env.project / ".claude" / "CLAUDE.md").is_symlink()


def test_a_symlinked_target_stays_a_symlink(env: SimpleNamespace) -> None:
    """Replacing the link with a regular file would detach the project from the file it shares."""
    real = env.tmp / "shared.md"
    real.write_text("# Shared\n")
    (env.project / "CLAUDE.md").symlink_to(real)
    env.run("apply", "oss-contrib", "--target", "CLAUDE.md")
    assert (env.project / "CLAUDE.md").is_symlink()
    assert real.read_text() == f"# Shared\n\n{imp('profiles/oss-contrib.md')}\n"


LINK_TARGETS = [
    ("old target moves onto the link", f"See [rules]({CHECKOUT}/claude/rules/pr-style.md).", f"See [rules]({LINK}/rules/pr-style.md)."),
    ("link target is untouched", f"See [rules]({LINK}/rules/pr-style.md).", f"See [rules]({LINK}/rules/pr-style.md)."),
    ("reference definition", f"[r]: {CHECKOUT}/claude/rules/pr-style.md", f"[r]: {LINK}/rules/pr-style.md"),
]


@pytest.mark.parametrize(("name", "before", "after"), LINK_TARGETS, ids=[c[0] for c in LINK_TARGETS])
def test_a_markdown_link_target_is_never_made_an_import(env: SimpleNamespace, name: str, before: str, after: str) -> None:
    """Writing @ into a link target breaks the link, and the target is not an import to begin with."""
    (env.project / "CLAUDE.md").write_text(before + "\n")
    _, plan, _ = env.run("plan", "python-project")
    assert plan["plain_text_paths"] == []
    _, result, _ = env.run("apply", "python-project")
    assert (env.project / "CLAUDE.md").read_text() == f"{after}\n\n{imp('profiles/python-project.md')}\n"
    assert result["flagged_prose"] == []


def test_a_missing_target_directory_is_a_usage_error(env: SimpleNamespace) -> None:
    """Retrying a missing directory with the sandbox off cannot help, so it must not exit 3."""
    status, result, err = env.run("apply", "go-service", "--target", "nope/CLAUDE.md")
    assert (status, result) == (1, None)
    assert "nope" in err and "does not exist" in err


def test_target_override_beats_the_file_that_imports_the_standards(env: SimpleNamespace) -> None:
    """The user's answer to the target question must win over detection."""
    (env.project / "CLAUDE.md").write_text(imp("rules/pr-style.md") + "\n")
    _, result, _ = env.run("apply", "oss-contrib", "--target", "sub/CLAUDE.md")
    assert result["target"] == str(env.project / "sub" / "CLAUDE.md")
    assert (env.project / "sub" / "CLAUDE.md").read_text() == imp("profiles/oss-contrib.md") + "\n"
    assert (env.project / "CLAUDE.md").read_text() == imp("rules/pr-style.md") + "\n"


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores file modes")
def test_a_new_file_in_an_unwritable_directory_writes_nothing(env: SimpleNamespace) -> None:
    """Creating a file needs the directory, so the probe must check it before anything is written."""
    (env.project / "CLAUDE.md").write_text(f"@{CHECKOUT}/claude/rules/pr-style.md\n")
    (env.project / "sub").chmod(0o555)
    try:
        status, result, _ = env.run("apply", "oss-contrib", "--target", "sub/CLAUDE.md")
    finally:
        (env.project / "sub").chmod(0o755)
    assert status == update_profile.EXIT_UNWRITABLE
    assert [u["path"] for u in result["unwritable"]] == [str(env.project / "sub" / "CLAUDE.md")]
    assert (env.project / "CLAUDE.md").read_text() == f"@{CHECKOUT}/claude/rules/pr-style.md\n"


def test_a_failed_write_leaves_the_original_intact(env: SimpleNamespace, monkeypatch: pytest.MonkeyPatch) -> None:
    """Truncate-then-write loses the user's file on a crash. The write must go through a temp file and a rename."""
    original = "# Project\n\nNotes.\n"
    (env.project / "CLAUDE.md").write_text(original)

    def boom(*args: object) -> None:
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(update_profile.os, "replace", boom)
    status, result, err = env.run("apply", "go-service")
    assert (status, result) == (1, None)
    assert "No space left" in err
    assert (env.project / "CLAUDE.md").read_text() == original
    assert sorted(p.name for p in env.project.iterdir() if p.name != ".git") == ["CLAUDE.md", "sub"]
