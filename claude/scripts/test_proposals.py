"""Tests for proposals.py. Run: uv run --with pytest pytest claude/scripts"""

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import proposals


def _proposal(status: str, milestones: str, log: str = "") -> str:
    return f"""# PROJ-001: Title

**Status:** {status}
**Created:** 2026-10-01
**Updated:** 2026-10-01

## Design Decisions (Settled)

### Cache keys

Keys carry a version.

## Milestones

{milestones}
## Decision Log

- 2026-10-01: Created.
{log}
## References

- [ADR-01](../adrs/ADR-01.md)
"""


def _milestone(n: int, status: str, as_built: str | None = None) -> str:
    text = f"### M{n}: Step {n}\n\n**Status:** {status}\n\n- Check {n}\n\n"
    if as_built is not None:
        text += f"**As built:**\n\n{as_built}\n\n"
    return text


def _write(directory: Path, name: str, text: str) -> Path:
    path = directory / name
    path.write_text(text)
    return path


def _queue(directory: Path, *rows: str) -> None:
    body = "\n".join(rows)
    _write(directory, "queue.md", f"# Queue\n\n| Milestones | Depends on | Note |\n|---|---|---|\n{body}\n")


# -- check ------------------------------------------------------------------


def _problems(directory: Path) -> list[str]:
    return [f["problem"] for f in proposals.check(directory)]


def test_check_clean_accepted_proposal(tmp_path: Path) -> None:
    _write(tmp_path, "PROJ-001-a.md", _proposal("accepted", _milestone(1, "DONE", "- Nothing beyond the checks.")
                                                 + _milestone(2, "NOT STARTED")))
    _queue(tmp_path, "| PROJ-001 M1-M2 | None | |")
    assert _problems(tmp_path) == []


def test_check_reports_unknown_status_and_missing_as_built(tmp_path: Path) -> None:
    _write(tmp_path, "PROJ-001-a.md", _proposal("accepted", _milestone(1, "CANCELED") + _milestone(2, "DONE")))
    problems = _problems(tmp_path)
    assert any("'CANCELED'" in p for p in problems)
    assert any("no As built block" in p for p in problems)


def test_check_reports_dropped_without_log_link(tmp_path: Path) -> None:
    _write(tmp_path, "PROJ-001-a.md", _proposal("accepted", _milestone(1, "DROPPED", "- Not needed.")
                                                 + _milestone(2, "NOT STARTED")))
    assert any("does not link its Decision Log" in p for p in _problems(tmp_path))


@pytest.mark.parametrize(
    "target, queue_rows, expected",
    [
        ("PROJ-002 M9", ["| PROJ-002 M1 | None | |"], "does not exist"),
        ("PROJ-002 M1", ["| PROJ-002 M1 | None | |"], "itself DROPPED"),
        ("PROJ-002 M2", [], "no queue row names"),
    ],
)
def test_check_validates_replaced_by(tmp_path: Path, target: str, queue_rows: list[str], expected: str) -> None:
    dropped = _milestone(1, "DROPPED", f"- See Decision Log.\n\nReplaced by: {target}")
    _write(tmp_path, "PROJ-001-a.md", _proposal("accepted", dropped + _milestone(2, "NOT STARTED")))
    other = _milestone(1, "DROPPED", "- See Decision Log.") + _milestone(2, "NOT STARTED")
    _write(tmp_path, "PROJ-002-b.md", _proposal("accepted", other).replace("PROJ-001", "PROJ-002"))
    _queue(tmp_path, *queue_rows)
    assert any(expected in p for p in _problems(tmp_path))


def test_check_reports_status_drift_both_ways(tmp_path: Path) -> None:
    _write(tmp_path, "PROJ-001-a.md", _proposal("accepted", _milestone(1, "DONE", "- Done.")))
    _write(tmp_path, "PROJ-002-b.md", _proposal("implemented", _milestone(1, "IN PROGRESS")))
    problems = _problems(tmp_path)
    assert any("should be implemented" in p for p in problems)
    assert any("implemented, but not every milestone" in p for p in problems)


