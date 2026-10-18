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
MIGRATED = re.compile(r"^\*\*Migrated:\*\*", re.MULTILINE)
FINISHED_PHASE = {"COMPLETE", "COMPLETED", "DONE", "SUPERSEDED", "CANCELLED", "CANCELED", "DROPPED", "SKIPPED"}
NOT_LIVE = {"implemented", "rejected", "superseded", "retracted"}
PROPOSAL_STATUSES = {"draft", "designing", "accepted", "deferred"} | NOT_LIVE
RETIRED_SKILLS = ("promote-proposal", "phase-cleanup")


class EraError(Exception):
    """A failure the user must act on; the message says what and where."""


def _status(text: str) -> str:
    m = STATUS.search(text)
    return re.sub(r"[_-]", " ", m.group(1)) if m else ""


def index_rows(phases_dir: Path) -> dict[str, dict[str, str]]:
    """Read each phase's Status and Proposal cells from the phase index, keyed by phase number."""
    rows: dict[str, dict[str, str]] = {}
    for name in ("index.md", "README.md"):
        path = phases_dir / name
        if not path.is_file():
            continue
        header: list[str] | None = None
        for line in _read(path).splitlines():
            if not line.lstrip().startswith("|"):
                continue
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if header is None and "Status" in cells:
                header = cells
            elif header is not None and re.fullmatch(r"\d+(?:\.\d+)?", cells[0]):
                rows[cells[0]] = {h: c for h, c in zip(header, cells) if h in ("Status", "Proposal")}
    return rows


def _read(path: Path) -> str:
    # A stray byte in an old document must not stop detection of the rest.
    return path.read_text(errors="replace")


def _refs(text: str, known: set[str]) -> list[str]:
    """Return the proposal IDs a line names. Tokens such as UTF-8 match the pattern too, so
    only IDs of real proposal files count once any are known."""
    found = set(PROPOSAL_REF.findall(text))
    return sorted(found & known if known else found)


def phase_files(phases_dir: Path, known: set[str]) -> list[dict[str, Any]]:
    found = []
    indexed = index_rows(phases_dir)
    for path in sorted(phases_dir.glob("phase-*.md"), key=lambda p: _number(PHASE_FILE.match(p.name))):
        m = PHASE_FILE.match(path.name)
        if not m:
            continue
        text = _read(path)
        row = indexed.get(m.group(1), {})
        status = (_status(text) or row.get("Status", "")).upper()
        scope = re.search(r"^Implements:\s*(.+)$", text, re.MULTILINE)
        refs = _refs(scope.group(1), known) if scope else _refs(row.get("Proposal", ""), known)
        # Era 1 introduced proposals, so a phase file that implements none is era 0.
        if ERA2_TABLE.search(text) or ERA2_CRITERIA.search(text):
            era = 2
        else:
            era = 1 if refs else 0
        migrated = bool(MIGRATED.search(text))
        found.append({
            "file": str(path),
            "phase": m.group(1),
            "era": era,
            "status": status,
            "migrated": migrated,
            "live": status not in FINISHED_PHASE and not migrated,
            "colon_outside_bold": bool(COLON_OUTSIDE.search(text)),
            "proposals": refs,
        })
    return found


def _number(m: re.Match[str] | None) -> float:
    return float(m.group(1)) if m else float("inf")


def plan_files(specs_dir: Path, known: set[str]) -> list[dict[str, Any]]:
    """Find era 0 rolling plans: files holding `## Phase N:` sections."""
    found = []
    for path in sorted(specs_dir.glob("*.md")):
        sections: list[dict[str, Any]] = []
        for line in _read(path).splitlines():
            m = PLAN_SECTION.match(line)
            if m:
                sections.append({
                    "phase": m.group(1),
                    "title": m.group(2),
                    "proposals": _refs(m.group(2), known),
                    "migrated": False,
                })
            elif line.startswith("## "):
                sections.append({"phase": None})
            elif sections and sections[-1]["phase"] is not None and MIGRATED.search(line):
                sections[-1]["migrated"] = True
        sections = [s for s in sections if s["phase"] is not None]
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
        text = _read(path)
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
    proposals = proposal_files(proposals_dir) if proposals_dir.is_dir() else []
    known = {p["id"] for p in proposals}
    phases = phase_files(phases_dir, known) if phases_dir.is_dir() else []
    plans = plan_files(specs_dir, known)
    has_queue = (proposals_dir / "queue.md").is_file()

    live_phases = [p for p in phases if p["live"]]
    live_sections = [
        s for plan in plans if not plan["likely_archive"] for s in plan["sections"] if not s["migrated"]
    ]
    eras_present = sorted(
        {p["era"] for p in phases}
        | ({0} if plans else set())
        | ({3} if has_queue or any(p["era3_milestones"] for p in proposals) else set())
    )
    # Live work in an older form: a phase or plan section a migration has not marked with a
    # **Migrated:** line, or an accepted or scheduled proposal without milestone status. One era 3
    # proposal does not make a project era 3 while such work remains.
    old_proposals = [
        p for p in proposals if p["status"] in ("accepted", "scheduled") and not p["era3_milestones"]
    ]
    if live_phases or live_sections or old_proposals:
        if has_queue:
            era: Any = "partial"
        elif live_phases or live_sections:
            live_eras = {p["era"] for p in live_phases} | ({0} if live_sections else set())
            era = live_eras.pop() if len(live_eras) == 1 else "mixed"
        else:
            older = set(eras_present) - {3}
            era = max(older) if older else 1
    elif 3 in eras_present:
        era = 3
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
        "proposals_without_milestone_status": [p["id"] for p in old_proposals],
        "scheduled_proposals": [p["id"] for p in proposals if p["status"] == "scheduled"],
        "scheduled_without_live_phase": [
            p["id"] for p in proposals
            if p["status"] == "scheduled"
            and not any(p["id"] in x["proposals"] for x in live_phases + live_sections)
        ],
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
