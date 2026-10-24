"""Tests for proposals.py. Run: uv run --with pytest pytest claude/scripts"""

import json
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


def _milestone(n: int, status: str, as_built: str | None = None, live_after: str | None = None) -> str:
    live = f"**Live after:** {live_after}\n" if live_after is not None else ""
    text = f"### M{n}: Step {n}\n\n**Status:** {status}\n{live}\n- Check {n}\n\n"
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
        ("when the parser streams; on or after 2027-01-15 (two releases out).", None),
        ("on or after 2027-01-15 (after v1.2 (beta))", None),
        ("when the parser streams", None),
        ("on or after 2027-01-15.", "no anchor"),
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


def test_hooks_flags_a_passed_hook_that_ends_a_sentence(tmp_path: Path) -> None:
    _write(tmp_path, "PROJ-001-a.md", _hooked("deferred", "when X; on or after 2026-01-01 (two releases (beta))."))
    [hook] = proposals.hooks(tmp_path, "2026-10-17", passed_only=True)
    assert (hook["date"], hook["anchor"]) == ("2026-01-01", "two releases (beta)")


def test_progress_sorts_rows_into_done_ready_and_held(tmp_path: Path) -> None:
    _write(tmp_path, "PROJ-001-a.md", _proposal("accepted", _milestone(1, "DONE", "- Done.")
                                                 + _milestone(2, "DROPPED", "- See Decision Log.")
                                                 + _milestone(3, "NOT STARTED") + _milestone(4, "NOT STARTED")))
    other = _proposal("accepted", _milestone(1, "NOT STARTED"))
    _write(tmp_path, "PROJ-002-b.md", other.replace("PROJ-001", "PROJ-002"))
    _queue(tmp_path, "| PROJ-001 M1-M2 | None | |", "| PROJ-001 M3 | None | Split: PROJ-002 first |",
           "| PROJ-002 M1 | None | |", "| PROJ-001 M4 | PROJ-002 M1 | Split: needs PROJ-002 M1 |")
    report = proposals.progress(tmp_path, "2026-10-17")
    assert [e["row"] for e in report["done"]] == ["PROJ-001 M1-M2"]
    assert (report["done"][0]["done"], report["done"][0]["dropped"]) == (1, 1)
    assert [e["row"] for e in report["ready"]] == ["PROJ-001 M3", "PROJ-002 M1"]
    [held] = report["held"]
    assert held["row"] == "PROJ-001 M4"
    assert any("earlier row PROJ-001 M3" in r for r in held["held"])
    assert any("PROJ-002 M1" in r for r in held["held"])
    text = proposals.render_progress(report)
    assert "1/1 done, 1 dropped" in text
    assert "Revisit hooks\n  (none)" in text


@pytest.mark.parametrize(
    "status, queue_row, key, reason",
    [
        ("accepted", "| PROJ-001 M1-M2 | None | |", "blocked", "PROJ-001 has no M2"),
        ("deferred", "| PROJ-001 M1 | None | |", "blocked", "PROJ-001 is deferred"),
        ("accepted", "| PROJ-001 M1 | PROJ-002 M1 (deployed) | |", "awaiting_deploy", "whether it is live"),
        ("accepted", "| PROJ-001 M1 | PROJ-002 M1 (merge after deployed) | |", "awaiting_deploy", "whether it is live"),
        ("accepted", "| PROJ-001 M1 | PROJ-002 M9 | |", "blocked", "has no M9"),
    ],
)
def test_progress_separates_held_from_blocked(tmp_path: Path, status: str, queue_row: str, key: str, reason: str) -> None:
    _write(tmp_path, "PROJ-001-a.md", _hooked(status, "when X") if status == "deferred"
           else _proposal(status, _milestone(1, "NOT STARTED")))
    other = _proposal("accepted", _milestone(1, "DONE", "- Done."))
    _write(tmp_path, "PROJ-002-b.md", other.replace("PROJ-001", "PROJ-002"))
    _queue(tmp_path, "| PROJ-002 M1 | None | |", queue_row)
    report = proposals.progress(tmp_path, "2026-10-17")
    [entry] = report[key]
    assert any(reason in r for r in entry[key])
    assert report["ready"] == []


