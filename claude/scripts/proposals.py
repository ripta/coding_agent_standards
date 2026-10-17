#!/usr/bin/env python3
"""Read era 3 proposals and the queue, and run the checks the standard defines.

    python3 proposals.py check --proposals-dir DIR
    python3 proposals.py row --proposals-dir DIR PROJ-NNN [MN]
    python3 proposals.py freeze --proposals-dir DIR [--row-commit SHA ...]

The rules live in project-management/proposals.md and plans.md. `check` reports
milestone status the standard rejects. `row` finds the queue row that names a
milestone, or a proposal's next unfinished one, and says whether it is ready.
`freeze` reports edits to implemented proposals that the freeze does not allow.

DIR is the proposals directory, which may sit in a symlinked specs repo. Results
are JSON on stdout. Errors go to stderr with exit status 1.
"""

import argparse
import difflib
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

MILESTONE_STATUSES = {"NOT STARTED", "IN PROGRESS", "DONE", "DROPPED"}
FINISHED = {"DONE", "DROPPED"}
NOT_LIVE = {"implemented", "rejected", "superseded", "retracted"}
STOPPED = {"deferred", "rejected", "superseded", "retracted"}

PROPOSAL_FILE = re.compile(r"^([A-Z][A-Z0-9]*-\d+)-.*\.md$")
PROPOSAL_STATUS = re.compile(r"^\*\*Status:\*\*\s*(.+?)\s*$", re.IGNORECASE)
MILESTONE_HEADING = re.compile(r"^###\s+M(\d+):")
REPLACED_BY = re.compile(r"^\s*(?:-\s*)?Replaced by:\s*([A-Z][A-Z0-9]*-\d+)(?:\s+M(\d+))?\s*$")
AS_BUILT = "**As built:**"
ROW_RANGE = re.compile(r"^([A-Z][A-Z0-9]*-\d+)\s+M(\d+)(?:-M(\d+))?$")
DEPENDENCY = re.compile(r"^([A-Z][A-Z0-9]*-\d+)(?:\s+M(\d+))?(\s+\(deployed\))?$")
META_LINE = re.compile(r"^\*\*(Status|Updated|Revisit):\*\*", re.IGNORECASE)
PARTIAL_SUPERSESSION = re.compile(r"Superseded in part by [A-Z][A-Z0-9]*-\d+", re.IGNORECASE)
LINK_TARGET = re.compile(r"\]\([^)]*\)")
AUDIT_ENTRY = re.compile(r"\brevisit\b", re.IGNORECASE)
CORRECTION_ENTRY = re.compile(r"\bcorrection of fact\b", re.IGNORECASE)
UNCOMMITTED = "0" * 40


class ProposalError(Exception):
    """A failure the user must act on; the message says what and where."""


# -- parsing --------------------------------------------------------------


@dataclass
class Milestone:
    number: int
    status: str | None
    as_built: list[str] = field(default_factory=list)

    @property
    def replaced_by(self) -> tuple[str, int | None] | None:
        for line in self.as_built:
            m = REPLACED_BY.match(line)
            if m:
                return m.group(1), int(m.group(2)) if m.group(2) else None
        return None


@dataclass
class Proposal:
    id: str
    path: Path
    status: str
    milestones: dict[int, Milestone]
    era3: bool

    @property
    def history(self) -> bool:
        return self.status in NOT_LIVE and not self.era3


def _sections(lines: list[str]) -> dict[str, tuple[int, int]]:
    """Map each `## ` heading to its [start, end) line span."""
    spans: dict[str, tuple[int, int]] = {}
    starts = [(i, line[3:].strip()) for i, line in enumerate(lines) if line.startswith("## ")]
    for n, (i, name) in enumerate(starts):
        end = starts[n + 1][0] if n + 1 < len(starts) else len(lines)
        spans[name] = (i, end)
    return spans