def test_check_reports_all_dropped_and_non_era3(tmp_path: Path) -> None:
    _write(tmp_path, "PROJ-001-a.md", _proposal("accepted", _milestone(1, "DROPPED", "- See Decision Log.")))
    _write(tmp_path, "PROJ-002-b.md", _proposal("accepted", "| Milestone | Description |\n|---|---|\n| 1 | x |\n"))
    problems = _problems(tmp_path)
    assert any("every milestone is DROPPED" in p for p in problems)
    assert any("not subsections" in p for p in problems)


def _hooked(status: str, header_hook: str | None, settled_hook: str | None = None, log_hook: str | None = None) -> str:
    text = _proposal(status, _milestone(1, "NOT STARTED"))
    if header_hook is not None:
        text = text.replace("**Updated:** 2026-10-01", f"**Updated:** 2026-10-01\n**Revisit:** {header_hook}")
    if settled_hook is not None:
        text = text.replace("Keys carry a version.", f"Keys carry a version.\n\n**Revisit:** {settled_hook}")
    if log_hook is not None:
        text = text.replace("- 2026-10-01: Created.", f"- 2026-10-01: Created.\n\n**Revisit:** {log_hook}")
    return text


@pytest.mark.parametrize(
    "hook, fault",
    [
        ("when the parser streams; on or after 2027-01-15 (two releases out)", None),
        ("when the parser streams", None),
        ("on or after 2027-01-15", "no anchor"),
        ("on or after next spring (x)", "not YYYY-MM-DD"),
        ("", "neither a condition nor a date"),
    ],
)
def test_check_reports_hook_structure(tmp_path: Path, hook: str, fault: str | None) -> None:
    _write(tmp_path, "PROJ-001-a.md", _hooked("deferred", hook))
    problems = _problems(tmp_path)
    assert any(fault in p for p in problems) if fault else problems == []


def test_check_requires_a_hook_on_deferred_but_never_reports_passed_dates(tmp_path: Path) -> None:
    _write(tmp_path, "PROJ-001-a.md", _hooked("deferred", None))
    _write(tmp_path, "PROJ-002-b.md", _hooked("deferred", "on or after 2000-01-01 (long ago)").replace("PROJ-001", "PROJ-002"))
    assert _problems(tmp_path) == ["deferred proposal has no **Revisit:** line in its header"]


def test_hooks_lists_header_and_settled_hooks_passed_first(tmp_path: Path) -> None:
    _write(tmp_path, "PROJ-001-a.md", _hooked("deferred", "on or after 2027-06-01 (a)",
                                               settled_hook="when X; on or after 2026-01-01 (b)",
                                               log_hook="on or after 2025-01-01 (old copy)"))
    listed = proposals.hooks(tmp_path, "2026-10-17", passed_only=False)
    assert [(h["location"], h["date"], h["passed"]) for h in listed] == [
        ("settled", "2026-01-01", True),
        ("header", "2027-06-01", False),
    ]
    assert listed[0]["condition"] == "when X"
    assert [h["date"] for h in proposals.hooks(tmp_path, "2026-10-17", passed_only=True)] == ["2026-01-01"]


def test_check_compares_the_index(tmp_path: Path) -> None:
    _write(tmp_path, "PROJ-001-a.md", _proposal("accepted", _milestone(1, "NOT STARTED")))
    _write(tmp_path, "index.md", "| Proposal | Description | Status |\n|---|---|---|\n"
                                 "| [PROJ-001](PROJ-001-a.md) | A | implemented |\n")
    assert any("index.md lists 'implemented'" in p for p in _problems(tmp_path))


def test_check_refuses_two_indexes(tmp_path: Path) -> None:
    _write(tmp_path, "index.md", "x")
    _write(tmp_path, "README.md", "x")
    with pytest.raises(proposals.ProposalError, match="both index.md and README.md"):
        proposals.check(tmp_path)


