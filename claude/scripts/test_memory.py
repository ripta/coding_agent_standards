"""Tests for memory.py. Run: uv run --with pytest pytest claude/scripts"""

from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import memory

TODAY = dt.date(2026, 12, 1)


def _memory(directory: Path, name: str, body: str, front: str = "type: feedback", index_hook: str | None = None) -> Path:
    path = directory / f"{name}.md"
    path.write_text(f"---\nname: {name}\ndescription: test\n{front}\n---\n\n{body}")
    if index_hook is not None:
        with (directory / "MEMORY.md").open("a") as handle:
            handle.write(f"- [{name}]({name}.md) — {index_hook}\n")
    return path


def _lesson(tier: str, instances: list[str], home: str = 'CLAUDE.md "Committing"', extra: str = "") -> str:
    lines = "\n".join(instances)
    return f"Tier: {tier}\nHome: {home}\nScope: test scope\n{extra}\nThe lesson.\n\n## Instances\n\n{lines}\n"


@pytest.fixture
def root(tmp_path: Path) -> Path:
    root = tmp_path / "projects"
    (root / "-proj" / "memory").mkdir(parents=True)
    return root


def _report(root: Path, since: dt.date | None = None) -> dict:
    return memory.sweep(root, TODAY, since, record=False)


def _one(report: dict, name: str) -> dict:
    for directory in report["directories"]:
        for item in directory["memories"]:
            if item["file"] == f"{name}.md":
                return item
    raise AssertionError(f"{name} not in report")


def test_observation_becomes_ready_only_on_three_distinct_counting_days(root: Path) -> None:
    """Catches counting repeats within one day, or `case` instances, toward a pattern."""
    mem = root / "-proj" / "memory"
    _memory(
        mem,
        "same-day",
        _lesson(
            "observation",
            [
                "- 2026-11-20 correction (a): one",
                "- 2026-11-20 correction (a): two",
                "- 2026-11-21 confirmation (b): three",
                "- 2026-11-22 case (c): applied",
            ],
        ),
        index_hook="(observation; test) hook",
    )
    _memory(
        mem,
        "three-days",
        _lesson(
            "observation",
            [
                "- 2026-11-20 correction (a): one",
                "- 2026-11-21 correction (a): two",
                "- 2026-11-22 confirmation (b): three",
            ],
        ),
        index_hook="(observation; test) hook",
    )

    report = _report(root)

    assert "ready_pattern" not in _one(report, "same-day")["status"]
    assert _one(report, "same-day")["counting_days"] == ["2026-11-20", "2026-11-21"]
    assert "ready_pattern" in _one(report, "three-days")["status"]


def test_only_instances_after_the_latest_contradiction_count(root: Path) -> None:
    """Catches a contradiction that fails to restart the count toward a pattern."""
    mem = root / "-proj" / "memory"
    _memory(
        mem,
        "contradicted",
        _lesson(
            "observation",
            [
                "- 2026-11-10 correction (a): one",
                "- 2026-11-11 correction (a): two",
                "- 2026-11-12 correction (a): three",
                "- 2026-11-13 contradiction (a): user went the other way",
                "- 2026-11-14 correction (a): four",
            ],
        ),
        index_hook="(observation; test) hook",
    )

    item = _one(_report(root), "contradicted")

    assert item["counting_days"] == ["2026-11-14"]
    assert "ready_pattern" not in item["status"]


def test_contradicted_is_bounded_by_the_last_sweep(root: Path) -> None:
    """Catches a contradiction re-reported every week, or one hidden before any sweep ran."""
    mem = root / "-proj" / "memory"
    _memory(
        mem,
        "c",
        _lesson("observation", ["- 2026-11-13 contradiction (a): no"]),
        index_hook="(observation; test) hook",
    )

    assert "contradicted" in _one(_report(root, since=None), "c")["status"]
    assert "contradicted" in _one(_report(root, since=dt.date(2026, 11, 12)), "c")["status"]
    assert "contradicted" not in _one(_report(root, since=dt.date(2026, 11, 13)), "c")["status"]