def parse_proposal(path: Path, text: str | None = None) -> Proposal:
    lines = (path.read_text() if text is None else text).splitlines()
    status = ""
    for line in lines:
        m = PROPOSAL_STATUS.match(line)
        if m:
            status = m.group(1).strip().lower()
            break

    milestones: dict[int, Milestone] = {}
    start, end = _sections(lines).get("Milestones", (0, 0))
    current: Milestone | None = None
    in_as_built = False
    for line in lines[start:end]:
        heading = MILESTONE_HEADING.match(line)
        if heading:
            current = Milestone(int(heading.group(1)), None)
            milestones[current.number] = current
            in_as_built = False
            continue
        if current is None:
            continue
        if current.status is None:
            m = PROPOSAL_STATUS.match(line)
            if m:
                current.status = m.group(1).strip()
                continue
        if line.strip() == AS_BUILT:
            in_as_built = True
            continue
        if in_as_built:
            current.as_built.append(line)

    era3 = bool(milestones) and all(m.status is not None for m in milestones.values())
    match = PROPOSAL_FILE.match(path.name)
    return Proposal(match.group(1) if match else path.stem, path, status, milestones, era3)


def load_proposals(proposals_dir: Path) -> dict[str, Proposal]:
    if not proposals_dir.is_dir():
        raise ProposalError(f"{proposals_dir} is not a directory")
    proposals = {}
    for path in sorted(proposals_dir.iterdir()):
        if PROPOSAL_FILE.match(path.name):
            proposal = parse_proposal(path)
            proposals[proposal.id] = proposal
    return proposals


@dataclass
class Dependency:
    proposal: str
    milestone: int | None
    deployed: bool

    def __str__(self) -> str:
        ref = self.proposal + (f" M{self.milestone}" if self.milestone else "")
        return ref + (" (deployed)" if self.deployed else "")


@dataclass
class Row:
    index: int
    proposal: str
    first: int
    last: int
    depends_on: list[Dependency]
    note: str

    @property
    def label(self) -> str:
        if self.first == self.last:
            return f"{self.proposal} M{self.first}"
        return f"{self.proposal} M{self.first}-M{self.last}"

    def names(self, proposal: str, milestone: int) -> bool:
        return self.proposal == proposal and self.first <= milestone <= self.last


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def load_queue(proposals_dir: Path) -> list[Row]:
    path = proposals_dir / "queue.md"
    if not path.is_file():
        raise ProposalError(f"{path} does not exist. Scheduling a proposal creates it.")
    rows: list[Row] = []
    for number, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.lstrip().startswith("|"):
            continue
        cells = _cells(line)
        if len(cells) < 3 or cells[0] == "Milestones" or set(cells[0]) <= {"-", ":"}:
            continue
        m = ROW_RANGE.match(cells[0])
        if not m:
            raise ProposalError(f"{path}:{number}: cannot read milestone range {cells[0]!r}")
        first = int(m.group(2))
        last = int(m.group(3)) if m.group(3) else first
        deps = []
        for raw in re.split(r"\s*,\s*", cells[1]):
            if raw in ("", "None", "none"):
                continue
            d = DEPENDENCY.match(raw)
            if not d:
                raise ProposalError(f"{path}:{number}: cannot read dependency {raw!r}")
            deps.append(Dependency(d.group(1), int(d.group(2)) if d.group(2) else None, bool(d.group(3))))
        rows.append(Row(len(rows), m.group(1), first, last, deps, cells[2]))
    return rows


# -- check ----------------------------------------------------------------