def test_check_skips_history_and_stopped(tmp_path: Path) -> None:
    _write(tmp_path, "PROJ-001-a.md", _proposal("implemented", "| 1 | x | NOT STARTED |\n"))
    deferred = _proposal("deferred", _milestone(1, "WHATEVER"))
    _write(tmp_path, "PROJ-002-b.md", deferred.replace("**Updated:** 2026-10-01", "**Updated:** 2026-10-01\n**Revisit:** when X"))
    assert _problems(tmp_path) == []


# -- row --------------------------------------------------------------------


def test_row_picks_next_unfinished_milestone_and_reports_ready(tmp_path: Path) -> None:
    _write(tmp_path, "PROJ-001-a.md", _proposal("accepted", _milestone(1, "DONE", "- Done.")
                                                 + _milestone(2, "NOT STARTED")))
    _queue(tmp_path, "| PROJ-001 M1-M2 | None | |")
    info = proposals.row_info(tmp_path, "PROJ-001", None)
    assert info["milestone"] == 2
    assert info["row"] == "PROJ-001 M1-M2"
    assert info["ready"] is True
    assert info["last_in_row"] is True
    assert info["last_unfinished_in_proposal"] is True


def test_row_refuses_unscheduled_milestone(tmp_path: Path) -> None:
    _write(tmp_path, "PROJ-001-a.md", _proposal("accepted", _milestone(1, "NOT STARTED") + _milestone(2, "NOT STARTED")))
    _queue(tmp_path, "| PROJ-001 M1 | None | |")
    with pytest.raises(proposals.ProposalError, match="not scheduled"):
        proposals.row_info(tmp_path, "PROJ-001", 2)


def test_row_not_ready_behind_earlier_milestone_or_row(tmp_path: Path) -> None:
    _write(tmp_path, "PROJ-001-a.md", _proposal("accepted", _milestone(1, "NOT STARTED")
                                                 + _milestone(2, "NOT STARTED") + _milestone(3, "NOT STARTED")))
    _queue(tmp_path, "| PROJ-001 M1 | None | |", "| PROJ-001 M2-M3 | None | Split: other work first |")
    later = proposals.row_info(tmp_path, "PROJ-001", 3)
    assert later["ready"] is False
    assert later["earlier_rows_unfinished"] == ["PROJ-001 M1"]
    assert later["earlier_milestones_in_row_unfinished"] == ["PROJ-001 M2"]


@pytest.mark.parametrize(
    "dependency, other_status, other_milestone, state",
    [
        ("PROJ-002 M1", "accepted", "DONE", "met"),
        ("PROJ-002 M1 (deployed)", "accepted", "DONE", "confirm"),
        ("PROJ-002 M1", "accepted", "IN PROGRESS", "unmet"),
        ("PROJ-002 M1", "accepted", "DROPPED", "blocked"),
        ("PROJ-002 M1", "deferred", "NOT STARTED", "blocked"),
        ("PROJ-002", "implemented", "DONE", "met"),
        ("PROJ-002", "rejected", "DROPPED", "blocked"),
    ],
)
def test_row_classifies_dependencies(
    tmp_path: Path, dependency: str, other_status: str, other_milestone: str, state: str
) -> None:
    _write(tmp_path, "PROJ-001-a.md", _proposal("accepted", _milestone(1, "NOT STARTED")))
    other = _proposal(other_status, _milestone(1, other_milestone, "- See Decision Log."))
    _write(tmp_path, "PROJ-002-b.md", other.replace("PROJ-001", "PROJ-002"))
    _queue(tmp_path, "| PROJ-002 M1 | None | |", f"| PROJ-001 M1 | {dependency} | |")
    info = proposals.row_info(tmp_path, "PROJ-001", 1)
    assert info["dependencies"][0]["state"] == state
    assert info["ready"] is (state == "met")


def test_row_blocks_dependency_on_unscheduled_milestone(tmp_path: Path) -> None:
    _write(tmp_path, "PROJ-001-a.md", _proposal("accepted", _milestone(1, "NOT STARTED")))
    other = _proposal("accepted", _milestone(1, "NOT STARTED"))
    _write(tmp_path, "PROJ-002-b.md", other.replace("PROJ-001", "PROJ-002"))
    _queue(tmp_path, "| PROJ-001 M1 | PROJ-002 M1 | |")
    dep = proposals.row_info(tmp_path, "PROJ-001", 1)["dependencies"][0]
    assert dep["state"] == "blocked"
    assert "no queue row" in dep["reason"]