def test_expiry_counts_any_instance_including_case(root: Path) -> None:
    """Catches the starvation bug: an obeyed memory, renewed only by `case`, must not expire."""
    mem = root / "-proj" / "memory"
    _memory(
        mem,
        "stale",
        _lesson("observation", ["- 2026-10-01 correction (a): one"]),
        index_hook="(observation; test) hook",
    )
    _memory(
        mem,
        "obeyed",
        _lesson("observation", ["- 2026-09-01 correction (a): one", "- 2026-11-30 case (b): applied"]),
        index_hook="(observation; test) hook",
    )

    report = _report(root)

    assert "expired" in _one(report, "stale")["status"]
    assert "expired" not in _one(report, "obeyed")["status"]


def test_an_observation_with_no_instances_starts_its_clock_at_modified(root: Path) -> None:
    """Catches a migrated memory with no instances that never expires, or expires at once."""
    mem = root / "-proj" / "memory"
    _memory(mem, "old", _lesson("observation", []), front="type: feedback\nmodified: 2026-09-01T00:00:00Z",
            index_hook="(observation; test) hook")
    _memory(mem, "fresh", _lesson("observation", []), front="type: feedback\nmodified: 2026-11-20T00:00:00Z",
            index_hook="(observation; test) hook")

    report = _report(root)

    assert "expired" in _one(report, "old")["status"]
    assert "expired" not in _one(report, "fresh")["status"]
    assert "no instances" in _one(report, "fresh")["problems"]


def test_facts_and_patterns_never_expire_with_silence(root: Path) -> None:
    """Catches silence decay leaking past observations."""
    mem = root / "-proj" / "memory"
    _memory(mem, "fact", "Tier: fact\n\nA pointer.\n", front="type: reference\nmodified: 2025-01-01",
            index_hook="(fact) hook")
    _memory(
        mem,
        "pattern",
        _lesson("pattern", ["- 2025-01-01 correction (a): one"], home="memory"),
        index_hook="(pattern; test) hook",
    )

    report = _report(root)

    assert _one(report, "fact")["status"] == []
    assert _one(report, "pattern")["status"] == []


def test_held_promotion_reopens_only_after_a_new_instance(root: Path) -> None:
    """Catches a declined promotion re-offered every week, or one never re-offered."""
    mem = root / "-proj" / "memory"
    instances = ["- 2026-11-01 correction (a): one"]
    _memory(mem, "ready", _lesson("pattern", instances), index_hook="(pattern; test) hook")
    _memory(
        mem,
        "held",
        _lesson("pattern", instances, extra="Promotion: held 2026-11-10 -- not yet\n"),
        index_hook="(pattern; test) hook",
    )
    _memory(
        mem,
        "reopened",
        _lesson("pattern", [*instances, "- 2026-11-20 case (b): again"], extra="Promotion: held 2026-11-10 -- no\n"),
        index_hook="(pattern; test) hook",
    )

    report = _report(root)

    assert _one(report, "ready")["status"] == ["ready_promote"]
    assert _one(report, "held")["status"] == ["held"]
    assert _one(report, "reopened")["status"] == ["ready_promote"]


def test_legacy_memories_are_sorted_for_triage(root: Path) -> None:
    """Catches untiered memories hidden from triage, or new untiered writes counted as old."""
    mem = root / "-proj" / "memory"
    _memory(mem, "ref", "A URL.\n", front="metadata:\n  type: reference\n  modified: 2026-10-01T00:00:00Z",
            index_hook="hook")
    _memory(mem, "hard", "HARD RULE: never.\n", front="type: feedback\nmodified: 2026-11-26T00:00:00Z",
            index_hook="hook")

    report = _report(root)
    ref, hard = _one(report, "ref"), _one(report, "hard")

    assert ref["status"] == ["legacy"]
    assert ref["suggested_tier"] == "fact"
    assert ref["untiered_new"] is False
    assert hard["suggested_tier"] == "observation"
    assert hard["hard_rule"] is True
    assert hard["untiered_new"] is True
    assert report["summary"]["untiered_new"] == 1