def check(proposals_dir: Path) -> list[dict[str, Any]]:
    proposals = load_proposals(proposals_dir)
    try:
        rows = load_queue(proposals_dir)
    except ProposalError:
        rows = []
    findings: list[dict[str, Any]] = []

    def report(proposal: Proposal, problem: str, milestone: int | None = None) -> None:
        findings.append(
            {"proposal": proposal.id, "milestone": milestone, "file": str(proposal.path), "problem": problem}
        )

    def queued(pid: str, number: int) -> bool:
        return any(row.names(pid, number) for row in rows)

    for p in proposals.values():
        if p.history or p.status in STOPPED:
            continue
        if p.status == "accepted" and not p.era3:
            report(p, "accepted proposal whose milestones are not subsections with a **Status:** line")
            continue
        for m in p.milestones.values():
            if m.status not in MILESTONE_STATUSES:
                report(p, f"milestone status {m.status!r} is not one of {sorted(MILESTONE_STATUSES)}", m.number)
            if m.status in FINISHED and not m.as_built:
                report(p, f"{m.status} milestone has no As built block", m.number)
            if m.status == "DROPPED" and not any("Decision Log" in line for line in m.as_built):
                report(p, "DROPPED milestone does not link its Decision Log entry", m.number)
            target = m.replaced_by
            if target is not None and target[1] is not None:
                other = proposals.get(target[0])
                replacement = other.milestones.get(target[1]) if other else None
                ref = f"{target[0]} M{target[1]}"
                if replacement is None:
                    report(p, f"Replaced by names {ref}, which does not exist", m.number)
                elif replacement.status == "DROPPED":
                    report(p, f"Replaced by names {ref}, which is itself DROPPED", m.number)
                elif not queued(*target):
                    report(p, f"Replaced by names {ref}, which no queue row names", m.number)
            elif target is not None and target[0] not in proposals:
                report(p, f"Replaced by names {target[0]}, which does not exist", m.number)
        statuses = [m.status for m in p.milestones.values()]
        done = "DONE" in statuses
        all_finished = bool(statuses) and all(s in FINISHED for s in statuses)
        if p.status == "accepted" and all_finished and done:
            report(p, "every milestone is finished, so the proposal should be implemented")
        if p.status == "accepted" and statuses and all(s == "DROPPED" for s in statuses):
            report(p, "every milestone is DROPPED, so it can never be implemented. Retract or supersede it")
        if p.status == "implemented" and not (all_finished and done):
            report(p, "implemented, but not every milestone is finished with at least one DONE")
    return findings


# -- row ------------------------------------------------------------------


def _dependency_state(dep: Dependency, proposals: dict[str, Proposal], rows: list[Row]) -> tuple[str, str]:
    """Classify one dependency as met, unmet, confirm, or blocked, with the reason."""
    target = proposals.get(dep.proposal)
    if target is None:
        return "blocked", f"{dep.proposal} does not exist"
    if dep.milestone is None:
        if target.status == "implemented":
            return ("confirm", "confirm it runs in production") if dep.deployed else ("met", "implemented")
        if target.status != "accepted":
            return "blocked", f"{dep.proposal} is {target.status or 'missing a status'}"
        return "unmet", f"{dep.proposal} is not implemented yet"

    if target.history and target.status == "implemented":
        return ("confirm", "confirm it runs in production") if dep.deployed else ("met", "implemented history")
    milestone = target.milestones.get(dep.milestone)
    if milestone is None:
        return "blocked", f"{dep.proposal} has no M{dep.milestone}"
    if milestone.status == "DONE":
        return ("confirm", "confirm it runs in production") if dep.deployed else ("met", "DONE")
    if milestone.status == "DROPPED":
        replacement = milestone.replaced_by
        hint = f"; wait on {replacement[0]}" + (f" M{replacement[1]}" if replacement[1] else "") if replacement else ""
        return "blocked", f"{dep} is DROPPED{hint}"
    if target.status not in ("accepted", "implemented"):
        return "blocked", f"{dep.proposal} is {target.status}"
    if not any(row.names(dep.proposal, dep.milestone) for row in rows):
        return "blocked", f"{dep.proposal} M{dep.milestone} is in no queue row"
    return "unmet", f"{dep.proposal} M{dep.milestone} is {milestone.status}"