def test_row_blocks_dependency_on_unscheduled_proposal(tmp_path: Path) -> None:
    _write(tmp_path, "PROJ-001-a.md", _proposal("accepted", _milestone(1, "NOT STARTED")))
    other = _proposal("accepted", _milestone(1, "NOT STARTED"))
    _write(tmp_path, "PROJ-002-b.md", other.replace("PROJ-001", "PROJ-002"))
    _queue(tmp_path, "| PROJ-001 M1 | PROJ-002 | |")
    dep = proposals.row_info(tmp_path, "PROJ-001", 1)["dependencies"][0]
    assert dep["state"] == "blocked"
    assert "no queue row" in dep["reason"]


def test_check_reports_unreadable_queue(tmp_path: Path) -> None:
    _write(tmp_path, "PROJ-001-a.md", _proposal("accepted", _milestone(1, "NOT STARTED")))
    _queue(tmp_path, "| PROJ-001 M1 | None |")
    with pytest.raises(proposals.ProposalError, match="3 cells"):
        proposals.check(tmp_path)


def test_check_without_a_queue_skips_queue_checks(tmp_path: Path) -> None:
    dropped = _milestone(1, "DROPPED", "- See Decision Log.\n\nReplaced by: PROJ-001 M2")
    _write(tmp_path, "PROJ-001-a.md", _proposal("accepted", dropped + _milestone(2, "NOT STARTED")))
    assert _problems(tmp_path) == []


def test_row_names_replacement_for_dropped_dependency(tmp_path: Path) -> None:
    _write(tmp_path, "PROJ-001-a.md", _proposal("accepted", _milestone(1, "NOT STARTED")))
    other = _proposal("accepted", _milestone(1, "DROPPED", "- See Decision Log.\n\nReplaced by: PROJ-002 M2")
                      + _milestone(2, "NOT STARTED"))
    _write(tmp_path, "PROJ-002-b.md", other.replace("PROJ-001", "PROJ-002"))
    _queue(tmp_path, "| PROJ-002 M1-M2 | None | |", "| PROJ-001 M1 | PROJ-002 M1 | |")
    dep = proposals.row_info(tmp_path, "PROJ-001", 1)["dependencies"][0]
    assert "wait on PROJ-002 M2" in dep["reason"]


# -- freeze -----------------------------------------------------------------


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True).stdout.strip()


def _commit(repo: Path, message: str) -> str:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture
def specs(tmp_path: Path) -> Path:
    repo = tmp_path / "specs"
    (repo / "proj" / "proposals").mkdir(parents=True)
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "T")
    _git(repo, "config", "commit.gpgsign", "false")
    return repo


FROZEN = _proposal("implemented", _milestone(1, "DONE", "- Done."))


def _freeze_setup(specs: Path) -> tuple[Path, Path]:
    directory = specs / "proj" / "proposals"
    path = _write(directory, "PROJ-001-a.md", _proposal("accepted", _milestone(1, "IN PROGRESS")))
    _commit(specs, "accepted")
    path.write_text(FROZEN)
    _commit(specs, "unrelated subject")
    return directory, path


def test_freeze_allows_listed_edits(specs: Path) -> None:
    directory, path = _freeze_setup(specs)
    text = FROZEN.replace("**Updated:** 2026-10-01", "**Updated:** 2026-11-01")
    text = text.replace("- Done.", "- Done. The cache warmed in 3s, not 5s.")
    text = text.replace("../adrs/ADR-01.md", "../adr/ADR-01.md")
    text = text.replace("Keys carry a version.", "Keys carry a version. Superseded in part by PROJ-009; see Decision Log.")
    text = text.replace("- 2026-10-01: Created.\n", "- 2026-10-01: Created.\n- 2026-11-01: Revisit hook audit: extended.\n")
    path.write_text(text)
    assert proposals.freeze(directory, []) == []