def test_format_and_index_problems_are_reported(root: Path) -> None:
    """Catches drift between files and MEMORY.md, and malformed lines a later sweep would misread."""
    mem = root / "-proj" / "memory"
    _memory(
        mem,
        "mismatch",
        _lesson("pattern", ["- 2026-11-01 correction (a): one", "- 2026-11-02 shrug (a): bad kind"]),
        index_hook="(observation; test) hook",
    )
    _memory(mem, "orphan", _lesson("observation", ["- 2026-11-01 correction (a): one"]))
    with (mem / "MEMORY.md").open("a") as handle:
        handle.write("- [Gone](gone.md) — (fact) hook\n")

    directory = _report(root)["directories"][0]
    problems = directory["problems"]

    assert any("tier observation but mismatch.md says pattern" in p for p in problems)
    assert "orphan.md: no MEMORY.md line" in problems
    assert any("no file gone.md" in p for p in problems)
    assert _one(_report(root), "mismatch")["problems"] == [
        "malformed instance line: - 2026-11-02 shrug (a): bad kind"
    ]


def test_index_near_cap_and_project_path(root: Path) -> None:
    """Catches an index about to be truncated at load, and a project whose checkout is gone."""
    project = root / "-proj"
    (project / "memory" / "MEMORY.md").write_text("".join(f"- line {n}\n" for n in range(185)))
    (project / "s.jsonl").write_text(json.dumps({"type": "x"}) + "\n" + json.dumps({"cwd": "/nonexistent/x"}) + "\n")

    directory = _report(root)["directories"][0]

    assert directory["index"]["near_cap"] is True
    assert directory["project_path"] == "/nonexistent/x"
    assert directory["project_exists"] is False


def test_record_saves_the_sweep_date_for_the_next_since(root: Path, tmp_path: Path, monkeypatch) -> None:
    """Catches a sweep that forgets where it left off, or leaves the trial review no numbers."""
    monkeypatch.setattr(memory, "SWEEP_STATE", tmp_path / "state.json")
    monkeypatch.setattr(memory, "SWEEP_LOG", tmp_path / "log.jsonl")

    memory.sweep(root, TODAY, None, record=True)

    assert memory.read_last_sweep() == TODAY
    logged = [json.loads(line) for line in (tmp_path / "log.jsonl").read_text().splitlines()]
    assert logged == [{"date": TODAY.isoformat(), "summary": {"problems": 0}}]
    assert memory.sweep(root, TODAY, None, record=False)["since"] == TODAY.isoformat()


def test_retier_updates_the_file_and_its_index_line(root: Path) -> None:
    mem = root / "-proj" / "memory"
    path = _memory(mem, "m", _lesson("observation", ["- 2026-11-01 correction (a): x"]),
                   index_hook="(observation; scope) hook")

    memory.retier(path, "pattern")

    assert "Tier: pattern" in path.read_text()
    assert "(pattern; scope) hook" in (mem / "MEMORY.md").read_text()
    assert _report(root)["directories"][0]["problems"] == []


def test_trash_moves_the_file_and_keeps_a_copy_of_the_index(root: Path, tmp_path: Path, monkeypatch) -> None:
    """Catches a deletion that cannot be undone, or one that leaves a dangling index line."""
    monkeypatch.setattr(memory, "TRASH_DIR", tmp_path / "trash")
    mem = root / "-proj" / "memory"
    keep = _memory(mem, "keep", _lesson("fact", []), index_hook="(fact) keep")
    gone = _memory(mem, "gone", _lesson("fact", []), index_hook="(fact) gone")

    result = memory.trash(gone, TODAY)

    trashed = Path(result["trashed_to"])
    assert not gone.exists() and keep.exists()
    assert trashed == tmp_path / "trash" / TODAY.isoformat() / "-proj" / "gone.md"
    assert trashed.read_text().startswith("---\nname: gone")
    assert "gone.md" not in (mem / "MEMORY.md").read_text()
    assert "keep.md" in (mem / "MEMORY.md").read_text()
    copies = list(trashed.parent.glob("MEMORY.md.*"))
    assert copies and "gone.md" in copies[0].read_text()


def test_trash_refuses_the_index(root: Path) -> None:
    (root / "-proj" / "memory" / "MEMORY.md").write_text("")
    with pytest.raises(memory.MemoryError_):
        memory.trash(root / "-proj" / "memory" / "MEMORY.md", TODAY)