def row_info(proposals_dir: Path, proposal_id: str, milestone: int | None) -> dict[str, Any]:
    proposals = load_proposals(proposals_dir)
    rows = load_queue(proposals_dir)
    proposal = proposals.get(proposal_id)
    if proposal is None:
        raise ProposalError(f"no proposal {proposal_id} in {proposals_dir}")

    def finished(row: Row) -> bool:
        return all(
            proposal.milestones.get(n) is not None and proposal.milestones[n].status in FINISHED
            for n in range(row.first, row.last + 1)
        )

    own = [row for row in rows if row.proposal == proposal_id]
    if milestone is None:
        target = next((row for row in own if not finished(row)), None)
        if target is None:
            raise ProposalError(f"{proposal_id} has no unfinished queue row")
        milestone = next(
            n for n in range(target.first, target.last + 1)
            if proposal.milestones.get(n) is None or proposal.milestones[n].status not in FINISHED
        )
    else:
        target = next((row for row in own if row.names(proposal_id, milestone)), None)
        if target is None:
            raise ProposalError(f"{proposal_id} M{milestone} is in no queue row, so it is not scheduled")

    entry = proposal.milestones.get(milestone)
    if entry is None:
        raise ProposalError(f"{proposal_id} has no M{milestone}")
    deps = []
    for dep in target.depends_on:
        state, reason = _dependency_state(dep, proposals, rows)
        deps.append({"dependency": str(dep), "state": state, "reason": reason})
    earlier = [row.label for row in own if row.index < target.index and not finished(row)]
    pending_before = [
        f"{proposal_id} M{n}" for n in range(target.first, milestone)
        if proposal.milestones.get(n) is None or proposal.milestones[n].status not in FINISHED
    ]
    ready = (
        proposal.status == "accepted"
        and entry.status not in FINISHED
        and not earlier
        and not pending_before
        and all(d["state"] == "met" for d in deps)
    )
    return {
        "proposal": proposal_id,
        "proposal_status": proposal.status,
        "proposal_file": str(proposal.path),
        "milestone": milestone,
        "milestone_status": entry.status,
        "row": target.label,
        "row_note": target.note,
        "last_in_row": milestone == target.last,
        "last_unfinished_in_proposal": all(
            m.status in FINISHED for n, m in proposal.milestones.items() if n != milestone
        ),
        "dependencies": deps,
        "earlier_rows_unfinished": earlier,
        "earlier_milestones_in_row_unfinished": pending_before,
        "ready": ready,
    }


# -- freeze ---------------------------------------------------------------


def _git(root: Path, *args: str, check: bool = True) -> str:
    proc = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=False)
    if check and proc.returncode != 0:
        raise ProposalError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout if proc.returncode == 0 else ""


def _status_at(repo: Path, commit: str, rel: str) -> str:
    text = _git(repo, "show", f"{commit}:{rel}", check=False)
    for line in text.splitlines():
        m = PROPOSAL_STATUS.match(line)
        if m:
            return m.group(1).strip().lower()
    return ""


def freeze_point(repo: Path, rel: str) -> tuple[str, str, bool]:
    """Return the commit that wrote `implemented`, the file's path there, and whether it fell back.

    The fallback is the file's first commit, for a proposal imported already implemented.
    """
    log = _git(repo, "log", "--follow", "--first-parent", "--format=%x00%H", "--name-only", "--", rel)
    history: list[tuple[str, str]] = []
    for chunk in log.split("\x00")[1:]:
        parts = [p for p in chunk.split("\n") if p]
        if len(parts) >= 2:
            history.append((parts[0], parts[-1]))
    if not history:
        raise ProposalError(f"{rel} has no commits in {repo}")
    for n, (commit, path) in enumerate(history[:-1]):
        if _status_at(repo, commit, path) != "implemented":
            continue
        if _status_at(repo, f"{commit}^", history[n + 1][1]) != "implemented":
            return commit, path, False
    commit, path = history[-1]
    return commit, path, True


def _regions(lines: list[str]) -> list[str]:
    """Label each line meta, as-built, decision-log, or text.

    Only the header's metadata counts as meta. A milestone's status line is text, since the
    freeze allows no milestone status change.
    """
    labels = ["text"] * len(lines)
    spans = _sections(lines)
    header_end = min((start for start, _ in spans.values()), default=len(lines))
    log_start, log_end = spans.get("Decision Log", (0, 0))
    for i in range(log_start + 1, log_end):
        labels[i] = "decision-log"
    in_as_built = False
    for i, line in enumerate(lines):
        if line.startswith("#"):
            in_as_built = False
        if i < header_end and META_LINE.match(line):
            labels[i] = "meta"
        elif line.strip() == AS_BUILT:
            in_as_built = True
            labels[i] = "as-built"
        elif in_as_built:
            labels[i] = "as-built"
    return labels


def _link_only(old: list[str], new: list[str]) -> bool:
    if len(old) != len(new):
        return False
    return all(LINK_TARGET.sub("]()", a) == LINK_TARGET.sub("]()", b) for a, b in zip(old, new))


def _marker_only(old: list[str], new: list[str]) -> bool:
    """Whether the change only appends a partial supersession marker to existing lines."""
    if len(old) != len(new):
        return False
    marker = re.compile(r"\s*" + PARTIAL_SUPERSESSION.pattern + r"[^.]*\.?", re.IGNORECASE)
    return all(a == b or (PARTIAL_SUPERSESSION.search(b) and marker.sub("", b).rstrip() == a.rstrip())
               for a, b in zip(old, new))