def test_freeze_reports_decision_and_milestone_status_edits(specs: Path) -> None:
    directory, path = _freeze_setup(specs)
    text = FROZEN.replace("Keys carry a version.", "Keys carry no version.")
    path.write_text(text.replace("**Status:** DONE", "**Status:** IN PROGRESS"))
    [result] = proposals.freeze(directory, [])
    assert len(result["hunks"]) == 2
    assert all(h["origin"] == "row" for h in result["hunks"])
    assert result["freeze_base"] == "flip"


def test_freeze_attributes_other_sessions_commits(specs: Path) -> None:
    directory, path = _freeze_setup(specs)
    path.write_text(FROZEN.replace("Keys carry a version.", "Keys carry no version."))
    other = _commit(specs, "elsewhere")
    [result] = proposals.freeze(directory, [])
    assert result["hunks"][0]["origin"] == "other"
    [result] = proposals.freeze(directory, [other])
    assert result["hunks"][0]["origin"] == "row"


def test_freeze_counts_correction_entries(specs: Path) -> None:
    directory, path = _freeze_setup(specs)
    text = FROZEN.replace("Keys carry a version.", "Keys carry a schema version.")
    text = text.replace("- 2026-10-01: Created.\n", "- 2026-10-01: Created.\n- 2026-11-01: Correction of fact: it said a version.\n")
    path.write_text(text)
    [result] = proposals.freeze(directory, [])
    assert result["corrections_logged"] == 1
    assert len(result["hunks"]) == 1


def test_freeze_reports_other_decision_log_entries(specs: Path) -> None:
    directory, path = _freeze_setup(specs)
    path.write_text(FROZEN.replace("- 2026-10-01: Created.\n", "- 2026-10-01: Created.\n- 2026-11-01: New idea.\n"))
    [result] = proposals.freeze(directory, [])
    assert "neither a revisit audit" in result["hunks"][0]["kind"]


def test_freeze_falls_back_to_first_commit_for_imported_proposal(specs: Path) -> None:
    directory = specs / "proj" / "proposals"
    path = _write(directory, "PROJ-001-a.md", FROZEN)
    first = _commit(specs, "import")
    path.write_text(FROZEN.replace("Keys carry a version.", "Keys carry no version."))
    [result] = proposals.freeze(directory, [])
    assert result["freeze_commit"] == first
    assert result["freeze_base"] == "first-commit"


def test_freeze_attributes_deletions(specs: Path) -> None:
    directory, path = _freeze_setup(specs)
    path.write_text(FROZEN.replace("Keys carry a version.\n", ""))
    [result] = proposals.freeze(directory, [])
    assert result["hunks"][0]["origin"] == "row"
    other = _commit(specs, "elsewhere")
    [result] = proposals.freeze(directory, [])
    assert result["hunks"][0]["origin"] == "other"
    [result] = proposals.freeze(directory, [other])
    assert result["hunks"][0]["origin"] == "row"


@pytest.mark.parametrize("status, reported", [("accepted", True), ("superseded", False)])
def test_freeze_limits_status_changes(specs: Path, status: str, reported: bool) -> None:
    directory, path = _freeze_setup(specs)
    path.write_text(FROZEN.replace("**Status:** implemented", f"**Status:** {status}"))
    _commit(specs, "status")
    path.write_text(path.read_text().replace("Keys carry a version.", "Keys carry no version."))
    [result] = proposals.freeze(directory, [])
    kinds = [h["kind"] for h in result["hunks"]]
    assert any("status change" in k for k in kinds) is reported
    assert any("outside the allowed edits" in k for k in kinds)


@pytest.mark.parametrize(
    "replacement",
    [
        "Keys carry a version. Superseded in part by PROJ-009 and the rest is rewritten.",
        "Keys carry a version.\n\nSuperseded in part by PROJ-009; we now do something else entirely.",
        "Keys carry a version. Superseded in part by PROJ-009; see Decision Log. Also new text.",
    ],
)
def test_freeze_accepts_only_the_exact_marker(specs: Path, replacement: str) -> None:
    directory, path = _freeze_setup(specs)
    path.write_text(FROZEN.replace("Keys carry a version.", replacement))
    [result] = proposals.freeze(directory, [])
    assert result["hunks"]