# --- churn --------------------------------------------------------------------------------------


def _git(repo: Path, *args: str, date: str = "2026-11-20T12:00:00") -> str:
    env = {**os.environ, "GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date}
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True, env=env).stdout


def _commit(repo: Path, files: dict[str, str], subject: str, date: str = "2026-11-20T12:00:00") -> None:
    for path, text in files.items():
        (repo / path).parent.mkdir(parents=True, exist_ok=True)
        (repo / path).write_text(text)
        _git(repo, "add", path)
    _git(repo, "commit", "-q", "-m", subject, date=date)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "t")
    return repo


RULE = "# Rule\n\n## Alpha\n\na1\na2\n\n## Beta\n\nb1\nb2\n"


def _sections(result: dict) -> dict[tuple[str, str], list[str]]:
    return {(s["file"], s["section"]): [c["subject"] for c in s["commits"]] for s in result["sections"]}


def test_churn_maps_each_line_to_its_own_section(repo: Path) -> None:
    """Catches a hunk spanning two sections credited to one, and deletions mapped by the new text."""
    _commit(repo, {"rules/r.md": RULE}, "add")
    _commit(repo, {"rules/r.md": RULE.replace("a2\n\n## Beta\n\nb1", "a2 edited\n\n## Beta\n\nb1 edited")}, "span")
    _commit(repo, {"rules/r.md": RULE.replace("a2\n\n## Beta\n\nb1", "a2 edited\n\n## Beta\n\nb1 edited").replace(
        "b2\n", "")}, "drop b2")

    result = memory.churn(repo, ["rules"], dt.date(2026, 11, 1), min_commits=1)
    sections = _sections(result)

    assert sections[("rules/r.md", "## Alpha")] == ["add", "span"]
    assert sections[("rules/r.md", "## Beta")] == ["add", "span", "drop b2"]
    beta = next(s for s in result["sections"] if s["section"] == "## Beta")
    assert beta["commits"][-1]["removed"] == 1 and beta["commits"][-1]["added"] == 0


def test_churn_follows_heading_and_file_renames(repo: Path) -> None:
    """Catches one section's history split across its old and new names."""
    _commit(repo, {"rules/r.md": RULE}, "add")
    _commit(repo, {"rules/r.md": RULE.replace("a1", "a1 edited")}, "edit alpha")
    renamed = RULE.replace("## Alpha", "## First").replace("a1", "a1 edited")
    _commit(repo, {"rules/r.md": renamed}, "rename heading")
    _git(repo, "mv", "rules/r.md", "rules/s.md")
    _git(repo, "commit", "-q", "-m", "rename file", date="2026-11-21T12:00:00")
    _commit(repo, {"rules/s.md": renamed.replace("a2", "a2 edited")}, "edit first", date="2026-11-22T12:00:00")

    sections = _sections(memory.churn(repo, ["rules"], dt.date(2026, 11, 1), min_commits=1))

    assert sections[("rules/s.md", "## First")] == ["add", "edit alpha", "rename heading", "edit first"]
    assert not any(section == "## Alpha" for _, section in sections)
    assert not any(path == "rules/r.md" for path, _ in sections)


def test_churn_respects_the_window_and_min_commits(repo: Path) -> None:
    _commit(repo, {"rules/r.md": RULE}, "old", date="2026-09-01T12:00:00")
    _commit(repo, {"rules/r.md": RULE.replace("a1", "x")}, "one")
    _commit(repo, {"rules/r.md": RULE.replace("a1", "y")}, "two")
    _commit(repo, {"rules/r.md": RULE.replace("a1", "y").replace("b1", "z")}, "beta")

    sections = _sections(memory.churn(repo, ["rules"], dt.date(2026, 11, 1), min_commits=2))

    assert sections == {("rules/r.md", "## Alpha"): ["one", "two"]}


def test_headings_ignore_fenced_code() -> None:
    text = "## Real\n\n```markdown\n## Not a heading\n```\n\nafter\n"

    assert memory.headings(text)[-1] == "## Real"