def _entries(lines: list[str]) -> list[str]:
    """Join a Decision Log hunk's lines into its list entries."""
    entries: list[str] = []
    for line in lines:
        if line.startswith("- ") or not entries:
            entries.append(line)
        else:
            entries[-1] += " " + line.strip()
    return [e for e in entries if e.strip()]


def _blame(repo: Path, rel: str) -> list[str]:
    """Return the commit behind each working-tree line, with zeros for uncommitted lines."""
    out = _git(repo, "blame", "--porcelain", "--", rel, check=False)
    commits: list[str] = []
    for line in out.splitlines():
        m = re.match(r"^([0-9a-f]{40}) \d+ \d+", line)
        if m:
            commits.append(m.group(1))
    return commits


def freeze(proposals_dir: Path, row_commits: list[str]) -> list[dict[str, Any]]:
    proposals_dir = proposals_dir.resolve()
    repo = Path(_git(proposals_dir, "rev-parse", "--show-toplevel").strip())
    row = {_git(repo, "rev-parse", c).strip() for c in row_commits}
    results: list[dict[str, Any]] = []
    for p in load_proposals(proposals_dir).values():
        # History was edited under its own era's rules, so the freeze starts with era 3.
        if p.status != "implemented" or p.history:
            continue
        rel = str(p.path.resolve().relative_to(repo))
        commit, old_rel, fell_back = freeze_point(repo, rel)
        old = _git(repo, "show", f"{commit}:{old_rel}").splitlines()
        new = p.path.read_text().splitlines()
        old_labels, new_labels = _regions(old), _regions(new)
        blame = _blame(repo, rel)
        hunks, corrections = [], 0
        matcher = difflib.SequenceMatcher(a=old, b=new, autojunk=False)
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "equal":
                continue
            old_part, new_part = old[i1:i2], new[j1:j2]
            labels = set(old_labels[i1:i2]) | set(new_labels[j1:j2])
            kind = None
            if labels <= {"meta", "as-built"} or _link_only(old_part, new_part) or _marker_only(old_part, new_part):
                continue
            if tag == "insert" and all(PARTIAL_SUPERSESSION.search(line) or not line.strip() for line in new_part):
                continue
            if labels == {"decision-log"} and tag == "insert":
                entries = _entries(new_part)
                corrections += sum(1 for e in entries if CORRECTION_ENTRY.search(e))
                if all(AUDIT_ENTRY.search(e) or CORRECTION_ENTRY.search(e) for e in entries):
                    continue
                kind = "decision-log entry that records neither a revisit audit nor a correction of fact"
            authors = {blame[j] for j in range(j1, j2) if j < len(blame)}
            if not authors:
                origin = "unknown"
            elif authors <= row | {UNCOMMITTED}:
                origin = "row"
            else:
                origin = "other"
            hunks.append({
                "kind": kind or "changed text outside the allowed edits",
                "old_lines": [i1 + 1, i2],
                "new_lines": [j1 + 1, j2],
                "removed": old_part,
                "added": new_part,
                "origin": origin,
            })
        if hunks:
            results.append({
                "proposal": p.id,
                "file": str(p.path),
                "freeze_commit": commit,
                "freeze_fallback": fell_back,
                "corrections_logged": corrections,
                "hunks": hunks,
            })
    return results


# -- cli ------------------------------------------------------------------


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("check", "row", "freeze"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--proposals-dir", type=Path, required=True)
        if name == "row":
            cmd.add_argument("proposal")
            cmd.add_argument("milestone", nargs="?")
        if name == "freeze":
            cmd.add_argument("--row-commit", action="append", default=[])
    args = parser.parse_args(argv)
    try:
        if args.command == "check":
            result: Any = check(args.proposals_dir)
        elif args.command == "row":
            milestone = None
            if args.milestone is not None:
                m = re.fullmatch(r"M?(\d+)", args.milestone)
                if not m:
                    raise ProposalError(f"cannot read milestone {args.milestone!r}; write it as M3")
                milestone = int(m.group(1))
            result = row_info(args.proposals_dir, args.proposal, milestone)
        else:
            result = freeze(args.proposals_dir, args.row_commit)
    except ProposalError as err:
        print(f"proposals.py: {err}", file=sys.stderr)
        return 1
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
