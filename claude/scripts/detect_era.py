#!/usr/bin/env python3
"""Detect a project's project-management era, and inventory what a migration to era 3 moves.

    python3 detect_era.py --specs-dir DIR [--project-root DIR]

DIR is the specs directory, such as `spec/`, which may be a symlink into a separate specs
repo. The markers come from project-management/eras.md. The result is JSON on stdout: the
era of each artifact, the live work a migration moves, and project-local copies of retired
skills. Errors go to stderr with exit status 1.

Detection reads markers, never dates. An artifact belongs to the era whose markers it carries.
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

PHASE_FILE = re.compile(r"^phase-(\d+(?:\.\d+)?)-.*\.md$")
PLAN_SECTION = re.compile(r"^## Phase (\d+(?:\.\d+)?):\s*(.*)$")
PROPOSAL_FILE = re.compile(r"^([A-Z0-9]*[A-Z][A-Z0-9]*-\d+)-.*\.md$")
PROPOSAL_REF = re.compile(r"\b([A-Z0-9]*[A-Z][A-Z0-9]*-\d+)\b")
# Older documents put the status mid-line and follow it with notes, as in
# "**Status**: DONE **Complexity**: HIGH" or "**Status:** implemented (Phase 12)". Only the
# leading status words count.
STATUS = re.compile(r"\*\*Status(?::\*\*|\*\*:)\s*([A-Za-z]+(?:[ _-](?:PROGRESS|STARTED))?)", re.IGNORECASE)
COLON_OUTSIDE = re.compile(r"^\*\*Status\*\*:", re.MULTILINE)
ERA2_TABLE = re.compile(r"^\|\s*Milestone\s*\|\s*Proposal\s*\|", re.MULTILINE | re.IGNORECASE)
ERA2_CRITERIA = re.compile(r"^### Phase \d+\.\d+", re.MULTILINE)
ERA3_MILESTONE = re.compile(r"^### M\d+:.*\n\n\*\*Status:\*\*", re.MULTILINE)
ARCHIVE_NAME = re.compile(r"complet|archiv|history|done", re.IGNORECASE)
FINISHED_PHASE = {"COMPLETE", "COMPLETED", "DONE", "SUPERSEDED", "CANCELLED", "CANCELED", "DROPPED", "SKIPPED"}
NOT_LIVE = {"implemented", "rejected", "superseded", "retracted"}
PROPOSAL_STATUSES = {"draft", "designing", "accepted", "deferred"} | NOT_LIVE
RETIRED_SKILLS = ("promote-proposal", "phase-cleanup")


class EraError(Exception):
    """A failure the user must act on; the message says what and where."""


def _status(text: str) -> str:
    m = STATUS.search(text)
    return re.sub(r"[_-]", " ", m.group(1)) if m else ""


def index_statuses(phases_dir: Path) -> dict[str, str]:
    """Read each phase's status from the phase index, keyed by phase number."""
    statuses: dict[str, str] = {}
    for name in ("index.md", "README.md"):
        path = phases_dir / name
        if not path.is_file():
            continue
        column = None
        for line in path.read_text().splitlines():
            if not line.lstrip().startswith("|"):
                continue
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if column is None and "Status" in cells:
                column = cells.index("Status")
            elif column is not None and len(cells) > column and re.fullmatch(r"\d+(?:\.\d+)?", cells[0]):
                statuses[cells[0]] = cells[column].upper()
    return statuses


def phase_files(phases_dir: Path) -> list[dict[str, Any]]:
    found = []
    indexed = index_statuses(phases_dir)
    for path in sorted(phases_dir.glob("phase-*.md"), key=lambda p: _number(PHASE_FILE.match(p.name))):
        m = PHASE_FILE.match(path.name)
        if not m:
            continue
        text = path.read_text()
        status = (_status(text) or indexed.get(m.group(1), "")).upper()
        era = 2 if ERA2_TABLE.search(text) or ERA2_CRITERIA.search(text) else 1
        scope = re.search(r"^Implements:\s*(.+)$", text, re.MULTILINE)
        found.append({
            "file": str(path),
            "phase": m.group(1),
            "era": era,
            "status": status,
            "live": status not in FINISHED_PHASE,
            "colon_outside_bold": bool(COLON_OUTSIDE.search(text)),
            "proposals": sorted(set(PROPOSAL_REF.findall(scope.group(1)))) if scope else [],
        })
    return found