def test_freeze_needs_an_audit_for_a_revisit_change(specs: Path) -> None:
    directory, path = _freeze_setup(specs)
    hooked = FROZEN.replace("**Updated:** 2026-10-01", "**Updated:** 2026-10-01\n**Revisit:** on or after 2027-01-01 (x)")
    path.write_text(hooked)
    _commit(specs, "hook")
    moved = hooked.replace("2027-01-01", "2027-06-01")
    path.write_text(moved)
    [result] = proposals.freeze(directory, [])
    assert "without a revisit audit" in result["hunks"][0]["kind"]
    path.write_text(moved.replace("- 2026-10-01: Created.\n", "- 2026-10-01: Created.\n- 2027-01-02: Revisit audit: extended.\n"))
    assert proposals.freeze(directory, []) == []


def test_freeze_allows_an_audited_settled_hook(specs: Path) -> None:
    directory = specs / "proj" / "proposals"
    hook = "Keys carry a version.\n\n**Revisit:** on or after 2027-01-01 (x)"
    accepted = _proposal("accepted", _milestone(1, "IN PROGRESS")).replace("Keys carry a version.", hook)
    path = _write(directory, "PROJ-001-a.md", accepted)
    _commit(specs, "accepted")
    hooked = FROZEN.replace("Keys carry a version.", hook)
    path.write_text(hooked)
    _commit(specs, "flip")
    path.write_text(hooked + "\n")
    assert proposals.freeze(directory, []) == []
    audited = hooked.replace("2027-01-01", "2027-06-01").replace(
        "- 2026-10-01: Created.\n", "- 2026-10-01: Created.\n- 2027-01-02: Revisit audit: extended.\n")
    path.write_text(audited)
    assert proposals.freeze(directory, []) == []
    path.write_text(audited.replace("\n\n**Revisit:** on or after 2027-06-01 (x)", ""))
    assert proposals.freeze(directory, []) == []


def test_freeze_ignores_implemented_only_in_the_working_tree(specs: Path) -> None:
    directory = specs / "proj" / "proposals"
    path = _write(directory, "PROJ-001-a.md", _proposal("accepted", _milestone(1, "IN PROGRESS")))
    _commit(specs, "accepted")
    path.write_text(FROZEN.replace("Keys carry a version.", "Keys carry a schema version."))
    assert proposals.freeze(directory, []) == []


def test_freeze_skips_a_proposal_never_committed(specs: Path) -> None:
    directory = specs / "proj" / "proposals"
    _write(directory, "PROJ-001-a.md", FROZEN)
    _write(directory, "README.md", "x")
    _commit(specs, "unrelated")
    _write(directory, "PROJ-001-a.md", FROZEN)
    (directory / "PROJ-002-b.md").write_text(FROZEN.replace("PROJ-001", "PROJ-002"))
    results = proposals.freeze(directory, [])
    assert [r["proposal"] for r in results] == []


def test_freeze_skips_history(specs: Path) -> None:
    directory = specs / "proj" / "proposals"
    path = _write(directory, "PROJ-001-a.md", _proposal("implemented", "| 1 | x | DONE |\n"))
    _commit(specs, "era 2")
    path.write_text(path.read_text().replace("Keys carry a version.", "Changed."))
    assert proposals.freeze(directory, []) == []


def test_freeze_follows_renames(specs: Path) -> None:
    directory, path = _freeze_setup(specs)
    flip = _git(specs, "rev-parse", "HEAD")
    _git(specs, "mv", str(path), str(directory / "PROJ-001-renamed.md"))
    _commit(specs, "rename")
    (directory / "PROJ-001-renamed.md").write_text(FROZEN.replace("Keys carry a version.", "Changed."))
    [result] = proposals.freeze(directory, [])
    assert result["freeze_commit"] == flip