def test_progress_cli_prints_json_and_notice_prints_nothing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write(tmp_path, "PROJ-001-a.md", _proposal("accepted", _milestone(1, "NOT STARTED")))
    _queue(tmp_path, "| PROJ-001 M1 | None | |")
    assert proposals.main(["progress", "--proposals-dir", str(tmp_path), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["ready"][0]["row"] == "PROJ-001 M1"
    assert proposals.main(["notice", "--proposals-dir", str(tmp_path)]) == 0
    assert capsys.readouterr().out == ""


def _next_setup(directory: Path) -> None:
    _write(directory, "PROJ-001-a.md", _proposal("accepted", _milestone(1, "DONE", "- Done.")
                                                  + _milestone(2, "NOT STARTED") + _milestone(3, "NOT STARTED")))
    for n, deps in ((2, "None"), (3, "PROJ-009 M1"), (4, "PROJ-001 M2")):
        other = _proposal("accepted", _milestone(1, "NOT STARTED"))
        _write(directory, f"PROJ-00{n}-b.md", other.replace("PROJ-001", f"PROJ-00{n}"))
    _queue(directory, "| PROJ-001 M1 | None | |", "| PROJ-001 M2 | None | Split: PROJ-002 between |",
           "| PROJ-002 M1 | None | |", "| PROJ-001 M3 | None | Split: PROJ-002 between |",
           "| PROJ-003 M1 | PROJ-009 M1 | |", "| PROJ-004 M1 | PROJ-001 M2 | |")


def test_next_defaults_to_the_first_ready_row(tmp_path: Path) -> None:
    _next_setup(tmp_path)
    report = proposals.next_rows(tmp_path, 1, [])
    assert [e["row"] for e in report["run"]] == ["PROJ-001 M2"]
    assert report["skipped"] == []


def test_next_takes_rows_that_wait_only_on_picked_rows(tmp_path: Path) -> None:
    _next_setup(tmp_path)
    report = proposals.next_rows(tmp_path, 4, [])
    assert [e["row"] for e in report["run"]] == ["PROJ-001 M2", "PROJ-002 M1", "PROJ-001 M3", "PROJ-004 M1"]
    [skipped] = report["skipped"]
    assert skipped["row"] == "PROJ-003 M1"
    assert any("has no M1" in r or "does not exist" in r for r in skipped["reasons"])


def test_next_skips_held_proposals_and_what_waits_on_them(tmp_path: Path) -> None:
    _next_setup(tmp_path)
    report = proposals.next_rows(tmp_path, 2, ["PROJ-001"])
    assert [e["row"] for e in report["run"]] == ["PROJ-002 M1"]
    assert [s["row"] for s in report["skipped"]] == ["PROJ-001 M2", "PROJ-001 M3", "PROJ-003 M1", "PROJ-004 M1"]
    assert "held by the run's notes" in report["skipped"][0]["reasons"]
    assert any("earlier row PROJ-001 M2, which is not in the run" in r for r in report["skipped"][1]["reasons"])
    assert any("PROJ-001 M2" in r and "not in the run" in r for r in report["skipped"][3]["reasons"])


def test_next_cli_rejects_a_count_below_one(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _next_setup(tmp_path)
    assert proposals.main(["next", "--proposals-dir", str(tmp_path), "--count", "2"]) == 0
    assert [e["row"] for e in json.loads(capsys.readouterr().out)["run"]] == ["PROJ-001 M2", "PROJ-002 M1"]
    assert proposals.main(["next", "--proposals-dir", str(tmp_path), "--count", "0"]) == 1
    assert "not a positive number" in capsys.readouterr().err


def _candidate(directory: Path, pid: str, status: str = "accepted", deps: str = "", created: str = "2026-10-01",
               extra: str = "", milestones: str | None = None) -> None:
    text = _proposal(status, milestones or _milestone(1, "NOT STARTED"))
    text = text.replace("PROJ-001", pid).replace("**Created:** 2026-10-01", f"**Created:** {created}")
    text = text.replace("## Design Decisions (Settled)",
                        f"## Dependencies\n\n{deps or 'None.'}\n\n## Motivation\n\nWhy {pid}. More detail.\n\n"
                        f"{extra}\n## Design Decisions (Settled)")
    _write(directory, f"{pid}-x.md", text)


def _tier(report: dict, name: str) -> list[str]:
    return [e["proposal"] for e in report[name]]


def test_candidates_sort_tiers_by_unblocks_then_bugs_then_age(tmp_path: Path) -> None:
    _candidate(tmp_path, "PROJ-001", created="2026-09-01")
    _candidate(tmp_path, "PROJ-002", created="2026-10-05")
    _candidate(tmp_path, "PROJ-003", created="2026-10-09", extra="See `spec/bugs/20261001-crash.md`.\n")
    _candidate(tmp_path, "PROJ-007", created="2026-10-10", extra="See `spec/bugs/20260901-fixed.md`.\n")
    (tmp_path.parent / "bugs").mkdir()
    _write(tmp_path.parent / "bugs", "20260901-fixed.md", "# Bug\n\n**Status:** fixed 2026-09-30\n")
    _candidate(tmp_path, "PROJ-004", deps="- PROJ-002 (the base)")
    _candidate(tmp_path, "PROJ-005", status="designing", deps="- [PROJ-004](PROJ-004-x.md) -- builds on it")
    _candidate(tmp_path, "PROJ-006", status="rejected", deps="- PROJ-001")
    report = proposals.candidates(tmp_path)
    assert _tier(report, "ready") == ["PROJ-002", "PROJ-003", "PROJ-001", "PROJ-007"]
    assert report["ready"][3]["bugs"] == []
    assert report["ready"][0]["unblocks"] == ["PROJ-004", "PROJ-005"]
    assert report["ready"][1]["bugs"] == ["20261001-crash.md"]
    assert report["ready"][0]["motivation"] == "Why PROJ-002."
    assert _tier(report, "waiting") == ["PROJ-004"]
    assert report["waiting"][0]["waits_on"] == ["PROJ-002"]
    assert report["not_schedulable"] == []


def test_candidates_skip_scheduled_work_and_count_queued_dependencies_as_ready(tmp_path: Path) -> None:
    _candidate(tmp_path, "PROJ-001")
    _candidate(tmp_path, "PROJ-002", deps="- PROJ-001")
    _candidate(tmp_path, "PROJ-003", status="implemented (phase 12)",
               milestones=_milestone(1, "DONE", "- Done."))
    _candidate(tmp_path, "PROJ-004", deps="- PROJ-003\n- ADR-0019 (not a proposal)")
    _queue(tmp_path, "| PROJ-001 M1 | None | |")
    report = proposals.candidates(tmp_path)
    assert _tier(report, "ready") == ["PROJ-002", "PROJ-004"]
    assert _tier(report, "waiting") == []


def test_candidates_hold_back_what_cannot_be_scheduled(tmp_path: Path) -> None:
    _candidate(tmp_path, "PROJ-001", extra="## Design Decisions (Open)\n\n- Which cache?\n")
    _candidate(tmp_path, "PROJ-002", extra="## Design Decisions (Open)\n\nNone.\n")
    _candidate(tmp_path, "PROJ-003", deps="- PROJ-009 (elsewhere)\n- PROJ-004")
    _candidate(tmp_path, "PROJ-004", status="draft")
    _candidate(tmp_path, "PROJ-005", milestones=_milestone(1, "NOT STARTED") + _milestone(2, "NOT STARTED"))
    _queue(tmp_path, "| PROJ-005 M2 | None | |")
    report = proposals.candidates(tmp_path)
    assert _tier(report, "ready") == ["PROJ-002"]
    blocked = {e["proposal"]: e["reasons"] for e in report["not_schedulable"]}
    assert "open design question" in blocked["PROJ-001"][0]
    assert blocked["PROJ-003"] == ["depends on PROJ-004, which is draft"]
    assert "between scheduled ones" in blocked["PROJ-005"][0]


def test_candidates_cli_works_without_a_queue(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _candidate(tmp_path, "PROJ-001")
    assert proposals.main(["candidates", "--proposals-dir", str(tmp_path)]) == 0
    assert _tier(json.loads(capsys.readouterr().out), "ready") == ["PROJ-001"]


def test_notice_is_silent_until_a_hook_passes(tmp_path: Path) -> None:
    _write(tmp_path, "PROJ-001-a.md", _hooked("deferred", "on or after 2026-11-01 (a release)"))
    assert proposals.notice(tmp_path, "2026-10-17") == ""
    line = proposals.notice(tmp_path, "2026-11-01")
    assert line.startswith("1 revisit hook has passed")
    assert "(PROJ-001)" in line
    assert "\n" not in line


def test_a_prefix_may_start_with_a_digit(tmp_path: Path) -> None:
    _write(tmp_path, "9AB-001-a.md", _proposal("accepted", _milestone(1, "NOT STARTED")).replace("PROJ-001", "9AB-001"))
    _queue(tmp_path, "| 9AB-001 M1 | None | |")
    assert proposals.row_info(tmp_path, "9AB-001", 1)["ready"] is True


def test_check_reports_queue_rules(tmp_path: Path) -> None:
    _write(tmp_path, "PROJ-001-a.md", _proposal("accepted", _milestone(1, "NOT STARTED")
                                                 + _milestone(2, "DONE", "- Done.") + _milestone(3, "NOT STARTED")))
    _write(tmp_path, "PROJ-002-b.md", _hooked("deferred", "when X").replace("PROJ-001", "PROJ-002"))
    _queue(tmp_path, "| PROJ-001 M1 | None | |", "| PROJ-001 M2 | None | Split: other work first |",
           "| PROJ-001 M2-M3 | None | Split again |", "| PROJ-002 M1 | None | |")
    problems = _problems(tmp_path)
    assert any("PROJ-001 M2 is also in row PROJ-001 M2" in p for p in problems)
    assert any("PROJ-001 M2: finished, so it moves to the end of history.md" in p for p in problems)
    assert any("queue row PROJ-001 M1: PROJ-001 has more than one row" in p for p in problems)
    assert any("unfinished, but PROJ-002 is deferred" in p for p in problems)


def _history(directory: Path, *rows: str) -> None:
    body = "\n".join(rows)
    _write(directory, "history.md", f"# History\n\n| Milestones | Depends on | Note |\n|---|---|---|\n{body}\n")


def test_history_rows_come_before_queue_rows(tmp_path: Path) -> None:
    _write(tmp_path, "PROJ-001-a.md", _proposal("accepted", _milestone(1, "DONE", "- Done.")
                                                 + _milestone(2, "NOT STARTED")))
    _history(tmp_path, "| PROJ-001 M1 | None | Split: M2 waits |")
    _queue(tmp_path, "| PROJ-001 M2 | PROJ-001 M1 | Split from M1 |")
    rows = proposals.load_queue(tmp_path)
    assert [(r.label, r.index, r.source) for r in rows] == [
        ("PROJ-001 M1", 0, "history.md"), ("PROJ-001 M2", 1, "queue.md"),
    ]
    assert _problems(tmp_path) == []
    assert proposals.row_info(tmp_path, "PROJ-001", None)["ready"] is True


def test_check_reports_rows_in_the_wrong_file(tmp_path: Path) -> None:
    _write(tmp_path, "PROJ-001-a.md", _proposal("accepted", _milestone(1, "DONE", "- Done.")
                                                 + _milestone(2, "NOT STARTED")))
    _history(tmp_path, "| PROJ-001 M1 | None | Split |", "| PROJ-001 M2 | None | Split |")
    _queue(tmp_path, "| PROJ-001 M1 | None | Split |")
    problems = _problems(tmp_path)
    assert any("queue row PROJ-001 M1: PROJ-001 M1 is also in row PROJ-001 M1 in history.md" in p for p in problems)
    assert any("queue row PROJ-001 M2 in history.md: unfinished, so it belongs in queue.md" in p for p in problems)


def test_check_reports_done_milestone_in_no_row(tmp_path: Path) -> None:
    _write(tmp_path, "PROJ-001-a.md", _proposal("accepted", _milestone(1, "DONE", "- Done.")
                                                 + _milestone(2, "DROPPED", "- See Decision Log.")
                                                 + _milestone(3, "NOT STARTED")))
    _queue(tmp_path, "| PROJ-001 M3 | None | |")
    problems = [f for f in proposals.check(tmp_path) if "in no queue row" in f["problem"]]
    assert [f["milestone"] for f in problems] == [1]


def test_check_refuses_history_without_a_queue(tmp_path: Path) -> None:
    _write(tmp_path, "PROJ-001-a.md", _proposal("accepted", _milestone(1, "DONE", "- Done.")))
    _history(tmp_path, "| PROJ-001 M1 | None | |")
    with pytest.raises(proposals.ProposalError, match="queue.md does not exist"):
        proposals.check(tmp_path)


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
        ("PROJ-002 M1 (deployed)", "accepted", "DONE", "awaiting deploy"),
        ("PROJ-002 M1 (merge after deployed)", "accepted", "DONE", "awaiting deploy"),
        ("PROJ-002 M1 (merge after deployed)", "accepted", "IN PROGRESS", "unmet"),
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
    assert info["ready_once_deployed"] is (state == "awaiting deploy")


def _live_setup(directory: Path, other_status: str = "DONE") -> None:
    milestones = (_milestone(1, "NOT STARTED") + _milestone(2, "NOT STARTED", live_after="PROJ-002 M1 deployed")
                  + _milestone(3, "NOT STARTED"))
    _write(directory, "PROJ-001-a.md", _proposal("accepted", milestones))
    other = _proposal("accepted", _milestone(1, other_status, "- Done."))
    _write(directory, "PROJ-002-b.md", other.replace("PROJ-001", "PROJ-002"))
    _queue(directory, "| PROJ-002 M1 | None | |", "| PROJ-001 M1-M3 | None | |")


def test_row_reports_live_after_only_on_its_milestone(tmp_path: Path) -> None:
    _live_setup(tmp_path)
    first = proposals.row_info(tmp_path, "PROJ-001", 1)
    assert first["live_after"] is None
    assert first["ready"] is True

    path = tmp_path / "PROJ-001-a.md"
    path.write_text(path.read_text().replace("**Status:** NOT STARTED\n\n- Check 1", "**Status:** DONE\n\n- Check 1"))
    live = proposals.row_info(tmp_path, "PROJ-001", None)
    assert live["milestone"] == 2
    assert live["live_after"] == {
        "dependency": "PROJ-002 M1 deployed", "state": "awaiting deploy", "reason": "ask the user whether it is live",
    }
    assert (live["ready"], live["ready_once_deployed"]) == (False, True)


def test_progress_runs_earlier_milestones_before_a_live_check(tmp_path: Path) -> None:
    _live_setup(tmp_path)
    report = proposals.progress(tmp_path, "2026-10-17")
    [ready] = report["ready"]
    assert ready["row"] == "PROJ-001 M1-M3"
    assert [w["milestone"] for w in ready["live_after"]] == ["PROJ-001 M2"]
    assert report["awaiting_deploy"] == []
    assert "PROJ-001 M2 live after PROJ-002 M1 deployed: awaiting deploy" in proposals.render_progress(report)


def test_progress_puts_a_live_check_whose_deploy_is_unconfirmed_in_its_own_bucket(tmp_path: Path) -> None:
    _live_setup(tmp_path)
    path = tmp_path / "PROJ-001-a.md"
    path.write_text(path.read_text().replace("**Status:** NOT STARTED\n\n- Check 1", "**Status:** DONE\n\n- Check 1"))
    report = proposals.progress(tmp_path, "2026-10-17")
    [entry] = report["awaiting_deploy"]
    assert entry["next"] == "PROJ-001 M2"
    assert entry["awaiting_deploy"] == ["PROJ-001 M2 live after PROJ-002 M1 deployed: ask the user whether it is live"]
    assert report["blocked"] == report["held"] == []
    assert "Awaiting deploy, the user says when it is live\n  PROJ-001 M1-M3" in proposals.render_progress(report)


def test_progress_holds_a_live_check_whose_code_is_unfinished(tmp_path: Path) -> None:
    _live_setup(tmp_path, other_status="IN PROGRESS")
    path = tmp_path / "PROJ-001-a.md"
    path.write_text(path.read_text().replace("**Status:** NOT STARTED\n\n- Check 1", "**Status:** DONE\n\n- Check 1"))
    [held] = proposals.progress(tmp_path, "2026-10-17")["held"]
    assert held["held"] == ["PROJ-001 M2 live after PROJ-002 M1 deployed: PROJ-002 M1 is IN PROGRESS"]


def test_next_takes_rows_that_await_a_deploy_and_lists_them(tmp_path: Path) -> None:
    _live_setup(tmp_path)
    path = tmp_path / "PROJ-001-a.md"
    path.write_text(path.read_text().replace("**Status:** NOT STARTED\n\n- Check 1", "**Status:** DONE\n\n- Check 1"))
    [entry] = proposals.next_rows(tmp_path, 1, [])["run"]
    assert entry["row"] == "PROJ-001 M1-M3"
    assert entry["awaiting_deploy"] == ["PROJ-001 M2 live after PROJ-002 M1 deployed: ask the user whether it is live"]


def test_next_skips_a_live_check_whose_code_a_run_cannot_deploy(tmp_path: Path) -> None:
    _live_setup(tmp_path, other_status="NOT STARTED")
    path = tmp_path / "PROJ-001-a.md"
    path.write_text(path.read_text().replace("**Status:** NOT STARTED\n\n- Check 1", "**Status:** DONE\n\n- Check 1"))
    report = proposals.next_rows(tmp_path, 2, [])
    assert [e["row"] for e in report["run"]] == ["PROJ-002 M1"]
    [skipped] = report["skipped"]
    assert any("a run cannot deploy it" in r for r in skipped["reasons"])


def test_next_takes_a_row_gate_whose_code_is_done_and_lists_it(tmp_path: Path) -> None:
    _write(tmp_path, "PROJ-001-a.md", _proposal("accepted", _milestone(1, "NOT STARTED")))
    other = _proposal("accepted", _milestone(1, "DONE", "- Done.") + _milestone(2, "NOT STARTED"))
    _write(tmp_path, "PROJ-002-b.md", other.replace("PROJ-001", "PROJ-002"))
    _queue(tmp_path, "| PROJ-002 M1 | None | |", "| PROJ-001 M1 | PROJ-002 M1 (merge after deployed) | |")
    [entry] = proposals.next_rows(tmp_path, 1, [])["run"]
    assert entry["row"] == "PROJ-001 M1"
    assert entry["awaiting_deploy"] == ["PROJ-002 M1 (merge after deployed): ask the user whether it is live"]


@pytest.mark.parametrize(
    "live_after, expected",
    [
        ("PROJ-002 M1 deployed", None),
        ("PROJ-002 deployed", None),
        ("PROJ-002 M1", "cannot read **Live after:**"),
        ("PROJ-009 M1 deployed", "PROJ-009, which does not exist"),
        ("PROJ-002 M7 deployed", "PROJ-002 M7, which does not exist"),
        ("PROJ-002 M2 deployed", "PROJ-002 M2, which is DROPPED"),
    ],
)
def test_check_validates_live_after(tmp_path: Path, live_after: str, expected: str | None) -> None:
    _write(tmp_path, "PROJ-001-a.md", _proposal("accepted", _milestone(1, "NOT STARTED", live_after=live_after)))
    other = (_milestone(1, "DONE", "- Done.") + _milestone(2, "DROPPED", "- See Decision Log.")
             + _milestone(3, "NOT STARTED"))
    _write(tmp_path, "PROJ-002-b.md", _proposal("accepted", other).replace("PROJ-001", "PROJ-002"))
    _queue(tmp_path, "| PROJ-002 M1-M3 | None | |", "| PROJ-001 M1 | None | |")
    problems = [p for p in _problems(tmp_path) if "PROJ-001" in p or "Live after" in p]
    assert any(expected in p for p in problems) if expected else problems == []


def test_check_asks_to_reclassify_each_legacy_deployed_gate(tmp_path: Path) -> None:
    milestones = _milestone(1, "NOT STARTED") + _milestone(2, "NOT STARTED")
    _write(tmp_path, "PROJ-001-a.md", _proposal("accepted", milestones))
    other = _proposal("implemented", _milestone(1, "DONE", "- Done."))
    _write(tmp_path, "PROJ-002-b.md", other.replace("PROJ-001", "PROJ-002"))
    _history(tmp_path, "| PROJ-002 M1 | None | |")
    _queue(tmp_path, "| PROJ-001 M1 | PROJ-002 M1 (deployed) | Split: a |",
           "| PROJ-001 M2 | PROJ-002 M1 (merge after deployed) | Split: b |")
    [problem] = _problems(tmp_path)
    assert problem.startswith("queue row PROJ-001 M1: PROJ-002 M1 (deployed) is the legacy row gate")
    assert "**Live after:** PROJ-002 M1 deployed" in problem
    assert "PROJ-002 M1 (merge after deployed)" in problem
    assert "plain dependency" in problem


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


# -- other projects ---------------------------------------------------------


def _other_setup(
    root: Path, dependency: str = "OTHER-001 M1", other: str = "NOT STARTED", other_rows: tuple[str, ...] = (),
    entry: str | None = "- OTHER: ../other", live_after: str | None = None,
) -> Path:
    """Write a local project whose row depends on a sibling project's proposal, and return the local directory."""
    local, sibling = root / "local", root / "other"
    local.mkdir()
    sibling.mkdir()
    _write(local, "PROJ-001-a.md", _proposal("accepted", _milestone(1, "NOT STARTED", live_after=live_after)))
    _queue(local, f"| PROJ-001 M1 | {dependency} | |")
    if entry is not None:
        queue = local / "queue.md"
        queue.write_text(queue.read_text() + f"\n## Other proposals\n\n{entry}\n")
    text = _proposal("accepted", _milestone(1, other, "- See Decision Log.") + _milestone(2, "NOT STARTED"))
    _write(sibling, "OTHER-001-b.md", text.replace("PROJ-001", "OTHER-001"))
    if other_rows:
        _queue(sibling, *other_rows)
    return local


@pytest.mark.parametrize(
    "dependency, other, other_rows, state, reason",
    [
        ("OTHER-001 M1", "DONE", ("| OTHER-001 M1 | None | |",), "met", "DONE"),
        ("OTHER-001 M1", "IN PROGRESS", ("| OTHER-001 M1-M2 | None | |",), "unmet", "OTHER-001 M1 is IN PROGRESS"),
        ("OTHER-001 M1 (merge after deployed)", "DONE", ("| OTHER-001 M1 | None | |",), "awaiting deploy",
         "whether it is live"),
        ("OTHER-001 M1", "NOT STARTED", (), "blocked", "OTHER-001 M1 is in no queue row in "),
        ("OTHER-001 M2", "DONE", ("| OTHER-001 M1 | None | |",), "blocked", "OTHER-001 M2 is in no queue row in "),
        ("OTHER-001", "DONE", (), "blocked", "has no queue row for its unfinished milestones in "),
        ("OTHER-009 M1", "DONE", (), "blocked", "OTHER-009 does not exist in "),
    ],
)
def test_row_resolves_a_dependency_in_another_project(
    tmp_path: Path, dependency: str, other: str, other_rows: tuple[str, ...], state: str, reason: str
) -> None:
    local = _other_setup(tmp_path, dependency, other, other_rows)
    [dep] = proposals.row_info(local, "PROJ-001", 1)["dependencies"]
    assert (dep["state"], reason in dep["reason"]) == (state, True)
    if state == "blocked":
        assert str((tmp_path / "other").resolve()) in dep["reason"]


def test_a_dependency_on_an_unlisted_prefix_is_unresolved_and_held(tmp_path: Path) -> None:
    local = _other_setup(tmp_path, other="DONE", entry=None)
    [dep] = proposals.row_info(local, "PROJ-001", 1)["dependencies"]
    assert dep["state"] == "unresolved"
    assert "no proposals directory is listed for OTHER" in dep["reason"]
    assert "`- OTHER: <path>`" in dep["reason"]
    assert "--proposals-for OTHER=<path>" in dep["reason"]

    report = proposals.progress(local, "2026-10-17")
    assert report["blocked"] == report["ready"] == []
    [held] = report["held"]
    assert held["held"][0].startswith("OTHER-001 M1: no proposals directory is listed for OTHER")

    report = proposals.next_rows(local, 1, [])
    assert report["run"] == []
    [skipped] = report["skipped"]
    assert any("no proposals directory is listed for OTHER" in r for r in skipped["reasons"])


@pytest.mark.parametrize(
    "entry, fault",
    [
        ("- OTHER: ../missing", "which is not a directory"),
        ("- OTHER: ../local", "which holds no OTHER proposals"),
    ],
)
def test_an_entry_that_does_not_lead_to_the_proposals_is_unresolved(tmp_path: Path, entry: str, fault: str) -> None:
    local = _other_setup(tmp_path, other="DONE", entry=entry)
    [dep] = proposals.row_info(local, "PROJ-001", 1)["dependencies"]
    assert dep["state"] == "unresolved"
    assert dep["reason"].startswith("the OTHER entry (queue.md line ")
    assert fault in dep["reason"]
    assert str(tmp_path.resolve() / entry.split("../")[1]) in dep["reason"]
    assert [e["row"] for e in proposals.progress(local, "2026-10-17")["held"]] == ["PROJ-001 M1"]


def test_an_unreadable_queue_in_another_project_is_unresolved_not_an_error(tmp_path: Path) -> None:
    local = _other_setup(tmp_path, other="DONE", other_rows=("| OTHER-001 M1 | None |",))
    [dep] = proposals.row_info(local, "PROJ-001", 1)["dependencies"]
    assert dep["state"] == "unresolved"
    assert "which cannot be read" in dep["reason"]
    assert "3 cells" in dep["reason"]


def test_a_flag_overrides_an_entry_relative_to_the_current_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    local = _other_setup(tmp_path, other="DONE", other_rows=("| OTHER-001 M1 | None | |",), entry="- OTHER: ../moved")
    monkeypatch.chdir(tmp_path)
    assert proposals.main(["row", "--proposals-dir", str(local), "PROJ-001", "M1"]) == 0
    assert json.loads(capsys.readouterr().out)["dependencies"][0]["state"] == "unresolved"
    assert proposals.main(["row", "--proposals-dir", str(local), "--proposals-for", "OTHER=other", "PROJ-001"]) == 0
    info = json.loads(capsys.readouterr().out)
    assert (info["dependencies"][0]["state"], info["ready"]) == ("met", True)


def test_a_flag_adds_an_entry_for_every_resolving_command(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    local = _other_setup(tmp_path, other="DONE", other_rows=("| OTHER-001 M1 | None | |",), entry=None)
    flag = ["--proposals-for", f"OTHER={tmp_path / 'other'}"]
    assert proposals.main(["progress", "--proposals-dir", str(local), "--json", *flag]) == 0
    assert [e["row"] for e in json.loads(capsys.readouterr().out)["ready"]] == ["PROJ-001 M1"]
    assert proposals.main(["next", "--proposals-dir", str(local), *flag]) == 0
    assert [e["row"] for e in json.loads(capsys.readouterr().out)["run"]] == ["PROJ-001 M1"]
    assert proposals.main(["check", "--proposals-dir", str(local), *flag]) == 0
    assert json.loads(capsys.readouterr().out) == []
    assert proposals.main(["candidates", "--proposals-dir", str(local), *flag]) == 0
    capsys.readouterr()


@pytest.mark.parametrize("flag", ["OTHER", "other=x", "OTHER="])
def test_a_malformed_flag_is_an_error(tmp_path: Path, flag: str, capsys: pytest.CaptureFixture[str]) -> None:
    local = _other_setup(tmp_path)
    assert proposals.main(["check", "--proposals-dir", str(local), "--proposals-for", flag]) == 1
    assert "write PREFIX=PATH" in capsys.readouterr().err


def test_a_malformed_entry_is_an_error(tmp_path: Path) -> None:
    local = _other_setup(tmp_path, entry="- OTHER ../other")
    with pytest.raises(proposals.ProposalError, match="cannot read '- OTHER ../other'"):
        proposals.progress(local, "2026-10-17")


def test_an_entry_resolves_from_where_a_symlinked_queue_really_sits(tmp_path: Path) -> None:
    specs = tmp_path / "specs"
    specs.mkdir()
    _other_setup(specs, other="DONE", other_rows=("| OTHER-001 M1 | None | |",))
    checkout = tmp_path / "app"
    checkout.mkdir()
    (checkout / "spec").symlink_to(specs / "local")
    [dep] = proposals.row_info(checkout / "spec", "PROJ-001", 1)["dependencies"]
    assert dep["state"] == "met"


def test_next_skips_a_row_whose_dependency_another_project_builds(tmp_path: Path) -> None:
    local = _other_setup(tmp_path, other="IN PROGRESS", other_rows=("| OTHER-001 M1 | None | |",))
    [skipped] = proposals.next_rows(local, 1, [])["skipped"]
    assert skipped["reasons"] == ["OTHER-001 M1: OTHER-001 M1 is IN PROGRESS, and another project builds it"]


def test_row_resolves_a_live_after_line_in_another_project(tmp_path: Path) -> None:
    local = _other_setup(tmp_path, "None", "DONE", ("| OTHER-001 M1 | None | |",), live_after="OTHER-001 M1 deployed")
    info = proposals.row_info(local, "PROJ-001", 1)
    assert info["live_after"]["state"] == "awaiting deploy"
    assert (info["ready"], info["ready_once_deployed"]) == (False, True)


def test_check_reports_unresolved_entries_and_references(tmp_path: Path) -> None:
    local = _other_setup(tmp_path, "APP-001 M1", "DROPPED", ("| OTHER-001 M2 | None | |",),
                         entry="- OTHER: ../other\n- LIB: ../lib", live_after="OTHER-001 M1 deployed")
    text = _proposal("accepted", _milestone(1, "DROPPED", "- See Decision Log.\n\nReplaced by: OTHER-001 M1")
                     + _milestone(2, "DROPPED", "- See Decision Log.\n\nReplaced by: LIB-001 M1")
                     + _milestone(3, "NOT STARTED"))
    _write(local, "PROJ-002-b.md", text.replace("PROJ-001", "PROJ-002"))
    findings = proposals.check(local)
    problems = [f["problem"] for f in findings]
    [entry] = [f for f in findings if f["proposal"] is None]
    assert entry["file"] == str(local / "queue.md")
    assert entry["problem"].startswith("## Other proposals: the LIB entry (queue.md line ")
    assert "which is not a directory" in entry["problem"]
    assert any(p.startswith("queue row PROJ-001 M1: APP-001 M1 is unresolved: no proposals directory is listed for APP")
               for p in problems)
    assert "Live after names OTHER-001 M1, which is DROPPED" in problems
    assert "Replaced by names OTHER-001 M1, which is itself DROPPED" in problems
    assert any(p.startswith("Replaced by names LIB-001 M1, which is unresolved: the LIB entry") for p in problems)


def test_check_looks_for_a_replacement_in_the_other_project_queue(tmp_path: Path) -> None:
    local = _other_setup(tmp_path, "None", "DONE", ("| OTHER-001 M1 | None | |",))
    text = _proposal("accepted", _milestone(1, "DROPPED", "- See Decision Log.\n\nReplaced by: OTHER-001 M2")
                     + _milestone(2, "NOT STARTED"))
    _write(local, "PROJ-002-b.md", text.replace("PROJ-001", "PROJ-002"))
    problems = _problems(local)
    assert any(p.startswith("Replaced by names OTHER-001 M2, which no queue row names in ") for p in problems)
    _queue(tmp_path / "other", "| OTHER-001 M1-M2 | None | |")
    assert not any("OTHER-001" in p for p in _problems(local))


def test_candidates_resolve_dependencies_in_another_project(tmp_path: Path) -> None:
    local = _other_setup(tmp_path, other="DONE", entry="- OTHER: ../other\n- LIB: ../lib")
    implemented = _proposal("implemented", _milestone(1, "DONE", "- Done.")).replace("PROJ-001", "OTHER-002")
    _write(tmp_path / "other", "OTHER-002-c.md", implemented)
    _candidate(local, "PROJ-002", deps="- OTHER-002")
    _candidate(local, "PROJ-003", deps="- OTHER-001")
    _candidate(local, "PROJ-004", deps="- LIB-001")
    _candidate(local, "PROJ-005", deps="- ADR-0019 (not a proposal)")
    report = proposals.candidates(local)
    assert _tier(report, "ready") == ["PROJ-002", "PROJ-005"]
    reasons = {e["proposal"]: e["reasons"] for e in report["not_schedulable"]}
    assert reasons["PROJ-003"][0].startswith("depends on OTHER-001, which has no queue row in ")
    assert reasons["PROJ-004"][0].startswith("depends on LIB-001, which is unresolved: the LIB entry")


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
