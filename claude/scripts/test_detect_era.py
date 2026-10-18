"""Tests for detect_era.py. Run: uv run --with pytest pytest claude/scripts"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import detect_era

ERA1_PHASE = """# Phase 3: Parser

**Goal:** Parse it
**Status**: {status}

## Scope

Implements: PROJ-002 (milestones 1-2)

## Milestones

| Milestone | Description | Status |
|---|---|---|
| 3.1 | Lex | DONE |
"""

ERA2_PHASE = """# Phase 4: Printer

**Status:** {status}

## Scope

Implements: PROJ-003

| Milestone | Proposal | Description | Status |
|---|---|---|---|
| 4.1 | PROJ-003 M1 | Print | NOT STARTED |

### Phase 4.1
- [ ] Prints
"""

ERA3_PROPOSAL = """# PROJ-009: Queue

**Status:** accepted

## Milestones

### M1: Build

**Status:** NOT STARTED

- It builds
"""


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def _proposal(spec: Path, ident: str, status: str) -> None:
    _write(spec / "proposals" / f"{ident}-x.md", f"# {ident}: X\n\n**Status:** {status}\n")


def test_era1_and_era2_phases_and_live_work(tmp_path: Path) -> None:
    spec = tmp_path / "spec"
    _write(spec / "phases" / "phase-3-parser.md", ERA1_PHASE.format(status="DONE"))
    _write(spec / "phases" / "phase-4-printer.md", ERA2_PHASE.format(status="PLANNED"))
    _proposal(spec, "PROJ-003", "scheduled (Phase 4)")
    _proposal(spec, "PROJ-002", "implemented (Phases 3 and 5)")
    result = detect_era.detect(spec, None)
    assert result["era"] == 2
    assert result["eras_present"] == [1, 2]
    [live] = result["live_phases"]
    assert (live["phase"], live["era"], live["proposals"]) == ("4", 2, ["PROJ-003"])
    assert result["finished_phases"] == 1
    assert result["scheduled_proposals"] == ["PROJ-003"]
    assert [p["id"] for p in result["live_proposals"]] == ["PROJ-003"]


def test_a_status_mid_line_or_only_in_the_index(tmp_path: Path) -> None:
    spec = tmp_path / "spec"
    _write(spec / "phases" / "phase-1-a.md", "# Phase 1\n\nIt works. **Status**: DONE **Complexity**: HIGH\n")
    _write(spec / "phases" / "phase-2-b.md", "# Phase 2\n\nNo status line here.\n")
    _write(spec / "phases" / "index.md", "| Phase | Proposal | Description | Status | Progress |\n|---|---|---|---|---|\n"
                                         "| 2 | PROJ-001 | B | IN PROGRESS | 1/3 |\n")
    result = detect_era.detect(spec, None)
    assert [(p["phase"], p["status"]) for p in result["live_phases"]] == [("2", "IN PROGRESS")]
    assert result["era"] == 1


def test_era0_rolling_plan_and_archive(tmp_path: Path) -> None:
    spec = tmp_path / "spec"
    _write(spec / "implementation.md", "# Plan\n\n## Phase 12: Fast path (9AB-405)\n\nText\n")
    _write(spec / "completed_detailed.md", "## Phase 1: Old\n\n## Phase 2: Older\n")
    _proposal(spec, "9AB-405", "accepted")
    _proposal(spec, "9AB-100", "absorbed (by 9AB-405)")
    result = detect_era.detect(spec, None)
    assert result["era"] == 0
    plans = {Path(p["file"]).name: p for p in result["plan_files"]}
    assert plans["completed_detailed.md"]["likely_archive"] is True
    assert plans["implementation.md"]["sections"][0]["proposals"] == ["9AB-405"]
    assert result["nonstandard_proposal_statuses"] == {"9AB-100": "absorbed"}


def test_a_migrated_live_phase_is_history_and_an_unmarked_one_is_partial(tmp_path: Path) -> None:
    spec = tmp_path / "spec"
    _write(spec / "proposals" / "queue.md", "# Queue\n")
    _write(spec / "proposals" / "PROJ-003-printer.md", ERA3_PROPOSAL.replace("PROJ-009", "PROJ-003"))
    phase = _write(spec / "phases" / "phase-4-printer.md", ERA2_PHASE.format(status="PLANNED"))
    assert detect_era.detect(spec, None)["era"] == "partial"
    phase.write_text(ERA2_PHASE.format(status="PLANNED").replace(
        "## Scope", "**Migrated:** 2026-10-17, see queue.md row PROJ-003 M1\n\n## Scope"))
    result = detect_era.detect(spec, None)
    assert result["era"] == 3
    assert result["live_phases"] == []


def test_one_era3_proposal_does_not_make_a_project_era3(tmp_path: Path) -> None:
    spec = tmp_path / "spec"
    _write(spec / "phases" / "phase-1-a.md", ERA2_PHASE.format(status="COMPLETE"))
    _write(spec / "proposals" / "PROJ-009-queue.md", ERA3_PROPOSAL)
    _proposal(spec, "PROJ-010", "accepted")
    result = detect_era.detect(spec, None)
    assert result["era"] == 2
    assert result["proposals_without_milestone_status"] == ["PROJ-010"]
    _write(spec / "proposals" / "queue.md", "# Queue\n")
    assert detect_era.detect(spec, None)["era"] == "partial"


def test_an_era3_project_needs_no_queue_before_its_first_schedule(tmp_path: Path) -> None:
    spec = tmp_path / "spec"
    _write(spec / "proposals" / "PROJ-009-queue.md", ERA3_PROPOSAL)
    assert detect_era.detect(spec, None)["era"] == 3


def test_a_migrated_plan_section_is_history(tmp_path: Path) -> None:
    spec = tmp_path / "spec"
    _write(spec / "proposals" / "queue.md", "# Queue\n")
    _write(spec / "plan.md", "## Phase 12: Fast path\n\n**Migrated:** 2026-10-17, see queue.md\n\n## Notes\n")
    assert detect_era.detect(spec, None)["era"] == 3


def test_a_phase_file_with_no_proposal_is_era0_and_lookalike_ids_are_ignored(tmp_path: Path) -> None:
    spec = tmp_path / "spec"
    _write(spec / "phases" / "phase-1-a.md", "# Phase 1\n\n**Status:** PLANNED\n\nImplements: UTF-8 support\n")
    _proposal(spec, "PROJ-001", "scheduled")
    result = detect_era.detect(spec, None)
    [live] = result["live_phases"]
    assert (live["era"], live["proposals"]) == (0, [])
    assert result["scheduled_without_live_phase"] == ["PROJ-001"]


def test_a_stray_byte_does_not_stop_detection(tmp_path: Path) -> None:
    spec = tmp_path / "spec"
    path = spec / "phases" / "phase-1-a.md"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"# Phase 1\n\n**Status:** DONE \xff\n")
    assert detect_era.detect(spec, None)["finished_phases"] == 1


def test_era3_and_retired_skill_copies(tmp_path: Path) -> None:
    spec = tmp_path / "specs" / "proj" / "spec"
    _write(spec / "proposals" / "queue.md", "# Queue\n")
    _write(spec / "proposals" / "PROJ-009-queue.md", ERA3_PROPOSAL)
    _write(spec / "phases" / "phase-1-a.md", ERA2_PHASE.format(status="COMPLETE"))
    root = tmp_path / "proj"
    _write(root / ".claude" / "skills" / "promote-proposal" / "SKILL.md", "x")
    _write(spec.parent / "claude" / "skills" / "phase-cleanup" / "SKILL.md", "x")
    result = detect_era.detect(spec, root)
    assert result["era"] == 3
    assert {Path(p).name for p in result["retired_skill_copies"]} == {"phase-cleanup", "promote-proposal"}