def _number(m: re.Match[str] | None) -> float:
    return float(m.group(1)) if m else float("inf")


def plan_files(specs_dir: Path) -> list[dict[str, Any]]:
    """Find era 0 rolling plans: files holding `## Phase N:` sections."""
    found = []
    for path in sorted(specs_dir.glob("*.md")):
        sections = []
        for line in path.read_text().splitlines():
            m = PLAN_SECTION.match(line)
            if m:
                sections.append({
                    "phase": m.group(1),
                    "title": m.group(2),
                    "proposals": sorted(set(PROPOSAL_REF.findall(m.group(2)))),
                })
        if sections:
            found.append({
                "file": str(path),
                "likely_archive": bool(ARCHIVE_NAME.search(path.stem)),
                "sections": sections,
            })
    return found


def proposal_files(proposals_dir: Path) -> list[dict[str, Any]]:
    found = []
    for path in sorted(proposals_dir.glob("*.md")):
        m = PROPOSAL_FILE.match(path.name)
        if not m:
            continue
        text = path.read_text()
        status = _status(text).lower()
        found.append({
            "file": str(path),
            "id": m.group(1),
            "status": status,
            "live": status not in NOT_LIVE,
            "era3_milestones": bool(ERA3_MILESTONE.search(text)),
        })
    return found


def retired_copies(specs_dir: Path, project_root: Path | None) -> list[str]:
    """Find project-local copies of skills era 3 retired, which would run era 2 logic."""
    roots = [specs_dir.resolve().parent]
    if project_root is not None:
        roots.insert(0, project_root.resolve())
    found = []
    for root in roots:
        for skills in (root / ".claude" / "skills", root / "claude" / "skills"):
            for name in RETIRED_SKILLS:
                if (skills / name).exists():
                    found.append(str(skills / name))
    return sorted(set(found))


def detect(specs_dir: Path, project_root: Path | None) -> dict[str, Any]:
    if not specs_dir.is_dir():
        raise EraError(f"{specs_dir} is not a directory")
    proposals_dir = specs_dir / "proposals"
    phases_dir = specs_dir / "phases"
    phases = phase_files(phases_dir) if phases_dir.is_dir() else []
    plans = plan_files(specs_dir)
    proposals = proposal_files(proposals_dir) if proposals_dir.is_dir() else []
    has_queue = (proposals_dir / "queue.md").is_file()

    live_phases = [p for p in phases if p["live"]]
    live_sections = [s for plan in plans if not plan["likely_archive"] for s in plan["sections"]]
    eras_present = sorted(
        {p["era"] for p in phases}
        | ({0} if plans else set())
        | ({3} if has_queue or any(p["era3_milestones"] for p in proposals) else set())
    )
    if has_queue and not live_phases and not live_sections:
        era: Any = 3
    elif live_phases or live_sections:
        live_eras = {p["era"] for p in live_phases} | ({0} if live_sections else set())
        era = live_eras.pop() if len(live_eras) == 1 else "mixed"
    elif eras_present:
        era = max(eras_present)
    else:
        era = None

    return {
        "specs_dir": str(specs_dir),
        "era": era,
        "eras_present": eras_present,
        "queue": has_queue,
        "phases_dir": str(phases_dir) if phases_dir.is_dir() else None,
        "live_phases": live_phases,
        "finished_phases": len(phases) - len(live_phases),
        "plan_files": plans,
        "live_proposals": [p for p in proposals if p["live"]],
        "scheduled_proposals": [p["id"] for p in proposals if p["status"] == "scheduled"],
        "nonstandard_proposal_statuses": {
            p["id"]: p["status"] for p in proposals if p["status"] not in PROPOSAL_STATUSES | {"scheduled"}
        },
        "deferred_proposals": [p["id"] for p in proposals if p["status"] == "deferred"],
        "retired_skill_copies": retired_copies(specs_dir, project_root),
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--specs-dir", type=Path, required=True)
    parser.add_argument("--project-root", type=Path)
    args = parser.parse_args(argv)
    try:
        result = detect(args.specs_dir, args.project_root)
    except EraError as err:
        print(f"detect_era.py: {err}", file=sys.stderr)
        return 1
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
